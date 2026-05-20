import requests

from .common import USER_AGENT, parse_int


NXT_MARKET_DATA_URL = "https://www.nextrade.co.kr/menu/en/marketData/menuList.do"
NXT_MARKET_REFRESH_URL = "https://www.nextrade.co.kr/menu/refreshMarketData.do"


def fetch_nxt_market_trade_summary(language="eng"):
    page_headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.nextrade.co.kr/en/main.do",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    refresh_headers = {
        "User-Agent": USER_AGENT,
        "Referer": NXT_MARKET_DATA_URL,
        "Origin": "https://www.nextrade.co.kr",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    with requests.Session() as session:
        session.get(NXT_MARKET_DATA_URL, headers=page_headers, timeout=10).raise_for_status()
        response = session.post(
            NXT_MARKET_REFRESH_URL,
            headers=refresh_headers,
            data={"scLanguageSe": language},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()

    if not payload.get("sttus"):
        raise ValueError("NXT refresh status is false")

    total = payload.get("totalVO") or {}
    stk = payload.get("stkVO") or {}
    ksq = payload.get("ksqVO") or {}
    current = payload.get("currentFluc") or {}
    return {
        "source": "nextrade_official_refreshMarketData",
        "language": language,
        "as_of": current.get("allDt") or "",
        "trade_date": total.get("nowDd") or current.get("aggDd") or "",
        "trade_time": total.get("nowTime") or "",
        "market_watch_total_count": parse_int(payload.get("totalCnt")),
        "market_watch_kospi_count": parse_int(payload.get("stkCnt")),
        "market_watch_kosdaq_count": parse_int(payload.get("ksqCnt")),
        "issue_total_count": parse_int(total.get("totalIsuCnt")),
        "issue_kospi_count": parse_int(stk.get("totalIsuCnt")),
        "issue_kosdaq_count": parse_int(ksq.get("totalIsuCnt")),
        "total_trade_volume": parse_int(total.get("totalAccTdQty")),
        "kospi_trade_volume": parse_int(stk.get("totalAccTdQty")),
        "kosdaq_trade_volume": parse_int(ksq.get("totalAccTdQty")),
        "total_trade_value": parse_int(total.get("totalAccTrval")),
        "kospi_trade_value": parse_int(stk.get("totalAccTrval")),
        "kosdaq_trade_value": parse_int(ksq.get("totalAccTrval")),
    }
