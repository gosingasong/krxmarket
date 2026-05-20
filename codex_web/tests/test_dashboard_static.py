import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "docs" / "app.js"
STYLES = ROOT / "docs" / "styles.css"
WORKFLOW = ROOT.parent / ".github" / "workflows" / "update_reports.yml"


class DashboardStaticTests(unittest.TestCase):
    def test_flow_columns_use_compact_classes_and_fixed_layout(self):
        app = APP_JS.read_text(encoding="utf-8")
        css = STYLES.read_text(encoding="utf-8")
        self.assertIn("flowCompactTable", app)
        self.assertIn("flowNameCell", app)
        self.assertIn("flowSectorCell", app)
        self.assertRegex(css, r"\.flowCompactTable\s*\{[^}]*table-layout:\s*fixed")
        self.assertRegex(css, r"\.flowNameCell\s*\{[^}]*max-width:")
        self.assertRegex(css, r"\.flowSectorCell\s*\{[^}]*max-width:")

    def test_wti_and_usdkrw_show_price_instead_of_candle(self):
        app = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function marketValueCell", app)
        self.assertIn('row.Ticker === "CL=F"', app)
        self.assertIn('row.Ticker === "KRW=X"', app)
        self.assertIn("formatMarketPrice", app)

    def test_kospi_nightly_futures_is_added_below_usdkrw_as_candle(self):
        source = (ROOT / "src" / "codex_web" / "sources" / "us_market.py").read_text(encoding="utf-8")
        app = APP_JS.read_text(encoding="utf-8")
        self.assertIn('"K_NIGHTLY": "KOSPI200 야간선물"', source)
        self.assertIn("KOSPI_NIGHTLY_BARS_URL", source)
        self.assertRegex(source, r'FIXED_TICKERS = \[[^\]]+"KRW=X"\]')
        self.assertRegex(source, r'(?s)_fetch_kospi_nightly_row\(\).*?fixed\.append\(row\)')
        self.assertNotIn('row.Ticker === "K_NIGHTLY"', app)

    def test_workflow_times_are_displayed_in_kst(self):
        app = APP_JS.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("function formatKstDateTime", app)
        self.assertIn("formatKstDateTime(status.generated_at)", app)
        self.assertIn("formatKstDateTime(appIndex.generated_at)", app)
        self.assertIn('name="KST"', workflow)
        self.assertIn("dt.datetime.now(KST).isoformat()", workflow)

    def test_workflow_has_redundant_us_market_morning_refreshes(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for cron in ['"30 21 * * 0-4"', '"39 21 * * 0-4"', '"50 21 * * 0-4"']:
            self.assertIn(cron, workflow)
        self.assertRegex(workflow, r'"30 21 \* \* 0-4"\|"39 21 \* \* 0-4"\|"50 21 \* \* 0-4"\) REPORTS="us_market"')

    def test_workflow_has_redundant_krx_alert_after_8pm_and_today_date_args(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for cron in ['"25 11 * * 1-5"', '"45 11 * * 1-5"', '"5 12 * * 1-5"']:
            self.assertIn(cron, workflow)
        self.assertRegex(workflow, r'"25 11 \* \* 1-5"\|"45 11 \* \* 1-5"\|"5 12 \* \* 1-5"\) REPORTS="krx_alert"')
        self.assertIn('REPORTS="krx_alert"', workflow)
        self.assertIn('DATE_ARGS="--date $BASE_DATE"', workflow)

    def test_risk_and_extra_roll_over_to_next_trading_day_like_flow(self):
        reports = (ROOT / "src" / "codex_web" / "reports.py").read_text(encoding="utf-8")
        cli = (ROOT / "src" / "codex_web" / "cli.py").read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        app = APP_JS.read_text(encoding="utf-8")

        self.assertIn("def next_krx_display_dates", reports)
        self.assertIn("risk_rollover_next", reports)
        self.assertIn("extra_rollover_next", reports)
        self.assertIn('display_dates=next_krx_display_dates(ctx, ctx.risk_rollover_next, data["target_date"])', reports)
        self.assertIn('display_dates=next_krx_display_dates(ctx, ctx.extra_rollover_next)', reports)
        self.assertIn('"--risk-rollover-next"', cli)
        self.assertIn('"--extra-rollover-next"', cli)
        self.assertIn("--risk-rollover-next", workflow)
        self.assertIn("--extra-rollover-next", workflow)
        self.assertNotIn("화면용 Risk Watch 데이터가 아직 없습니다", app)


if __name__ == "__main__":
    unittest.main()
