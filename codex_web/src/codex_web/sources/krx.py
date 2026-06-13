import logging
import math
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
import pandas as pd
import requests
from pykrx import stock

from .common import USER_AGENT, TradingDayCalendar, parse_int, parse_number, pct_diff


TOP10_KRX_BLD = "dbms/MDC_OUT/STAT/standard/MDCSTAT02401_OUT"
INVESTOR_CODE_MAP = {"기관합계": "7050", "외국인": "9000"}
OHLCV_CACHE = {}
INDEX_CACHE = {}
MARKET_CACHE = {}


def _post_krx_json(url, headers, data, label, attempts=4):
    last_error = None
    with requests.Session() as session:
        for attempt in range(1, attempts + 1):
            try:
                response = session.post(url, headers=headers, data=data, timeout=8)
                response.raise_for_status()
                text = response.text or ""
                if not text.lstrip().startswith("{"):
                    raise ValueError("KRX returned non-JSON response")
                payload = response.json()
                if "output" not in payload:
                    raise KeyError("KRX output missing")
                return payload
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(0.6 * attempt)
                logging.warning("[KRX] %s retry %s/%s: %s", label, attempt, attempts, exc)
    raise RuntimeError("KRX request failed: %s" % last_error)


def _get_first(row, names, default=""):
    for name in names:
        if name in row and row.get(name) not in (None, ""):
            return row.get(name)
    return default


def fetch_investor_ranking(date_str, investor_name, limit=100):
    investor_code = INVESTOR_CODE_MAP[investor_name]
    url = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCSTAT024&locale=ko_KR&kosdaqGlobalYn=1",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://data.krx.co.kr",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    data = {
        "bld": TOP10_KRX_BLD,
        "locale": "ko_KR",
        "mktId": "ALL",
        "invstTpCd": investor_code,
        "strtDd": date_str,
        "endDd": date_str,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    payload = _post_krx_json(url, headers, data, investor_name)
    records = []
    for row in payload.get("output") or []:
        buy_amount = parse_number(_get_first(row, ["BID_TRDVAL", "BID_TRDVAL_VAL"]))
        if buy_amount <= 0:
            continue
        sell_amount = parse_number(_get_first(row, ["ASK_TRDVAL", "ASK_TRDVAL_VAL"]))
        net_buy = parse_number(_get_first(row, ["NETBID_TRDVAL", "NETBID_TRDVAL_VAL"]))
        trade_amount = parse_number(_get_first(row, ["ACC_TRDVAL", "TRDVAL"]))
        records.append(
            {
                "ticker": _get_first(row, ["ISU_SRT_CD", "ISU_CD"]),
                "name": _get_first(row, ["ISU_NM", "ISU_ABBRV"]),
                "market": _get_first(row, ["MKT_NM", "MKT_ID"]),
                "buy_amount_raw": buy_amount,
                "buy_amount_eok": int(buy_amount / 100_000_000),
                "sell_amount_raw": sell_amount,
                "sell_amount_eok": int(sell_amount / 100_000_000) if sell_amount else 0,
                "net_buy_amount_raw": net_buy,
                "net_buy_amount_eok": int(net_buy / 100_000_000) if net_buy else 0,
                "trade_amount_raw": trade_amount,
                "trade_amount_eok": int(trade_amount / 100_000_000) if trade_amount else 0,
                "buy_volume": parse_int(_get_first(row, ["BID_TRDVOL"])),
                "sell_volume": parse_int(_get_first(row, ["ASK_TRDVOL"])),
            }
        )
    records.sort(key=lambda item: item["buy_amount_raw"], reverse=True)
    for index, item in enumerate(records, start=1):
        item["rank"] = index
    return (records if limit == 0 else records[:limit]), len(records)


def get_naver_sector(ticker):
    url = "https://finance.naver.com/item/main.naver?code=%s" % ticker
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=4)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        tag = soup.select_one('a[href*="type=upjong"]')
        return tag.text.strip() if tag else "기타"
    except Exception:
        return "기타"


def get_sector_map(tickers):
    result = {}
    for ticker in tickers:
        result[ticker] = get_naver_sector(ticker)
        time.sleep(0.08)
    return result


