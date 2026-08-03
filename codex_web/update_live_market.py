from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_web.sources.live_market import fetch_live_market_data
from codex_web.storage import write_json


if __name__ == "__main__":
    target = ROOT / "docs" / "data" / "live_market.json"
    write_json(target, fetch_live_market_data())
    print(target)
