import argparse
import datetime as dt
import logging
from pathlib import Path
import traceback


KST = dt.timezone(dt.timedelta(hours=9), name="KST")
DEFAULT_REPORT_NAMES = [
    "investor_flow",
    "ipo",
    "krx_alert",
    "us_market",
    "nxt_market",
    "liquidity",
]
ALL_REPORT_NAMES = list(DEFAULT_REPORT_NAMES)


def parse_date(value):
    if value:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    return dt.datetime.now(KST).date()


def parse_reports(value):
    if not value or value == "default":
        return list(DEFAULT_REPORT_NAMES)
    if value == "all":
        return list(ALL_REPORT_NAMES)
    reports = [item.strip() for item in value.split(",") if item.strip()]
    unknown = sorted(set(reports) - set(ALL_REPORT_NAMES))
    if unknown:
        raise ValueError("Unknown reports: %s" % ", ".join(unknown))
    return reports


def configure_logging(verbose=False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate date-based JSON files for the Codex Web GitHub Pages dashboard."
    )
    parser.add_argument("--date", help="Base date in YYYY-MM-DD. Default: today in KST.")
    parser.add_argument("--reports", default="default", help="default, all, or comma-separated report names.")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[2] / "docs" / "data"))
    parser.add_argument("--flow-limit", type=int, default=100, help="Investor flow rows per investor. Use 0 for all positive rows.")
    parser.add_argument("--sector-lookup-limit", type=int, default=30, help="Naver sector lookup count per investor flow side.")
    parser.add_argument("--force-non-trading", action="store_true", help="Generate KRX reports even on non-trading days.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first report error.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure_logging(args.verbose)

    base_date = parse_date(args.date)
    report_names = parse_reports(args.reports)

    from .reports import REPORT_FUNCTIONS, ReportContext, base_payload
    from .storage import build_day_manifest, build_global_index, write_report

    out_dir = Path(args.out_dir).resolve()
    root_dir = Path(__file__).resolve().parents[2]

    ctx = ReportContext(
        base_date=base_date,
        root_dir=root_dir,
        flow_limit=args.flow_limit,
        sector_lookup_limit=args.sector_lookup_limit,
        skip_non_trading=not args.force_non_trading,
    )

    logging.info("date=%s reports=%s out_dir=%s", base_date, ",".join(report_names), out_dir)

    written_dates = set()
    for report_name in report_names:
        logging.info("[%s] generating", report_name)
        try:
            payload = REPORT_FUNCTIONS[report_name](ctx)
        except Exception as exc:
            logging.error("[%s] failed: %s", report_name, exc)
            if args.verbose:
                logging.error(traceback.format_exc())
            payload = base_payload(
                ctx,
                report_name,
                status="error",
                data={
                    "error": str(exc),
                    "traceback": traceback.format_exc() if args.verbose else None,
                },
            )
            if args.fail_fast:
                write_report(out_dir, ctx.date_str, report_name, payload)
                written_dates.add(ctx.date_str)
                raise

        write_date = payload.get("display_date") or ctx.date_str
        path = write_report(out_dir, write_date, report_name, payload)
        written_dates.add(write_date)
        logging.info("[%s] wrote %s status=%s", report_name, path, payload.get("status"))

    for date_str in sorted(written_dates):
        build_day_manifest(out_dir, date_str)
    build_global_index(out_dir)
    logging.info("done")
    return 0
