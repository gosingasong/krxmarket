import json

from codex_web.storage import build_global_index, build_day_manifest, write_json


REQUIRED_REPORTS = [
    "investor_flow",
    "ipo",
    "krx_alert",
    "us_market",
    "nxt_market",
    "liquidity",
]


def write_report(data_root, date_str, report_name, status="ok"):
    write_json(
        data_root / date_str / f"{report_name}.json",
        {
            "date": date_str,
            "report": report_name,
            "status": status,
            "generated_at": f"{date_str}T20:30:00+09:00",
            "data": {},
        },
    )


def test_global_latest_ignores_partial_future_rollover_folder(tmp_path):
    data_root = tmp_path / "data"
    for report_name in REQUIRED_REPORTS:
        write_report(data_root, "2026-06-09", report_name)
    write_report(data_root, "2026-06-10", "ipo")

    build_day_manifest(data_root, "2026-06-09")
    build_day_manifest(data_root, "2026-06-10")
    index = build_global_index(data_root)

    latest = json.loads((data_root / "latest.json").read_text(encoding="utf-8"))
    assert index["dates"][0]["date"] == "2026-06-10"
    assert index["latest_date"] == "2026-06-09"
    assert latest["date"] == "2026-06-09"
    assert set(latest["reports"]) == set(REQUIRED_REPORTS)


def test_global_latest_falls_back_when_no_complete_day_exists(tmp_path):
    data_root = tmp_path / "data"
    write_report(data_root, "2026-06-10", "ipo")

    build_day_manifest(data_root, "2026-06-10")
    index = build_global_index(data_root)

    latest = json.loads((data_root / "latest.json").read_text(encoding="utf-8"))
    assert index["latest_date"] == "2026-06-10"
    assert latest["date"] == "2026-06-10"
