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

    def test_workflow_uses_scheduled_attempts_and_watchdog_backstops(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        expected_crons = [
            '"5 21 * * 0-4"',
            '"8 21 * * 0-4"',
            '"11 21 * * 0-4"',
            '"14 21 * * 0-4"',
            '"17 21 * * 0-4"',
            '"1 9 * * 1-5"',
            '"4 9 * * 1-5"',
            '"7 9 * * 1-5"',
            '"10 9 * * 1-5"',
            '"13 9 * * 1-5"',
            '"6 11 * * 1-5"',
            '"9 11 * * 1-5"',
            '"12 11 * * 1-5"',
            '"15 11 * * 1-5"',
            '"18 11 * * 1-5"',
            '"31 9-13 * * 1-5"',
        ]
        for cron in expected_crons:
            self.assertIn(cron, workflow)
        for comment in [
            "06:05 KST, US market + IPO attempt 1/5",
            "18:13 KST, investor flow attempt 5/5",
            "20:18 KST, KRX alert + liquidity / NXT attempt 5/5",
            "18:31-22:31 KST, stale-data watchdog",
        ]:
            self.assertIn(comment, workflow)

    def test_memo_pushes_are_not_ignored_so_user_activity_can_refresh_stale_data(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("paths-ignore:", workflow)
        self.assertIn('"codex_web/docs/data/20*/**"', workflow)
        self.assertIn('"codex_web/docs/data/index.json"', workflow)
        self.assertIn('"codex_web/docs/data/latest.json"', workflow)
        self.assertNotIn('"codex_web/docs/data/**"', workflow)

    def test_workflow_scheduled_attempts_skip_after_fresh_success(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("group_is_fresh()", workflow)
        self.assertIn("run_group_once_if_stale()", workflow)
        self.assertIn("fresh data already exists; skipping this scheduled attempt", workflow)
        self.assertIn("generated_at is older than", workflow)
        self.assertIn("has empty investor flow rows", workflow)
        self.assertIn('run_group_once_if_stale morning_us_ipo 06:05 "$BASE_DATE" refresh_morning_us_ipo', workflow)
        self.assertIn('run_group_once_if_stale investor_flow 18:01 "$BASE_DATE" refresh_investor_flow', workflow)
        self.assertIn('run_group_once_if_stale risk_auxiliary 20:06 "$BASE_DATE" refresh_risk_and_auxiliary', workflow)
        self.assertIn('--fail-fast', workflow)

    def test_workflow_maps_requested_report_groups(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(workflow, r'"5 21 \* \* 0-4"\|"8 21 \* \* 0-4".*REPORTS="morning_us_ipo"')
        self.assertRegex(workflow, r'"1 9 \* \* 1-5"\|"4 9 \* \* 1-5".*REPORTS="investor_flow"')
        self.assertRegex(workflow, r'"6 11 \* \* 1-5"\|"9 11 \* \* 1-5".*REPORTS="risk_auxiliary"')
        self.assertIn('"31 9-13 * * 1-5") REPORTS="stale_watchdog"', workflow)
        self.assertIn('run_staleness_watchdog "$BASE_DATE"', workflow)
        self.assertIn('if [ "$EVENT_NAME" = "push" ]; then', workflow)
        self.assertIn('run_staleness_watchdog "$TODAY_KST"', workflow)
        self.assertIn('[ "$HOUR_KST" -ge 6 ] && [ "$HOUR_KST" -lt 18 ]', workflow)
        self.assertIn('python codex_web/update_reports.py --date "$BASE_DATE" --reports us_market --fail-fast --verbose', workflow)
        self.assertIn('refresh_ipo_today_and_next "$BASE_DATE"', workflow)
        self.assertIn('--flow-source-date "$BASE_DATE" --flow-rollover-next --fail-fast', workflow)
        self.assertIn('--reports krx_alert --risk-rollover-next --fail-fast', workflow)
        self.assertIn('--reports liquidity,nxt_market --extra-rollover-next --fail-fast', workflow)

    def test_client_uses_available_krx_dates_for_today_next_and_memo_rollover(self):
        app = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function nextTradingDate", app)
        self.assertIn("return nextAvailableDate(dateStr);", app)
        self.assertIn("nextTradingDate(currentDate)", app)
        self.assertIn("다음 거래일", app)
        self.assertIn("previousAvailableDate(currentDate) || shiftDateString(currentDate, -1)", app)
        self.assertNotIn("function nextCalendarDate", app)
        self.assertNotIn("const isWeekday", app)

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
        self.assertIn("MEMO_RAW_URL", app)
        self.assertIn("fetchMemoFileMetadata", app)
        self.assertIn("saveRemoteMemo", app)
        self.assertIn("function validateMemoToken", app)
        self.assertIn("github_token.txt에 있는 넓은 권한 토큰을 그대로 넣는 것은 권장하지 않습니다", app)
        self.assertIn("토큰 확인 실패", app)
        self.assertIn("state.daily?.[previousDate]", app)
        self.assertIn("function clearGlobalMemo", app)
        self.assertIn("function clearDailyMemo", app)
        self.assertIn('id="memoRefreshButton"', html)
        self.assertIn('id="memoTokenButton"', html)
        self.assertIn('id="clearGlobalMemo"', html)
        self.assertIn('id="clearDailyMemo"', html)
        self.assertIn("memoSaveStatus", html)
        self.assertIn("memoReadOnly", css)
        self.assertRegex(css, r"\.memoSaveStatus\s*\{[^}]*position:\s*absolute")
        self.assertRegex(css, r"\.memoSaveStatus\s*\{[^}]*right:\s*16px")
        self.assertRegex(css, r"\.memoSaveStatus\s*\{[^}]*bottom:\s*6px")

    def test_workflow_deploys_pages_artifact_without_pushing_generated_data(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("actions/cache/restore@v4", workflow)
        self.assertIn("actions/cache/save@v4", workflow)
        self.assertIn("krxmarket-generated-data-${{ github.run_id }}", workflow)
        self.assertIn("paths-ignore:", workflow)
        self.assertIn('"codex_web/docs/data/20*/**"', workflow)
        self.assertIn('"codex_web/docs/data/index.json"', workflow)
        self.assertIn('"codex_web/docs/data/latest.json"', workflow)
        self.assertNotIn('"codex_web/docs/data/**"', workflow)
        self.assertIn('"codex_web/state/**"', workflow)
        self.assertIn("actions/upload-pages-artifact@v4", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("git commit", workflow)

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
