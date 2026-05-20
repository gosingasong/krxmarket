import logging
import re
import datetime as dt
from urllib.parse import urlencode

from bs4 import BeautifulSoup
import pandas as pd
import requests
import yfinance as yf

from .common import USER_AGENT, parse_number


FINVIZ_SCREENER_URL = "https://finviz.com/screener.ashx"
FINVIZ_HEADERS = {"User-Agent": USER_AGENT, "Referer": "https://finviz.com/"}
US_ACTIVE_SCAN_PAGES = 5
BACKUP_TOP = ["AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "AVGO", "LLY"]
FIXED_TICKERS = ["^GSPC", "^IXIC", "^DJI", "IWO", "XBI", "SOXX", "EWY", "CL=F", "KRW=X"]
NAME_MAPPING = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^DJI": "Dow Jones",
    "IWO": "Russell 2k Growth",
    "XBI": "S&P Biotech (XBI)",
    "SOXX": "PHLX Semi (SOXX)",
    "EWY": "MSCI Korea (EWY)",
    "CL=F": "WTI Crude Oil",
    "KRW=X": "USD/KRW",
}


def _fetch_finviz_page(sort_order="-volume", start_row=1):
    params = {"v": "111", "o": sort_order}
    if start_row > 1:
        params["r"] = str(start_row)
    response = requests.get(
        "%s?%s" % (FINVIZ_SCREENER_URL, urlencode(params)),
        headers=FINVIZ_HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    return response.text


def _parse_finviz_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("tr.styled-row"):
        cells = tr.find_all("td")
        if len(cells) < 11:
            continue
        ticker = cells[1].get_text(strip=True).replace(".", "-")
        industry = cells[4].get_text(" ", strip=True)
        price = parse_number(cells[8].get_text(strip=True), default=None)
        volume = parse_number(cells[10].get_text(strip=True), default=None)
        market_cap = cells[6].get_text(strip=True)
        if not ticker or price is None or volume is None:
            continue
        if industry.lower() == "exchange traded fund" or market_cap in ("", "-"):
            continue
        rows.append(
            {
                "Ticker": ticker,
                "Company": cells[2].get_text(" ", strip=True),
                "Industry": industry,
                "Price": float(price),
                "Volume": int(volume),
                "DollarVolume": float(price) * float(volume),
            }
        )
    return rows


def get_us_top_traded_value(limit=11):
    try:
        candidates = []
        for page in range(US_ACTIVE_SCAN_PAGES):
            candidates.extend(_parse_finviz_rows(_fetch_finviz_page(start_row=1 + page * 20)))
        unique = {}
        for row in candidates:
            prev = unique.get(row["Ticker"])
            if prev is None or row["DollarVolume"] > prev["DollarVolume"]:
                unique[row["Ticker"]] = row
        ranked = sorted(unique.values(), key=lambda row: row["DollarVolume"], reverse=True)
        tickers = [row["Ticker"] for row in ranked[:limit]]
        return tickers or BACKUP_TOP[:limit]
    except Exception as exc:
        logging.warning("[US] Finviz scan failed: %s", exc)
        return BACKUP_TOP[:limit]


def _as_date(value):
    if value is None:
        return dt.date.today()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return pd.Timestamp(value).date()


def _target_us_session_date(base_date=None):
    return _as_date(base_date) - dt.timedelta(days=1)


def _history_until_target(stock, target_date):
    start = target_date - dt.timedelta(days=14)
    end = target_date + dt.timedelta(days=1)
    hist = stock.history(start=start.isoformat(), end=end.isoformat())
    if hist is None or hist.empty:
        hist = stock.history(period="5d")
    if hist is None or hist.empty:
        return hist

    session_dates = pd.Series(pd.to_datetime(hist.index).date, index=hist.index)
    filtered = hist[session_dates <= target_date]
    return filtered if not filtered.empty else hist


def _fetch_ticker_row(ticker, is_top=False, target_date=None):
    stock = yf.Ticker(ticker)
    hist = _history_until_target(stock, target_date) if target_date else stock.history(period="5d")
    if hist is None or len(hist) < 2:
        return None
    today = hist.iloc[-1]
    previous = hist.iloc[-2]
    session_date = pd.Timestamp(hist.index[-1]).date().isoformat()
    close = float(today["Close"])
    prev_close = float(previous["Close"])
    open_price = float(today["Open"])
    chg = (close - prev_close) / prev_close * 100 if prev_close else None
    body = (close - open_price) / open_price * 100 if open_price else None
    return {
        "Ticker": ticker,
        "Name": ticker if is_top else NAME_MAPPING.get(ticker, ticker),
        "Chg": chg,
        "Body": body,
        "Open": open_price,
        "High": float(today["High"]),
        "Low": float(today["Low"]),
        "Close": close,
        "Volume": int(today.get("Volume", 0)),
        "MarketDate": session_date,
        "IsTop10": is_top,
        "Status": "OK",
    }


def fetch_us_market_data(base_date=None):
    target_date = _target_us_session_date(base_date)
    fixed = []
    for ticker in FIXED_TICKERS:
        try:
            row = _fetch_ticker_row(ticker, is_top=False, target_date=target_date)
            if row:
                fixed.append(row)
        except Exception as exc:
            logging.warning("[US] fixed ticker failed %s: %s", ticker, exc)

    top = []
    for ticker in get_us_top_traded_value():
        try:
            row = _fetch_ticker_row(ticker, is_top=True, target_date=target_date)
            if row:
                top.append(row)
        except Exception as exc:
            logging.warning("[US] top ticker failed %s: %s", ticker, exc)

    market_date = next((row["MarketDate"] for row in fixed if row["Ticker"] == "^GSPC"), None)
    if market_date is None:
        dates = [row.get("MarketDate") for row in fixed + top if row.get("MarketDate")]
        market_date = max(dates) if dates else target_date.isoformat()

    return {
        "fixed": fixed,
        "top_traded_value": top,
        "target_session_date": target_date.isoformat(),
        "market_date": market_date,
        "note": "US rows use the latest yfinance session on or before the KST base date minus one day; Finviz ranking is the latest available screener order.",
    }
