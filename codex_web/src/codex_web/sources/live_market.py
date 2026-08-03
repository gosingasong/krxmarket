import datetime as dt
import math

import pandas as pd
import requests
import yfinance as yf

from .common import KST, USER_AGENT


NAVER_REALTIME_ROOT = "https://polling.finance.naver.com/api/realtime/domestic"

YAHOO_QUOTES = [
    {"ticker": "^TNX", "label": "미 10년물 금리", "format": "percent3"},
]

NAVER_QUOTES = [
    {"kind": "index", "ticker": "KOSDAQ", "label": "KOSDAQ", "format": "number2"},
    {"kind": "stock", "ticker": "005930", "label": "삼성전자", "format": "krw0"},
    {"kind": "stock", "ticker": "000660", "label": "SK하이닉스", "format": "krw0"},
]


def _number(value):
    if value is None:
        return None
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _iso_timestamp(value):
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
    except Exception:
        return str(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.isoformat()


def _latest_close(history):
    if history is None or history.empty or "Close" not in history:
        return None, None
    closes = history["Close"].dropna()
    if closes.empty:
        return None, None
    return _number(closes.iloc[-1]), _iso_timestamp(closes.index[-1])


def _previous_close(stock, daily):
    try:
        value = _number(stock.fast_info.get("previous_close"))
        if value is not None:
            return value
    except Exception:
        pass
    if daily is None or daily.empty or "Close" not in daily:
        return None
    closes = daily["Close"].dropna()
    if len(closes) < 2:
        return None
    return _number(closes.iloc[-2])


def fetch_yahoo_quote(spec):
    stock = yf.Ticker(spec["ticker"])
    intraday = stock.history(period="1d", interval="5m", prepost=True)
    daily = stock.history(period="5d", interval="1d")
    price, market_time = _latest_close(intraday)
    if price is None:
        price, market_time = _latest_close(daily)
    if price is None:
        raise RuntimeError("no Yahoo Finance price")
    previous = _previous_close(stock, daily)
    change_pct = (price - previous) / previous * 100 if previous else None
    return {
        **spec,
        "price": price,
        "change_pct": change_pct,
        "market_time": market_time,
        "source": "Yahoo Finance",
        "status": "ok",
    }


def fetch_naver_quote(spec, session=None):
    session = session or requests.Session()
    url = f"{NAVER_REALTIME_ROOT}/{spec['kind']}/{spec['ticker']}"
    response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    rows = response.json().get("datas") or []
    if not rows:
        raise RuntimeError("no Naver Finance price")
    row = rows[0]
    price = _number(row.get("closePriceRaw") or row.get("closePrice"))
    if price is None:
        raise RuntimeError("invalid Naver Finance price")
    return {
        **spec,
        "price": price,
        "change_pct": _number(row.get("fluctuationsRatioRaw") or row.get("fluctuationsRatio")),
        "market_time": row.get("localTradedAt"),
        "market_status": row.get("marketStatus"),
        "source": "Naver Finance",
        "status": "ok",
    }


def fetch_kospi_realized_volatility():
    history = yf.Ticker("^KS11").history(period="3mo", interval="1d")
    if history is None or history.empty or "Close" not in history:
        raise RuntimeError("no KOSPI history")
    closes = history["Close"].dropna()
    volatility = closes.pct_change().rolling(20).std() * math.sqrt(252) * 100
    values = volatility.dropna()
    if values.empty:
        raise RuntimeError("not enough KOSPI history")
    price = _number(values.iloc[-1])
    previous = _number(values.iloc[-2]) if len(values) >= 2 else None
    change_pct = (price - previous) / previous * 100 if price is not None and previous else None
    return {
        "ticker": "^KS11:RV20",
        "label": "KOSPI 변동성*",
        "format": "percent2",
        "price": price,
        "change_pct": change_pct,
        "market_time": _iso_timestamp(closes.index[-1]),
        "source": "Yahoo Finance 계산",
        "status": "ok",
        "note": "VKOSPI 대용 20일 실현변동성",
    }


def _error_item(spec, source, exc):
    return {
        **spec,
        "price": None,
        "change_pct": None,
        "market_time": None,
        "source": source,
        "status": "error",
        "error": str(exc),
    }


def fetch_live_market_data():
    items = []
    for spec in YAHOO_QUOTES:
        try:
            items.append(fetch_yahoo_quote(spec))
        except Exception as exc:
            items.append(_error_item(spec, "Yahoo Finance", exc))

    try:
        items.append(fetch_kospi_realized_volatility())
    except Exception as exc:
        items.append(
            _error_item(
                {"ticker": "^KS11:RV20", "label": "KOSPI 변동성*", "format": "percent2", "note": "VKOSPI 대용 20일 실현변동성"},
                "Yahoo Finance 계산",
                exc,
            )
        )

    with requests.Session() as session:
        for spec in NAVER_QUOTES:
            try:
                items.append(fetch_naver_quote(spec, session=session))
            except Exception as exc:
                items.append(_error_item(spec, "Naver Finance", exc))

    now = dt.datetime.now(KST).isoformat()
    return {
        "schema_version": 1,
        "status": "ok" if any(item["status"] == "ok" for item in items) else "error",
        "generated_at": now,
        "refresh_minutes": 15,
        "items": items,
        "note": "TradingView 미지원 종목의 무료 공개 보조 시세이며 일부 시장은 지연될 수 있습니다. *VKOSPI가 아닌 KOSPI 20일 실현변동성입니다.",
    }
