import datetime as dt
from pathlib import Path

import pandas as pd

from .serialization import dataframe_records, json_safe
from .sources.common import KST, TradingDayCalendar
from .sources.ipo import fetch_ipo_items
from .sources.krx import analyze_krx_alerts, fetch_investor_flow
from .sources.liquidity import fetch_liquidity_data
from .sources.nxt import fetch_nxt_market_trade_summary
from .sources.us_market import fetch_us_market_data


class ReportContext:
    def __init__(
        self,
        base_date,
        root_dir,
        flow_limit=100,
        sector_lookup_limit=30,
        skip_non_trading=True,
    ):
        self.base_date = base_date
        self.root_dir = Path(root_dir).resolve()
        self.state_dir = self.root_dir / "state"
        self.flow_limit = flow_limit
        self.sector_lookup_limit = sector_lookup_limit
        self.skip_non_trading = skip_non_trading
        self.calendar = TradingDayCalendar()

    @property
    def date_str(self):
        return self.base_date.isoformat()

    @property
    def yyyymmdd(self):
        return self.base_date.strftime("%Y%m%d")


def generated_at():
    return dt.datetime.now(KST).isoformat()


def base_payload(ctx, report_name, status="ok", data=None, summary=None, **extra):
    payload = {
        "schema_version": 1,
        "report": report_name,
        "status": status,
        "date": ctx.date_str,
        "generated_at": generated_at(),
        "source": {"module": "codex_web"},
        "data": data or {},
        "summary": summary or {},
    }
    payload.update(extra)
    return json_safe(payload)


def skipped_payload(ctx, report_name, reason):
    return base_payload(ctx, report_name, status="skipped", data={"reason": reason})


def is_krx_trading_day(ctx):
    return ctx.calendar.is_krx_trading_day(ctx.base_date)


def fetch_investor_flow_report(ctx):
    if ctx.skip_non_trading and not is_krx_trading_day(ctx):
        return skipped_payload(ctx, "investor_flow", "KRX 휴장일")
    data = fetch_investor_flow(
        ctx.yyyymmdd,
        limit=ctx.flow_limit,
        sector_lookup_limit=ctx.sector_lookup_limit,
    )
    summary = {
        "institution_count": len(data["institution"]),
        "institution_total_count": data["institution_total_count"],
        "foreigner_count": len(data["foreigner"]),
        "foreigner_total_count": data["foreigner_total_count"],
    }
    return base_payload(ctx, "investor_flow", data=data, summary=summary)


def fetch_krx_alert_report(ctx):
    if ctx.skip_non_trading and not is_krx_trading_day(ctx):
        return skipped_payload(ctx, "krx_alert", "KRX 휴장일")
    data = analyze_krx_alerts(ctx.base_date, ctx.state_dir)
    summary = {
        "release_count": len(data["release"]),
        "designation_count": len(data["designation"]),
        "redesignation_count": len(data["redesignation"]),
        "target_date": data["target_date"],
    }
    return base_payload(ctx, "krx_alert", data=data, summary=summary)


def fetch_ipo_report(ctx):
    if ctx.skip_non_trading and not is_krx_trading_day(ctx):
        return skipped_payload(ctx, "ipo", "KRX 휴장일")
    today_date = pd.Timestamp(ctx.base_date)
    next_date = ctx.calendar.add_krx_trading_days(today_date, 1)
    if next_date is None:
        return skipped_payload(ctx, "ipo", "다음 거래일 계산 실패")
    today_items = fetch_ipo_items(today_date)
    next_items = fetch_ipo_items(next_date)
    data = {
        "source_date": ctx.date_str,
        "today_listing_date": today_date.strftime("%Y.%m.%d"),
        "next_listing_date": next_date.strftime("%Y.%m.%d"),
        "target_listing_date": next_date.strftime("%Y.%m.%d"),
        "today_items": today_items,
        "next_items": next_items,
        "items": next_items,
    }
    return base_payload(
        ctx,
        "ipo",
        data=data,
        summary={
            "today_item_count": len(today_items),
            "next_item_count": len(next_items),
            "item_count": len(next_items),
        },
    )


def fetch_us_market_report(ctx):
    market = fetch_us_market_data(ctx.base_date)
    data = {
        "fixed": market["fixed"],
        "top_traded_value": market["top_traded_value"],
        "target_session_date": market["target_session_date"],
        "market_date": market["market_date"],
        "note": market["note"],
    }
    return base_payload(
        ctx,
        "us_market",
        data=data,
        summary={
            "fixed_count": len(market["fixed"]),
            "top_traded_value_count": len(market["top_traded_value"]),
            "target_session_date": market["target_session_date"],
            "market_date": market["market_date"],
        },
    )


def fetch_nxt_market_report(ctx):
    data = fetch_nxt_market_trade_summary()
    return base_payload(ctx, "nxt_market", data=data)


def fetch_liquidity_report(ctx):
    data = fetch_liquidity_data(ctx.base_date)
    upper = dataframe_records(data["upper"])
    lower = dataframe_records(data["lower"])
    payload_data = {"range": data["range"], "upper": upper, "lower": lower}
    summary = {"upper_count": len(upper), "lower_count": len(lower)}
    if upper:
        summary["latest_credit_date"] = upper[-1].get("Date")
    if lower:
        summary["latest_liquidity_date"] = lower[-1].get("Date")
    return base_payload(ctx, "liquidity", data=payload_data, summary=summary)


REPORT_FUNCTIONS = {
    "investor_flow": fetch_investor_flow_report,
    "krx_alert": fetch_krx_alert_report,
    "ipo": fetch_ipo_report,
    "us_market": fetch_us_market_report,
    "nxt_market": fetch_nxt_market_report,
    "liquidity": fetch_liquidity_report,
}

DEFAULT_REPORTS = [
    "investor_flow",
    "ipo",
    "krx_alert",
    "us_market",
    "nxt_market",
    "liquidity",
]

ALL_REPORTS = list(REPORT_FUNCTIONS.keys())
