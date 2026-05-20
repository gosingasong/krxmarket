import datetime as dt
import math

import numpy as np
import pandas as pd


def is_missing(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def json_safe(value):
    if is_missing(value):
        return None

    if isinstance(value, pd.Timestamp):
        if value.time() == dt.time(0, 0):
            return value.date().isoformat()
        return value.isoformat()

    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, np.ndarray):
        return [json_safe(item) for item in value.tolist()]

    if isinstance(value, pd.DataFrame):
        return dataframe_records(value)

    if isinstance(value, pd.Series):
        return {str(key): json_safe(item) for key, item in value.to_dict().items()}

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]

    return value


def dataframe_records(df, add_rank=False):
    if df is None or df.empty:
        return []

    records = []
    safe_df = df.copy()
    for index, row in safe_df.reset_index(drop=True).iterrows():
        item = {str(col): json_safe(row[col]) for col in safe_df.columns}
        if add_rank and "rank" not in item:
            item = {"rank": int(index) + 1, **item}
        records.append(item)
    return records


def parse_number(value, default=0.0):
    if value is None:
        return default
    text = str(value).replace(",", "").replace("%", "").strip()
    if text in ("", "-", "nan", "None"):
        return default
    try:
        return float(text)
    except Exception:
        return default


def parse_int(value, default=0):
    try:
        return int(parse_number(value, default=default))
    except Exception:
        return default
