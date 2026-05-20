import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_web.reports import ReportContext
from codex_web.sources import krx


class InvestorFlowTests(unittest.TestCase):
    def test_report_context_defaults_to_top10_flow_and_sector_lookup(self):
        ctx = ReportContext(base_date=__import__("datetime").date(2026, 5, 20), root_dir=ROOT)
        self.assertEqual(ctx.flow_limit, 10)
        self.assertEqual(ctx.sector_lookup_limit, 10)

    def test_fetch_investor_flow_returns_top10_with_sector_counts(self):
        institution_rows = [
            {"ticker": f"I{i:06d}", "name": f"기관{i}", "buy_amount_raw": 1000 - i, "sector": "old"}
            for i in range(12)
        ]
        foreigner_rows = [
            {"ticker": f"F{i:06d}", "name": f"외국인{i}", "buy_amount_raw": 1000 - i}
            for i in range(12)
        ]
        sector_map = {
            **{f"I{i:06d}": "반도체" if i < 3 else "자동차" for i in range(10)},
            **{f"F{i:06d}": "기계" if i < 4 else "복합기업" for i in range(10)},
        }

        def fake_ranking(date_str, investor_name, limit=10):
            rows = institution_rows if investor_name == "기관합계" else foreigner_rows
            return rows[:limit], len(rows)

        with patch.object(krx, "fetch_investor_ranking", side_effect=fake_ranking), patch.object(
            krx, "get_sector_map", return_value=sector_map
        ):
            data = krx.fetch_investor_flow("20260520")

        self.assertEqual(data["flow_limit"], 10)
        self.assertEqual(data["sector_lookup_limit"], 10)
        self.assertEqual(len(data["institution"]), 10)
        self.assertEqual(len(data["foreigner"]), 10)
        self.assertEqual(data["institution_sector_counts"][0], {"sector": "자동차", "count": 7})
        self.assertEqual(data["institution_sector_counts"][1], {"sector": "반도체", "count": 3})
        self.assertEqual(data["foreigner_sector_counts"][0], {"sector": "복합기업", "count": 6})
        self.assertEqual(data["foreigner_sector_counts"][1], {"sector": "기계", "count": 4})


if __name__ == "__main__":
    unittest.main()
