"""A lightweight, dependency-free NYSE trading-session calendar.

Used ONLY to answer "what is the latest US trading session that has already
fully closed, right now?" -- never to change prediction formulas, targets,
or any ML behavior. This exists so the daily cycle can tell the difference
between "today's session hasn't closed/published yet" (data legitimately
not ready) and "the provider is simply behind" (retryable), rather than
using naive calendar-day arithmetic that would treat weekends/holidays as
regular trading days.

No third-party dependency: NYSE's fixed holiday schedule is small and
well-defined, and is computed algorithmically per year (including the
weekend-observed shift) rather than hardcoded to a list of known years.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MARKET_TIMEZONE = ZoneInfo("America/New_York")
MARKET_CLOSE_TIME = time(16, 0)


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """weekday: Monday=0 ... Sunday=6. n is 1-indexed (1st, 2nd, 3rd...)."""
    first_of_month = date(year, month, 1)
    offset = (weekday - first_of_month.weekday()) % 7
    return first_of_month + timedelta(days=offset + 7 * (n - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        first_of_next_month = date(year + 1, 1, 1)
    else:
        first_of_next_month = date(year, month + 1, 1)
    last_of_month = first_of_next_month - timedelta(days=1)
    offset = (last_of_month.weekday() - weekday) % 7
    return last_of_month - timedelta(days=offset)


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed(holiday: date) -> date:
    """NYSE observes a holiday that falls on Saturday the preceding Friday,
    and one that falls on Sunday the following Monday."""
    if holiday.weekday() == 5:  # Saturday
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:  # Sunday
        return holiday + timedelta(days=1)
    return holiday


def nyse_holidays(year: int) -> set[date]:
    holidays = {
        _observed(date(year, 1, 1)),  # New Year's Day
        _nth_weekday_of_month(year, 1, 0, 3),  # Martin Luther King Jr. Day -- 3rd Monday of January
        _nth_weekday_of_month(year, 2, 0, 3),  # Washington's Birthday -- 3rd Monday of February
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday_of_month(year, 5, 0),  # Memorial Day -- last Monday of May
        _observed(date(year, 6, 19)),  # Juneteenth
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday_of_month(year, 9, 0, 1),  # Labor Day -- 1st Monday of September
        _nth_weekday_of_month(year, 11, 3, 4),  # Thanksgiving -- 4th Thursday of November
        _observed(date(year, 12, 25)),  # Christmas
    }
    return holidays


def is_trading_day(day: date) -> bool:
    if day.weekday() >= 5:  # Saturday/Sunday
        return False
    return day not in nyse_holidays(day.year)


def previous_trading_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def latest_completed_trading_session(now: datetime) -> date:
    """The most recent NYSE trading session that has fully closed as of
    `now` (must be timezone-aware; converted internally to US/Eastern).

    If `now` falls on a trading day AFTER the close, that day's session is
    the latest completed one. Otherwise (before close, or on a
    weekend/holiday), walks back to the most recent prior trading day.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    eastern_now = now.astimezone(MARKET_TIMEZONE)
    today = eastern_now.date()

    if is_trading_day(today) and eastern_now.time() >= MARKET_CLOSE_TIME:
        return today
    return previous_trading_day(today)
