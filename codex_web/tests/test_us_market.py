import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_web.sources.us_market import _parse_finviz_rows


class UsMarketTests(unittest.TestCase):
    def test_finviz_parser_uses_ticker_metadata_instead_of_logo_initial(self):
        html = """
        <table>
          <tr class="styled-row">
            <td>1</td>
            <td data-boxover-ticker="AAL">
              <a class="company-ticker"><span>A</span></a>
              <a class="tab-link">AAL</a>
            </td>
            <td>American Airlines Group Inc</td>
            <td>Industrials</td>
            <td>Airlines</td>
            <td>USA</td>
            <td>10.34B</td>
            <td>51.03</td>
            <td>15.63</td>
            <td>-0.26%</td>
            <td>181,598,183</td>
          </tr>
        </table>
        """

        rows = _parse_finviz_rows(html)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Ticker"], "AAL")


if __name__ == "__main__":
    unittest.main()
