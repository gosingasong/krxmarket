import datetime as dt
import json
import logging

import pandas as pd
import requests

from .common import USER_AGENT


KOFIA_URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
DISPLAY_ROWS = 30


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


def build_lower_df(df_kospi, df_kosdaq, df_deposit):
    if df_kospi.empty or df_kosdaq.empty:
        return pd.DataFrame()
    lower = pd.merge(
        df_kospi[["Date", "KOSPI_Trade", "KOSPI_Close"]],
        df_kosdaq[["Date", "KOSDAQ_Trade"]],
        on="Date",
        how="inner",
    )
    if not df_deposit.empty:
        lower = pd.merge(lower, df_deposit[["Date", "Deposit_Value"]], on="Date", how="left")
    else:
        lower["Deposit_Value"] = None
    lower = lower.sort_values("Date", ascending=False).head(DISPLAY_ROWS).sort_values("Date")
    lower["KOSPI_Trade_Total"] = lower["KOSPI_Trade"]
    lower["KOSDAQ_Trade_Total"] = lower["KOSDAQ_Trade"]
    lower["NXT_KOSPI_Trade"] = 0.0
    lower["NXT_KOSDAQ_Trade"] = 0.0
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
    return {
        "range": {"start": start_str, "end": end_str},
        "upper": build_upper_df(df_kospi, df_kosdaq, df_credit),
        "lower": build_lower_df(df_kospi, df_kosdaq, df_deposit),
    }
