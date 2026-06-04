import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_web.sources.liquidity import build_lower_df


class LiquidityTests(unittest.TestCase):
    def test_build_lower_df_appends_current_krx_trade_when_kofia_lags(self):
        df_kospi = pd.DataFrame(
            [
                {"Date": pd.Timestamp("2026-06-01"), "KOSPI_Trade": 1000.0, "KOSPI_Close": 2900.0},
                {"Date": pd.Timestamp("2026-06-02"), "KOSPI_Trade": 1100.0, "KOSPI_Close": 2910.0},
            ]
        )
        df_kosdaq = pd.DataFrame(
            [
                {"Date": pd.Timestamp("2026-06-01"), "KOSDAQ_Trade": 500.0},
                {"Date": pd.Timestamp("2026-06-02"), "KOSDAQ_Trade": 550.0},
            ]
        )
        df_deposit = pd.DataFrame(
            [{"Date": pd.Timestamp("2026-06-02"), "Deposit_Value": 12345.0}]
        )
        nxt_df = pd.DataFrame(
            [
                {
                    "Date": pd.Timestamp("2026-06-04"),
                    "NXT_KOSPI_Trade": 10.0,
                    "NXT_KOSDAQ_Trade": 20.0,
                    "NXT_KOSPI_Records": 100,
                    "NXT_KOSDAQ_Records": 200,
                    "NXT_Set_Time_STK": "20:05:00",
                    "NXT_Set_Time_KSQ": "20:05:00",
                }
            ]
        )
        krx_trade_df = pd.DataFrame(
            [
                {
                    "Date": pd.Timestamp("2026-06-04"),
                    "KOSPI_Trade": 476385.53,
                    "KOSDAQ_Trade": 110543.29,
                    "KOSPI_Close": 8750.0,
                }
            ]
        )

        lower = build_lower_df(df_kospi, df_kosdaq, df_deposit, nxt_df=nxt_df, krx_trade_df=krx_trade_df)

        latest = lower.iloc[-1]
        self.assertEqual(latest["Date"], pd.Timestamp("2026-06-04"))
        self.assertEqual(latest["KOSPI_Trade"], 476385.53)
        self.assertEqual(latest["KOSDAQ_Trade"], 110543.29)
        self.assertEqual(latest["NXT_KOSPI_Trade"], 10.0)
        self.assertEqual(latest["NXT_KOSDAQ_Trade"], 20.0)
        self.assertEqual(latest["KOSPI_Trade_Total"], 476395.53)
        self.assertEqual(latest["KOSDAQ_Trade_Total"], 110563.29)
        self.assertTrue(pd.isna(latest["Deposit_Value"]))


if __name__ == "__main__":
    unittest.main()
