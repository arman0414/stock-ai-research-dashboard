from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from stock_ai.market_calendar import is_trading_day, latest_completed_trading_session, nyse_holidays, previous_trading_day

ET = ZoneInfo("America/New_York")


def test_weekends_are_never_trading_days():
    assert is_trading_day(date(2026, 9, 12)) is False  # Saturday
    assert is_trading_day(date(2026, 9, 13)) is False  # Sunday
    assert is_trading_day(date(2026, 9, 14)) is True  # Monday


@pytest.mark.parametrize(
    "holiday",
    [
        date(2026, 1, 1),  # New Year's Day
        date(2026, 1, 19),  # MLK Day (3rd Monday of Jan 2026)
        date(2026, 2, 16),  # Washington's Birthday (3rd Monday of Feb 2026)
        date(2026, 4, 3),  # Good Friday 2026
        date(2026, 5, 25),  # Memorial Day (last Monday of May 2026)
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),  # Independence Day observed (July 4 2026 is a Saturday)
        date(2026, 9, 7),  # Labor Day (1st Monday of Sep 2026)
        date(2026, 11, 26),  # Thanksgiving (4th Thursday of Nov 2026)
        date(2026, 12, 25),  # Christmas
    ],
)
def test_known_2026_holidays_are_not_trading_days(holiday):
    assert is_trading_day(holiday) is False


def test_ordinary_weekday_is_a_trading_day():
    assert is_trading_day(date(2026, 9, 15)) is True


def test_previous_trading_day_skips_weekends_and_holidays():
    # Labor Day 2026 is Monday Sep 7 -- the previous trading day is Friday Sep 4.
    assert previous_trading_day(date(2026, 9, 7)) == date(2026, 9, 4)  # walking back from the holiday itself
    assert previous_trading_day(date(2026, 9, 14)) == date(2026, 9, 11)  # walking back from Monday skips the weekend


def test_latest_completed_session_after_close_is_todays_session():
    now = datetime(2026, 9, 15, 21, 0, tzinfo=ET)  # 9pm ET, well after 4pm close
    assert latest_completed_trading_session(now) == date(2026, 9, 15)


def test_latest_completed_session_before_close_is_the_prior_session():
    now = datetime(2026, 9, 15, 10, 0, tzinfo=ET)  # 10am ET, market not yet closed
    assert latest_completed_trading_session(now) == date(2026, 9, 14)


def test_latest_completed_session_on_a_weekend_falls_back_to_friday():
    now = datetime(2026, 9, 20, 21, 0, tzinfo=ET)  # Sunday evening
    assert latest_completed_trading_session(now) == date(2026, 9, 18)  # Friday


def test_latest_completed_session_handles_a_non_eastern_local_run_time():
    """A scheduler firing at 21:30 Pacific time is 00:30 ET the NEXT calendar
    day -- this must still resolve to the correct completed ET session, not
    be confused by the Mac's local timezone. This is exactly the real bug
    this phase fixes."""
    now = datetime(2026, 9, 15, 21, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert latest_completed_trading_session(now) == date(2026, 9, 15)


def test_latest_completed_session_requires_timezone_aware_input():
    with pytest.raises(ValueError):
        latest_completed_trading_session(datetime(2026, 9, 15, 21, 0))


def test_nyse_holidays_returns_a_set_for_any_year():
    holidays = nyse_holidays(2027)
    assert isinstance(holidays, set)
    assert len(holidays) == 10