def build_sector_counts(rows):
    counts = {}
    for row in rows or []:
        sector = (row.get("sector") or "기타").strip() or "기타"
        counts[sector] = counts.get(sector, 0) + 1
    return [
        {"sector": sector, "count": count}
        for sector, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def fetch_investor_flow(date_str, limit=10, sector_lookup_limit=10):
    institution, institution_total = fetch_investor_ranking(date_str, "기관합계", limit=limit)
    foreigner, foreigner_total = fetch_investor_ranking(date_str, "외국인", limit=limit)
    sector_tickers = []
    for item in institution[:sector_lookup_limit] + foreigner[:sector_lookup_limit]:
        ticker = item.get("ticker")
        if ticker and ticker not in sector_tickers:
            sector_tickers.append(ticker)
    sector_map = get_sector_map(sector_tickers)
    for item in institution + foreigner:
        if item.get("ticker") in sector_map:
            item["sector"] = sector_map[item["ticker"]]
    return {
        "trade_date": date_str,
        "flow_limit": limit,
        "sector_lookup_limit": sector_lookup_limit,
        "sector_map": sector_map,
        "institution": institution,
        "foreigner": foreigner,
        "institution_sector_counts": build_sector_counts(institution),
        "foreigner_sector_counts": build_sector_counts(foreigner),
        "institution_total_count": institution_total,
        "foreigner_total_count": foreigner_total,
    }


def safe_market_ohlcv(start_str, end_str, ticker, retries=2):
    key = (start_str, end_str, ticker)
    if key in OHLCV_CACHE:
        return OHLCV_CACHE[key]
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            df = stock.get_market_ohlcv(start_str, end_str, ticker)
            if df is not None and not df.empty:
                OHLCV_CACHE[key] = df
                return df
        except Exception as exc:
            last_error = exc
            time.sleep(0.3 * attempt)
    logging.warning("[OHLCV] pykrx failed %s %s~%s: %s", ticker, start_str, end_str, last_error)
    OHLCV_CACHE[key] = pd.DataFrame()
    return OHLCV_CACHE[key]


def get_close_price(ticker, date):
    df = safe_market_ohlcv(date.strftime("%Y%m%d"), date.strftime("%Y%m%d"), ticker)
    if df is None or df.empty:
        return 0
    return int(df.iloc[-1]["종가"])


def get_closest_price(ticker, date):
    end = pd.Timestamp(date)
    start = end - pd.Timedelta(days=5)
    df = safe_market_ohlcv(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker)
    if df is None or df.empty:
        return 0
    return int(df.iloc[-1]["종가"])


def get_max_close_price(ticker, start_date, end_date):
    df = safe_market_ohlcv(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"), ticker)
    if df is None or df.empty:
        return 0
    return int(df["종가"].max())


def average_trade_value(calendar, today_ts, ticker):
    start = calendar.shift_krx_session(today_ts, -4)
    if start is None:
        return None
    df = safe_market_ohlcv(start.strftime("%Y%m%d"), today_ts.strftime("%Y%m%d"), ticker)
    if df is None or df.empty:
        return None
    if "거래대금" in df.columns:
        return float(df["거래대금"].mean())
    return float((df["종가"] * df["거래량"]).mean())


def get_non_halt_shifted_date(calendar, ticker, target_date, trading_days_back):
    lookback = trading_days_back + 20
    while lookback <= trading_days_back + 120:
        start = calendar.shift_krx_session(target_date, -lookback)
        end = calendar.shift_krx_session(target_date, -1)
        if start is None or end is None:
            return None
        df = safe_market_ohlcv(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker)
        if df is None or df.empty or "거래량" not in df.columns:
            return None
        df_desc = df.sort_index(ascending=False)
        non_halt = df_desc[df_desc["거래량"].fillna(0) > 0].index.tolist()
        if len(non_halt) >= trading_days_back:
            return pd.Timestamp(non_halt[trading_days_back - 1])
        lookback += 20
    return None


def get_krx_tick_size(price):
    price = int(price)
    if price < 2000:
        return 1
    if price < 5000:
        return 5
    if price < 20000:
        return 10
    if price < 50000:
        return 50
    if price < 200000:
        return 100
    if price < 500000:
        return 500
    return 1000


def floor_to_tick(price):
    price = int(price)
    if price <= 0:
        return 0
    tick = get_krx_tick_size(price)
    return (price // tick) * tick


def ceil_to_tick(price):
    price = int(price)
    if price <= 0:
        return 0
    tick = get_krx_tick_size(price)
    return ((price + tick - 1) // tick) * tick


def next_tick_price(price):
    price = int(price)
    if price <= 0:
        return 0
    return ceil_to_tick(price + get_krx_tick_size(price))


def prev_tick_price(price):
    price = int(price)
    if price <= 1:
        return 0
    return floor_to_tick(price - 1)


def ceil_tick_ratio(base_price, numerator, denominator):
    raw = (int(base_price) * int(numerator) + int(denominator) - 1) // int(denominator)
    return ceil_to_tick(raw)


def floor_tick_below_ratio(base_price, numerator, denominator):
    raw = (int(base_price) * int(numerator) - 1) // int(denominator)
    return floor_to_tick(raw)


def safe_get_market_ticker_list(date_str, market):
    try:
        return stock.get_market_ticker_list(date_str, market=market)
    except Exception as exc:
        logging.warning("[KRX] ticker list failed market=%s: %s", market, exc)
        return []


def get_ticker_set_for_date(date_ts):
    date_str = pd.Timestamp(date_ts).strftime("%Y%m%d")
    tickers = set()
    for market in ("KOSPI", "KOSDAQ"):
        tickers.update(safe_get_market_ticker_list(date_str, market))
    return tickers


def get_ticker_market(ticker, ref_date):
    ref_ts = pd.Timestamp(ref_date).normalize()
    today_ts = pd.Timestamp.today().normalize()
    if ref_ts > today_ts:
        ref_ts = today_ts
    date_str = ref_ts.strftime("%Y%m%d")
    if MARKET_CACHE.get("date") != date_str:
        MARKET_CACHE.clear()
        MARKET_CACHE.update(
            {
                "date": date_str,
                "KOSPI": set(safe_get_market_ticker_list(date_str, "KOSPI")),
                "KOSDAQ": set(safe_get_market_ticker_list(date_str, "KOSDAQ")),
            }
        )
    if ticker in MARKET_CACHE.get("KOSPI", set()):
        return "KOSPI"
    if ticker in MARKET_CACHE.get("KOSDAQ", set()):
        return "KOSDAQ"
    return "UNKNOWN"


def fetch_index_close_from_naver(index_code, target_date, max_pages=20):
    target_ts = pd.Timestamp(target_date).normalize()
    cache_key = (index_code, target_ts.strftime("%Y%m%d"))
    if cache_key in INDEX_CACHE:
        return INDEX_CACHE[cache_key]

    rows = []
    for page in range(1, max_pages + 1):
        try:
            response = requests.get(
                "https://finance.naver.com/sise/sise_index_day.naver",
                params={"code": index_code, "page": str(page)},
                headers={"User-Agent": USER_AGENT, "Referer": "https://finance.naver.com/sise/"},
                timeout=6,
            )
            response.raise_for_status()
            tables = pd.read_html(response.text)
            if not tables:
                continue
            df = tables[0].dropna().copy()
            if "날짜" not in df.columns or "체결가" not in df.columns:
                continue
            df["날짜"] = pd.to_datetime(df["날짜"], errors="coerce")
            df["체결가"] = pd.to_numeric(df["체결가"].astype(str).str.replace(",", "", regex=False), errors="coerce")
            df = df.dropna(subset=["날짜", "체결가"])
            if df.empty:
                continue
            rows.append(df[["날짜", "체결가"]])
            if df["날짜"].min() <= target_ts:
                break
        except Exception as exc:
            logging.warning("[Index] Naver index fetch failed %s page=%s: %s", index_code, page, exc)
            break

    if not rows:
        INDEX_CACHE[cache_key] = 0.0
        return 0.0
    merged = pd.concat(rows, ignore_index=True).drop_duplicates(subset=["날짜"]).sort_values("날짜")
    exact = merged[merged["날짜"] == target_ts]
    if not exact.empty:
        value = float(exact.iloc[-1]["체결가"])
    else:
        prev = merged[merged["날짜"] <= target_ts]
        value = float(prev.iloc[-1]["체결가"]) if not prev.empty else 0.0
    INDEX_CACHE[cache_key] = value
    return value


def get_market_index_code(ticker, ref_date):
    market = get_ticker_market(ticker, ref_date)
    if market == "KOSPI":
        return "KOSPI"
    if market == "KOSDAQ":
        return "KOSDAQ"
    return ""


def get_index_adjusted_trigger(base_price, base_date, target_date, index_code, multiple, min_numerator, min_denominator):
    base_price = int(base_price)
    if base_price <= 0:
        return 0
    min_trigger = ceil_tick_ratio(base_price, min_numerator, min_denominator)
    if not index_code:
        return min_trigger
    idx_base = fetch_index_close_from_naver(index_code, base_date)
    idx_target = fetch_index_close_from_naver(index_code, target_date)
    if idx_base <= 0 or idx_target <= 0:
        return min_trigger
    idx_rate = (idx_target - idx_base) / idx_base
    if idx_rate <= 0:
        return min_trigger
    idx_trigger = ceil_to_tick(math.ceil(base_price * (1.0 + idx_rate * int(multiple))))
    return max(min_trigger, idx_trigger)


def calculate_release_ceiling(calendar, ticker, check_date):
    date_t5 = calendar.shift_krx_session(check_date, -5)
    date_t15 = calendar.shift_krx_session(check_date, -15)
    start = calendar.shift_krx_session(check_date, -15)
    end = calendar.shift_krx_session(check_date, -1)
    if date_t5 is None or date_t15 is None or start is None or end is None:
        return {"error": "날짜 데이터 부족"}
    p5 = get_close_price(ticker, date_t5)
    p15 = get_close_price(ticker, date_t15)
    max_close = get_max_close_price(ticker, start, end)
    if p5 == 0 or p15 == 0 or max_close == 0:
        return {"error": "가격 정보 없음"}
    c1 = floor_tick_below_ratio(p5, 16, 10)
    c2 = floor_tick_below_ratio(p15, 2, 1)
    c3 = prev_tick_price(max_close)
    return {"release_ceiling": int(min(c1, c2, c3))}


def calculate_warning_trigger_price(p5, p15):
    return min(ceil_tick_ratio(p5, 16, 10), ceil_tick_ratio(p15, 2, 1))


def calculate_designation_trigger(calendar, ticker, target_date):
    date_t5 = get_non_halt_shifted_date(calendar, ticker, target_date, 5)
    date_t15 = get_non_halt_shifted_date(calendar, ticker, target_date, 15)
    if date_t5 is None:
        date_t5 = calendar.shift_krx_session(target_date, -5)
    if date_t15 is None:
        date_t15 = calendar.shift_krx_session(target_date, -15)
    start = calendar.shift_krx_session(target_date, -15)
    end = calendar.shift_krx_session(target_date, -1)
    if date_t5 is None or date_t15 is None or start is None or end is None:
        return {"error": "날짜 부족"}
    p5 = get_close_price(ticker, date_t5)
    p15 = get_close_price(ticker, date_t15)
    max_close = get_max_close_price(ticker, start, end)
    if p5 == 0 or p15 == 0 or max_close == 0:
        return {"error": "가격 정보 없음"}
    index_code = get_market_index_code(ticker, target_date)
    trigger_5d = max(get_index_adjusted_trigger(p5, date_t5, target_date, index_code, 5, 16, 10), ceil_to_tick(max_close))
    trigger_15d = max(get_index_adjusted_trigger(p15, date_t15, target_date, index_code, 3, 2, 1), ceil_to_tick(max_close))
    return {"trigger_price": int(min(trigger_5d, trigger_15d))}


def calculate_redesignation_trigger(calendar, ticker, target_date, dsgn_date, release_date):
    try:
        dsgn_ts = pd.to_datetime(dsgn_date)
        release_ts = pd.to_datetime(release_date)
    except Exception:
        return {"error": "재지정 기준일 오류"}
    date_dsgn_prev = calendar.shift_krx_session(dsgn_ts, -1)
    date_release_prev = calendar.shift_krx_session(release_ts, -1)
    date_t2 = get_non_halt_shifted_date(calendar, ticker, target_date, 2)
    if date_t2 is None:
        date_t2 = calendar.shift_krx_session(target_date, -2)
    if date_dsgn_prev is None or date_release_prev is None or date_t2 is None:
        return {"error": "재지정 날짜 부족"}
    p_dsgn_prev = get_close_price(ticker, date_dsgn_prev)
    p_release_prev = get_close_price(ticker, date_release_prev)
    p2 = get_close_price(ticker, date_t2)
    if p_dsgn_prev == 0 or p_release_prev == 0 or p2 == 0:
        return {"error": "재지정 가격 정보 없음"}
    trigger = max(next_tick_price(p_dsgn_prev), next_tick_price(p_release_prev), ceil_tick_ratio(p2, 14, 10))
    return {"trigger_price": int(trigger)}

def probe_ticker_by_ohlcv(ticker, ref_date_ts):
    start = (pd.Timestamp(ref_date_ts) - pd.Timedelta(days=7)).strftime("%Y%m%d")
    end = pd.Timestamp(ref_date_ts).strftime("%Y%m%d")
    df = safe_market_ohlcv(start, end, ticker, retries=1)
    return df is not None and not df.empty


def resolve_kind_ticker(name, base_code, ticker_set, ref_date_ts=None):
    if base_code in ticker_set:
        return base_code
    if ref_date_ts is not None and len(ticker_set) < 2000 and probe_ticker_by_ohlcv(base_code, ref_date_ts):
        return base_code
    for suffix in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
        candidate = base_code + suffix
        if candidate in ticker_set:
            return candidate
        if ref_date_ts is not None and len(ticker_set) < 2000 and probe_ticker_by_ohlcv(candidate, ref_date_ts):
            return candidate
    logging.debug("[KIND] ticker unresolved %s %s", name, base_code)
    return None


def fetch_kind_data_rows(forward_val, target_date_str, ticker_set, ref_date_ts=None):
    url = "https://kind.krx.co.kr/investwarn/investattentwarnrisky.do"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://kind.krx.co.kr/investwarn/investattentwarnrisky.do?method=investattentwarnriskyMain",
        "X-Requested-With": "XMLHttpRequest",
    }
    if forward_val == "invstwarnisu_sub":
        menu_index, order_mode = "2", "3"
    else:
        menu_index, order_mode = "1", "4"
    data = {
        "method": "investattentwarnriskySub",
        "currentPageSize": "100",
        "pageIndex": "1",
        "orderMode": order_mode,
        "orderStat": "D",
        "forward": forward_val,
        "menuIndex": menu_index,
        "searchFromDate": target_date_str,
        "startDate": target_date_str,
        "endDate": target_date_str,
    }
    response = requests.post(url, headers=headers, data=data, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    for tr in soup.select("tr"):
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue
        name = cells[1].get_text(strip=True)
        match = re.search(r"companysummary_open\(['\"](\d+)['\"]", str(cells[1]))
        base_code = match.group(1) if match else None
        if not base_code:
            continue
        remarks = cells[2].get_text(strip=True) if forward_val == "invstcautnisu_sub" else ""
        dsgn_date = None
        for cell in cells[2:]:
            text = cell.get_text(strip=True)
            if re.match(r"\d{4}-\d{2}-\d{2}", text):
                dsgn_date = text
                break
        dsgn_date = dsgn_date or target_date_str
        code = resolve_kind_ticker(name, base_code, ticker_set, ref_date_ts)
        if code:
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "dsgn_date": pd.to_datetime(dsgn_date),
                    "raw_date_str": dsgn_date,
                    "remarks": remarks,
                }
            )
    return rows


def _read_state(path, next_trading_day, kind):
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split("	")
        if kind == "rewarn" and len(parts) >= 5:
            dsgn_date, release_date, valid_until, name, code = parts[:5]
        elif len(parts) >= 4:
            first_date, valid_until, name, code = parts[:4]
            dsgn_date = first_date
            release_date = first_date
        else:
            continue
        valid_ts = pd.to_datetime(valid_until)
        if next_trading_day > valid_ts:
            continue
        if kind == "rewarn":
            result[code] = {
                "code": code,
                "name": name,
                "dsgn_date": dsgn_date,
                "release_date": release_date,
                "valid_until": valid_ts,
            }
        else:
            result[code] = {"code": code, "name": name, "dsgn_date": dsgn_date, "valid_until": valid_ts}
    return result


def _write_state(path, rows, first_date_key):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in rows:
            handle.write(
                "%s\t%s\t%s\t%s\n"
                % (item[first_date_key], item["valid_until"].strftime("%Y-%m-%d"), item["name"], item["code"])
            )


def _write_rewarn_state(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in rows:
            handle.write(
                "%s\t%s\t%s\t%s\t%s\n"
                % (
                    item.get("dsgn_date", item["release_date"]),
                    item["release_date"],
                    item["valid_until"].strftime("%Y-%m-%d"),
                    item["name"],
                    item["code"],
                )
            )


def _read_warning_history(path):
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split("	")
        if len(parts) >= 3:
            dsgn_date, name, code = parts[:3]
            result[code] = {"name": name, "dsgn_date": dsgn_date}
    return result


def _write_warning_history(path, warning_history, active_warning_codes, rewarn_codes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for code, info in warning_history.items():
            if code in active_warning_codes or code in rewarn_codes:
                handle.write("%s\t%s\t%s\n" % (info["dsgn_date"], info["name"], code))

def analyze_krx_alerts(base_date, state_dir):
    OHLCV_CACHE.clear()
    calendar = TradingDayCalendar()
    today_ts = pd.Timestamp(base_date)
    next_trading_day = calendar.add_krx_trading_days(today_ts, 1)
    if next_trading_day is None:
        raise RuntimeError("다음 거래일 계산 실패")
    next_date_str = next_trading_day.strftime("%Y-%m-%d")
    ticker_set = get_ticker_set_for_date(today_ts)
    cutoff_date = calendar.shift_krx_session(next_trading_day, -10)
    if cutoff_date is None:
        raise RuntimeError("cutoff date calculation failed")

    all_warning = fetch_kind_data_rows("invstwarnisu_sub", next_date_str, ticker_set, today_ts)
    all_warning_codes = {item["code"] for item in all_warning}
    warn_list = [item for item in all_warning if item["dsgn_date"] <= cutoff_date]

    state_dir = Path(state_dir)
    candidate_map = _read_state(state_dir / "krx_caution_candidates.txt", next_trading_day, "candidate")
    rewarn_map = _read_state(state_dir / "krx_rewarn_candidates.txt", next_trading_day, "rewarn")
    warning_history_path = state_dir / "krx_warning_history.txt"
    warning_history = _read_warning_history(warning_history_path)
    for item in all_warning:
        warning_history[item["code"]] = {"name": item["name"], "dsgn_date": item["raw_date_str"]}

    caution_rows = fetch_kind_data_rows("invstcautnisu_sub", next_date_str, ticker_set, today_ts)
    for item in caution_rows:
        remarks = item.get("remarks", "")
        if "투자경고" in remarks and "예고" in remarks:
            valid_until = calendar.add_krx_trading_days(item["dsgn_date"], 10)
            if valid_until is not None:
                candidate_map[item["code"]] = {
                    "code": item["code"],
                    "name": item["name"],
                    "dsgn_date": item["raw_date_str"],
                    "valid_until": valid_until,
                }
        elif "투자경고" in remarks and "해제" in remarks:
            valid_until = calendar.add_krx_trading_days(item["dsgn_date"], 10)
            if valid_until is not None:
                prev_warning = warning_history.get(item["code"], {})
                rewarn_map[item["code"]] = {
                    "code": item["code"],
                    "name": item["name"],
                    "dsgn_date": prev_warning.get("dsgn_date", item["raw_date_str"]),
                    "release_date": item["raw_date_str"],
                    "valid_until": valid_until,
                }

    threshold = 10_000_000_000
    pre_list, valid_candidates = [], []
    for code, info in candidate_map.items():
        if next_trading_day > info["valid_until"] or code in all_warning_codes:
            continue
        avg_val = average_trade_value(calendar, today_ts, code)
        if avg_val is None or avg_val < threshold:
            continue
        item = dict(info)
        item["avg_trade_value_5d"] = avg_val
        pre_list.append(item)
        valid_candidates.append(info)

    redesignation_list, valid_rewarn = [], []
    for code, info in rewarn_map.items():
        if next_trading_day > info["valid_until"] or code in all_warning_codes:
            continue
        avg_val = average_trade_value(calendar, today_ts, code)
        if avg_val is None or avg_val < threshold:
            continue
        item = dict(info)
        item["avg_trade_value_5d"] = avg_val
        redesignation_list.append(item)
        valid_rewarn.append(info)

    _write_state(state_dir / "krx_caution_candidates.txt", valid_candidates, "dsgn_date")
    _write_rewarn_state(state_dir / "krx_rewarn_candidates.txt", valid_rewarn)
    _write_warning_history(warning_history_path, warning_history, all_warning_codes, set(rewarn_map.keys()))

    release, designation, redesignation = [], [], []
    for item in warn_list:
        avg_val = average_trade_value(calendar, today_ts, item["code"])
        if avg_val is None or avg_val < threshold:
            continue
        current = get_closest_price(item["code"], today_ts)
        result = calculate_release_ceiling(calendar, item["code"], next_trading_day)
        if "error" in result or not current:
            continue
        ceiling = int(result["release_ceiling"])
        release.append(
            {
                "code": item["code"],
                "name": item["name"],
                "designation_date": item.get("raw_date_str"),
                "current_price": int(current),
                "release_ceiling": ceiling,
                "diff_pct": pct_diff(ceiling, current),
                "avg_trade_value_5d": avg_val,
            }
        )

    for item in pre_list:
        current = get_closest_price(item["code"], today_ts)
        result = calculate_designation_trigger(calendar, item["code"], next_trading_day)
        if "error" in result or not current:
            continue
        trigger = int(result["trigger_price"])
        diff = pct_diff(trigger, current)
        if diff is not None and diff <= 30:
            designation.append(
                {
                    "code": item["code"],
                    "name": item["name"],
                    "notice_date": item.get("dsgn_date"),
                    "valid_until": item.get("valid_until"),
                    "current_price": int(current),
                    "trigger_price": trigger,
                    "diff_pct": diff,
                    "avg_trade_value_5d": item.get("avg_trade_value_5d", 0),
                }
            )

    for item in redesignation_list:
        current = get_closest_price(item["code"], today_ts)
        result = calculate_redesignation_trigger(
            calendar,
            item["code"],
            next_trading_day,
            item.get("dsgn_date", item.get("release_date")),
            item.get("release_date"),
        )
        if "error" in result or not current:
            continue
        trigger = int(result["trigger_price"])
        diff = pct_diff(trigger, current)
        if diff is not None and diff <= 30:
            redesignation.append(
                {
                    "code": item["code"],
                    "name": item["name"],
                    "release_date": item.get("release_date"),
                    "valid_until": item.get("valid_until"),
                    "current_price": int(current),
                    "trigger_price": trigger,
                    "diff_pct": diff,
                    "avg_trade_value_5d": item.get("avg_trade_value_5d", 0),
                }
            )

    release.sort(key=lambda row: row.get("diff_pct") if row.get("diff_pct") is not None else 999999)
    designation.sort(key=lambda row: row.get("avg_trade_value_5d", 0), reverse=True)
    redesignation.sort(key=lambda row: row.get("diff_pct") if row.get("diff_pct") is not None else 999999)
    return {
        "target_date": next_date_str,
        "source_date": today_ts.strftime("%Y-%m-%d"),
        "avg_trade_value_threshold": threshold,
        "release": release,
        "designation": designation,
        "redesignation": redesignation,
        "diagnostics": {
            "ticker_set_count": len(ticker_set),
            "warning_fetched_count": len(all_warning),
            "warning_old_enough_count": len(warn_list),
            "caution_fetched_count": len(caution_rows),
            "candidate_map_count": len(candidate_map),
            "rewarn_map_count": len(rewarn_map),
        },
    }
