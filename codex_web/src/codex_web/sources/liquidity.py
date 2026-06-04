import datetime as dt
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .common import USER_AGENT, parse_number


KOFIA_URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
NAVER_INDEX_URL = "https://finance.naver.com/sise/sise_index.naver?code=%s"
NXT_DAILY_PAGE_URL = "https://www.nextrade.co.kr/menu/en/transactionStatusDaily/menuList.do"
NXT_GRID_URL = "https://www.nextrade.co.kr/brdinfoTime/brdinfoTimeList.do"
DISPLAY_ROWS = 30
NXT_GRID_PAGE_UNIT = 1000
MAX_WORKERS = 6
NAVER_INDEX_CODES = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}


def fetch_kofia_dataset(obj_nm, start_str, end_str, field_map, unit_map):
    payload = {
        "dmSearch": {
            "tmpV40": unit_map["tmpV40"],
            "tmpV41": unit_map["tmpV41"],
            "tmpV1": "D",
            "tmpV45": start_str,
            "tmpV46": end_str,
            "OBJ_NM": obj_nm,
        }
    }
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json; charset=UTF-8",
        "Origin": "https://freesis.kofia.or.kr",
        "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do",
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
    }
    response = requests.post(KOFIA_URL, headers=headers, data=json.dumps(payload), timeout=15)
    response.raise_for_status()
    rows = response.json().get("ds1") or []
    if not rows:
        logging.warning("[Liquidity] KOFIA empty obj=%s", obj_nm)
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    result = pd.DataFrame({"Date": pd.to_datetime(df["TMPV1"], format="%Y%m%d")})
    for src, dest in field_map.items():
        result[dest] = pd.to_numeric(df[src], errors="coerce")
    return result


def build_upper_df(df_kospi, df_kosdaq, df_credit):
    if df_kospi.empty or df_kosdaq.empty or df_credit.empty:
        return pd.DataFrame()
    upper = pd.merge(
        df_kospi[["Date", "KOSPI_Trade", "KOSPI_Cap"]],
        df_kosdaq[["Date", "KOSDAQ_Trade", "KOSDAQ_Cap"]],
        on="Date",
        how="inner",
    )
    upper = pd.merge(upper, df_credit, on="Date", how="inner")
    upper = upper.sort_values("Date", ascending=False).head(DISPLAY_ROWS).sort_values("Date")
    upper["Ratio_KOSPI"] = upper["Credit_KOSPI"] / upper["KOSPI_Cap"]
    upper["Ratio_KOSDAQ"] = upper["Credit_KOSDAQ"] / upper["KOSDAQ_Cap"]
    return upper.reset_index(drop=True)


