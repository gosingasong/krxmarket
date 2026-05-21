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
        for cron in [
            '"25 11 * * 1-5"',
            '"45 11 * * 1-5"',
            '"5 12 * * 1-5"',
            '"25 12 * * 1-5"',
            '"45 12 * * 1-5"',
        ]:
            self.assertIn(cron, workflow)
        self.assertRegex(
            workflow,
            r'"25 11 \* \* 1-5"\|"45 11 \* \* 1-5"\|"5 12 \* \* 1-5"\|"25 12 \* \* 1-5"\|"45 12 \* \* 1-5"\) REPORTS="krx_alert"',
        )
        self.assertIn('REPORTS="krx_alert"', workflow)
        self.assertIn('DATE_ARGS="--date $BASE_DATE"', workflow)

    def test_workflow_retries_and_evening_catchup_cover_all_krx_reports(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for cron in [
            '"20 6 * * 1-5"',
            '"40 6 * * 1-5"',
            '"0 7 * * 1-5"',
            '"1 9 * * 1-5"',
            '"20 9 * * 1-5"',
            '"40 9 * * 1-5"',
            '"10 11 * * 1-5"',
            '"30 11 * * 1-5"',
            '"50 11 * * 1-5"',
            '"5 13 * * 1-5"',
        ]:
            self.assertIn(cron, workflow)
        self.assertRegex(workflow, r'"20 6 \* \* 1-5"\|"40 6 \* \* 1-5"\|"0 7 \* \* 1-5"\) REPORTS="ipo"')
        self.assertRegex(workflow, r'"1 9 \* \* 1-5"\|"20 9 \* \* 1-5"\|"40 9 \* \* 1-5"\) REPORTS="investor_flow"')
        self.assertRegex(workflow, r'"10 11 \* \* 1-5"\|"30 11 \* \* 1-5"\|"50 11 \* \* 1-5"\) REPORTS="liquidity,nxt_market"')
        self.assertIn('REPORTS="evening_krx"', workflow)
        self.assertIn('refresh_evening_krx "$BASE_DATE"', workflow)
        self.assertIn('refresh_ipo_today_and_next "$BASE_DATE"', workflow)
        self.assertIn('--flow-source-date "$BASE_DATE" --flow-rollover-next', workflow)
        self.assertIn('--risk-rollover-next', workflow)
        self.assertIn('--extra-rollover-next', workflow)

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
    def test_daily_memo_rolls_to_next_day_and_clear_buttons_exist(self):
        app = APP_JS.read_text(encoding="utf-8")
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        css = STYLES.read_text(encoding="utf-8")
        self.assertIn("let activeDailyMemoDate", app)
        self.assertIn("function dailyMemoSourceDate", app)
        self.assertIn("shiftDateString(currentDate, -1)", app)
        self.assertIn("localStorage.getItem(dailyMemoKey(previousDate))", app)
        self.assertIn("function clearGlobalMemo", app)
        self.assertIn("function clearDailyMemo", app)
        self.assertIn('id="clearGlobalMemo"', html)
        self.assertIn('id="clearDailyMemo"', html)
        self.assertIn("memoSaveStatus", html)
        self.assertRegex(css, r"\.memoSaveStatus\s*\{[^}]*position:\s*absolute")
        self.assertRegex(css, r"\.memoSaveStatus\s*\{[^}]*right:\s*16px")
        self.assertRegex(css, r"\.memoSaveStatus\s*\{[^}]*bottom:\s*6px")

    def test_favicon_links_and_assets_exist(self):
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        for rel in [
            'rel="icon" href="./favicon.ico"',
            'rel="icon" type="image/png" href="./favicon.png"',
            'rel="apple-touch-icon" href="./apple-touch-icon.png"',
        ]:
            self.assertIn(rel, html)
        for name in ["favicon.ico", "favicon.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png"]:
            path = ROOT / "docs" / name
            self.assertTrue(path.exists(), name)
            self.assertGreater(path.stat().st_size, 0, name)


if __name__ == "__main__":
    unittest.main()
