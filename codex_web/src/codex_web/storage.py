import datetime as dt
import json
from pathlib import Path
import re

from .serialization import json_safe


DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_REPORT_NAMES = {
    "investor_flow",
    "ipo",
    "krx_alert",
    "us_market",
    "nxt_market",
    "liquidity",
}


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp_path.replace(path)


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def report_summary(payload):
    data = payload.get("data") or {}
    summary = dict(payload.get("summary") or {})
    status = payload.get("status", "unknown")

    if not summary and isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                summary[key + "_count"] = len(value)
            elif isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    if isinstance(nested_value, list):
                        summary["%s_%s_count" % (key, nested_key)] = len(nested_value)

    summary["status"] = status
    return summary


def write_report(data_root, date_str, report_name, payload):
    report_path = Path(data_root) / date_str / ("%s.json" % report_name)
    write_json(report_path, payload)
    return report_path


def build_day_manifest(data_root, date_str):
    day_dir = Path(data_root) / date_str
    reports = {}
    if day_dir.exists():
        for path in sorted(day_dir.glob("*.json")):
            if path.name == "manifest.json":
                continue
            try:
                payload = read_json(path)
            except Exception as exc:
                reports[path.stem] = {"status": "read_error", "error": str(exc)}
                continue
            reports[path.stem] = {
                "file": path.name,
                "report": payload.get("report", path.stem),
                "status": payload.get("status", "unknown"),
                "generated_at": payload.get("generated_at"),
                "summary": report_summary(payload),
            }

    manifest = {
        "schema_version": 1,
        "date": date_str,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "reports": reports,
    }
    write_json(day_dir / "manifest.json", manifest)
    return manifest


def build_global_index(data_root):
    data_root = Path(data_root)
    dates = []
    if data_root.exists():
        for day_dir in sorted(data_root.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            manifest_path = day_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = read_json(manifest_path)
            except Exception:
                continue
            dates.append(
                {
                    "date": day_dir.name,
                    "manifest": "%s/manifest.json" % day_dir.name,
                    "reports": manifest.get("reports", {}),
                }
            )

    latest_complete = next((item for item in dates if day_has_complete_reports(item)), dates[0] if dates else None)
    index = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "latest_date": latest_complete["date"] if latest_complete else None,
        "dates": dates,
    }
    write_json(data_root / "index.json", index)
    if latest_complete:
        write_json(data_root / "latest.json", latest_complete)
    return index


def day_has_complete_reports(index_item):
    reports = index_item.get("reports") or {}
    if not DEFAULT_REPORT_NAMES.issubset(reports):
        return False
    return all((reports.get(name) or {}).get("status") == "ok" for name in DEFAULT_REPORT_NAMES)



def prune_old_data(data_root, today=None, keep_days=60, keep_min=20):
    data_root = Path(data_root)
    if not data_root.exists():
        return []
    today = today or dt.datetime.now(dt.timezone.utc).date()
    cutoff = today - dt.timedelta(days=keep_days)
    day_dirs = []
    for path in data_root.iterdir():
        if not path.is_dir() or not DATE_DIR_RE.match(path.name):
            continue
        try:
            day = dt.date.fromisoformat(path.name)
        except ValueError:
            continue
        day_dirs.append((day, path))
    day_dirs.sort(reverse=True)
    protected = {path for _, path in day_dirs[:keep_min]}
    removed = []
    for day, path in day_dirs:
        if path in protected or day >= cutoff:
            continue
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
        removed.append(path.name)
    return removed