def fetch_nxt_market_trade_value(cookies, date_str, market_id):
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.nextrade.co.kr/menu/en/transactionStatusMain/menuList.do",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    response = requests.post(
        NXT_GRID_URL,
        headers=headers,
        cookies=cookies,
        data={
            "pageIndex": "1",
            "pageUnit": str(NXT_GRID_PAGE_UNIT),
            "scAggDd": date_str,
            "scMktId": market_id,
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("brdinfoTimeList") or []
    raw_total = sum(parse_number(row.get("accTrval"), default=0.0) for row in rows)
    return {
        "trade_value_eok": float(raw_total) / 100_000_000,
        "records": int(parse_number(payload.get("records"), default=0)),
        "set_time": payload.get("setTime") or "",
    }


def fetch_nxt_trade_overlay_df(date_list):
    if not date_list:
        return pd.DataFrame()
    with requests.Session() as session:
        session.get(NXT_DAILY_PAGE_URL, headers={"User-Agent": USER_AGENT}, timeout=10).raise_for_status()
        cookies = session.cookies.get_dict()

    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {}
        for date_str in date_list:
            future_map[executor.submit(fetch_nxt_market_trade_value, cookies, date_str, "STK")] = (date_str, "STK")
            future_map[executor.submit(fetch_nxt_market_trade_value, cookies, date_str, "KSQ")] = (date_str, "KSQ")

        for future in as_completed(future_map):
            date_str, market_id = future_map[future]
            results.setdefault(date_str, {})
            try:
                results[date_str][market_id] = future.result()
            except Exception as exc:
                logging.warning("[Liquidity] NXT overlay failed date=%s market=%s: %s", date_str, market_id, exc)
                results[date_str][market_id] = {"trade_value_eok": 0.0, "records": 0, "set_time": ""}

    rows = []
    for date_str in date_list:
        stk = results.get(date_str, {}).get("STK", {})
        ksq = results.get(date_str, {}).get("KSQ", {})
        rows.append(
            {
                "Date": pd.to_datetime(date_str, format="%Y%m%d"),
                "NXT_KOSPI_Trade": float(stk.get("trade_value_eok", 0.0)),
                "NXT_KOSDAQ_Trade": float(ksq.get("trade_value_eok", 0.0)),
                "NXT_KOSPI_Records": int(stk.get("records", 0)),
                "NXT_KOSDAQ_Records": int(ksq.get("records", 0)),
                "NXT_Set_Time_STK": stk.get("set_time", ""),
                "NXT_Set_Time_KSQ": ksq.get("set_time", ""),
            }
        )
    return pd.DataFrame(rows)


def fetch_naver_index_snapshot(index_code):
    response = requests.get(
        NAVER_INDEX_URL % index_code,
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    response.encoding = "euc-kr"

    import re

    soup = BeautifulSoup(response.text, "html.parser")
    plain = soup.get_text("|", strip=True)
    trade_match = re.search(r"거래대금\(백만\)\|+([0-9,]+)", plain)
    if not trade_match:
        raise ValueError(f"Naver index trade value not found: {index_code}")
    value_tag = soup.select_one("#now_value")
    return {
        "trade_value_eok": parse_number(trade_match.group(1)) / 100.0,
        "close": parse_number(value_tag.get_text(strip=True) if value_tag else None),
    }


def fetch_krx_current_trade_df(base_date):
    base_ts = pd.Timestamp(base_date).normalize()
    today_kst = pd.Timestamp(dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date())
    if base_ts != today_kst:
        return pd.DataFrame()
    kospi = fetch_naver_index_snapshot(NAVER_INDEX_CODES["KOSPI"])
    kosdaq = fetch_naver_index_snapshot(NAVER_INDEX_CODES["KOSDAQ"])
    return pd.DataFrame(
        [
            {
                "Date": base_ts,
                "KOSPI_Trade": float(kospi["trade_value_eok"]),
                "KOSDAQ_Trade": float(kosdaq["trade_value_eok"]),
                "KOSPI_Close": float(kospi.get("close") or 0),
            }
        ]
    )


def build_lower_df(df_kospi, df_kosdaq, df_deposit, nxt_df=None, krx_trade_df=None):
    if df_kospi.empty or df_kosdaq.empty:
        lower = pd.DataFrame(columns=["Date", "KOSPI_Trade", "KOSPI_Close", "KOSDAQ_Trade"])
    else:
        lower = pd.merge(
            df_kospi[["Date", "KOSPI_Trade", "KOSPI_Close"]],
            df_kosdaq[["Date", "KOSDAQ_Trade"]],
            on="Date",
            how="inner",
        )
    if krx_trade_df is not None and not krx_trade_df.empty:
        krx_rows = krx_trade_df[["Date", "KOSPI_Trade", "KOSPI_Close", "KOSDAQ_Trade"]].copy()
        lower = lower[~lower["Date"].isin(krx_rows["Date"])]
        lower = pd.concat([lower, krx_rows], ignore_index=True)
    if not df_deposit.empty:
        lower = pd.merge(lower, df_deposit[["Date", "Deposit_Value"]], on="Date", how="left")
    else:
        lower["Deposit_Value"] = None
    lower = lower.sort_values("Date", ascending=False).head(DISPLAY_ROWS).sort_values("Date")
    if nxt_df is not None and not nxt_df.empty:
        lower = pd.merge(lower, nxt_df, on="Date", how="left")
    for col in ["NXT_KOSPI_Trade", "NXT_KOSDAQ_Trade", "NXT_KOSPI_Records", "NXT_KOSDAQ_Records"]:
        if col not in lower:
            lower[col] = 0
        lower[col] = lower[col].fillna(0)
    for col in ["NXT_Set_Time_STK", "NXT_Set_Time_KSQ"]:
        if col not in lower:
            lower[col] = ""
        lower[col] = lower[col].fillna("")
    lower["KOSPI_Trade_Total"] = lower["KOSPI_Trade"].fillna(0) + lower["NXT_KOSPI_Trade"].fillna(0)
    lower["KOSDAQ_Trade_Total"] = lower["KOSDAQ_Trade"].fillna(0) + lower["NXT_KOSDAQ_Trade"].fillna(0)
    return lower.reset_index(drop=True)


def fetch_liquidity_data(base_date):
    end_dt = dt.datetime.combine(base_date, dt.time(18, 0))
    end_str = end_dt.strftime("%Y%m%d")
    start_str = (end_dt - dt.timedelta(days=90)).strftime("%Y%m%d")
    df_kospi = fetch_kofia_dataset(
        "STATSCU0100000020BO",
        start_str,
        end_str,
        {"TMPV2": "KOSPI_Close", "TMPV4": "KOSPI_Trade", "TMPV5": "KOSPI_Cap"},
        {"tmpV40": "100000000", "tmpV41": "10000"},
    )
    df_kosdaq = fetch_kofia_dataset(
        "STATSCU0100000030BO",
        start_str,
        end_str,
        {"TMPV4": "KOSDAQ_Trade", "TMPV5": "KOSDAQ_Cap"},
        {"tmpV40": "100000000", "tmpV41": "10000"},
    )
    df_deposit = fetch_kofia_dataset(
        "STATSCU0100000060BO",
        start_str,
        end_str,
        {"TMPV2": "Deposit_Value"},
        {"tmpV40": "1000000", "tmpV41": "1"},
    )
    df_credit = fetch_kofia_dataset(
        "STATSCU0100000070BO",
        start_str,
        end_str,
        {"TMPV2": "Credit_Total", "TMPV3": "Credit_KOSPI", "TMPV4": "Credit_KOSDAQ"},
        {"tmpV40": "1000000", "tmpV41": "1"},
    )
    trade_dates = (
        pd.merge(df_kospi[["Date"]], df_kosdaq[["Date"]], on="Date", how="inner")
        .sort_values("Date", ascending=False)
        .head(DISPLAY_ROWS)
        .sort_values("Date")["Date"]
        .tolist()
        if not df_kospi.empty and not df_kosdaq.empty
        else []
    )
    try:
        nxt_df = fetch_nxt_trade_overlay_df([pd.Timestamp(date).strftime("%Y%m%d") for date in trade_dates])
    except Exception as exc:
        logging.warning("[Liquidity] NXT overlay unavailable: %s", exc)
        nxt_df = pd.DataFrame()
    try:
        krx_trade_df = fetch_krx_current_trade_df(base_date)
    except Exception as exc:
        logging.warning("[Liquidity] current KRX trade unavailable: %s", exc)
        krx_trade_df = pd.DataFrame()
    if not krx_trade_df.empty:
        current_trade_dates = [pd.Timestamp(date).strftime("%Y%m%d") for date in krx_trade_df["Date"].tolist()]
        try:
            current_nxt_df = fetch_nxt_trade_overlay_df(current_trade_dates)
            nxt_df = pd.concat([nxt_df, current_nxt_df], ignore_index=True) if not nxt_df.empty else current_nxt_df
        except Exception as exc:
            logging.warning("[Liquidity] current NXT overlay unavailable: %s", exc)
    return {
        "range": {"start": start_str, "end": end_str},
        "upper": build_upper_df(df_kospi, df_kosdaq, df_credit),
        "lower": build_lower_df(df_kospi, df_kosdaq, df_deposit, nxt_df, krx_trade_df),
    }
