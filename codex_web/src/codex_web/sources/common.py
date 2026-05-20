import datetime as dt
import logging

import exchange_calendars as xcals
import pandas as pd


KST = dt.timezone(dt.timedelta(hours=9), name="KST")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


class TradingDayCalendar:
    _krx_calendar = None
    _nyse_calendar = None

    def __init__(self):
        if TradingDayCalendar._krx_calendar is None:
            TradingDayCalendar._krx_calendar = xcals.get_calendar("XKRX")
        self.krx = TradingDayCalendar._krx_calendar

    @property
    def krx_sessions(self):
        return self.krx.schedule.index

    def _timestamp(self, value):
        return pd.Timestamp(value).normalize()

    def is_krx_trading_day(self, value):
        return self.krx.is_session(self._timestamp(value))

    def _nearest_session(self, value, direction="previous"):
        ts = self._timestamp(value)
        sessions = self.krx_sessions
        if self.krx.is_session(ts):
            return ts
        pos = sessions.searchsorted(ts)
        if direction == "next":
            if pos >= len(sessions):
                return None
            return sessions[pos]
        pos = pos - 1
        if pos < 0:
            return None
        return sessions[pos]

    def add_krx_trading_days(self, value, days):
        session = self._nearest_session(value, direction="next")
        if session is None:
            return None
        sessions = self.krx_sessions
        pos = sessions.searchsorted(session)
        target = pos + days
        if 0 <= target < len(sessions):
            return sessions[target]
        logging.warning("KRX trading-day target out of range: %s %+d", value, days)
        return None

    def shift_krx_session(self, value, shift):
        session = self._nearest_session(value, direction="previous")
        if session is None:
            return None
        sessions = self.krx_sessions
        pos = sessions.searchsorted(session)
        target = pos + shift
        if 0 <= target < len(sessions):
            return sessions[target]
        return None

    @classmethod
    def is_us_session_for_kst_morning(cls, now_kst):
        if cls._nyse_calendar is None:
            cls._nyse_calendar = xcals.get_calendar("XNYS")
        now_ny = now_kst.astimezone(dt.timezone(dt.timedelta(hours=-5)))
        return cls._nyse_calendar.is_session(pd.Timestamp(now_ny.date()))


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


def pct_diff(target, current):
    if not current:
        return None
    return (float(target) - float(current)) / float(current) * 100.0
