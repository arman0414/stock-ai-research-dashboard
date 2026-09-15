from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd


MARKET_TZ = ZoneInfo("America/New_York")
MARKET_CLOSE = time(16, 0)


def eligible_prediction_date(published_at: datetime, market_close: time = MARKET_CLOSE) -> date:
    """Map an article to the first prediction date allowed to use it.

    Articles published after the regular U.S. market close are assigned to the
    next business day to avoid same-day close leakage.
    """
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    local_time = published_at.astimezone(MARKET_TZ)
    eligible = local_time.date()
    if local_time.time() >= market_close:
        eligible = (pd.Timestamp(eligible) + pd.offsets.BDay(1)).date()
    while pd.Timestamp(eligible).weekday() >= 5:
        eligible = (pd.Timestamp(eligible) + pd.offsets.BDay(1)).date()
    return eligible

