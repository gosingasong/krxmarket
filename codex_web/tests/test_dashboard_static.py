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

    def test_workflow_has_redundant_krx_alert_after_8pm_and_today_date_args(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for cron in ['"25 11 * * 1-5"', '"45 11 * * 1-5"', '"5 12 * * 1-5"']:
            self.assertIn(cron, workflow)
        self.assertRegex(workflow, r'"25 11 \* \* 1-5"\|"45 11 \* \* 1-5"\|"5 12 \* \* 1-5"\) REPORTS="krx_alert"')
        self.assertIn('REPORTS="krx_alert"', workflow)
        self.assertIn('DATE_ARGS="--date $BASE_DATE"', workflow)


if __name__ == "__main__":
    unittest.main()
