from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class DailyPrice:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: int


@dataclass(frozen=True)
class Quote:
    """A fresh/latest market quote -- distinct from a completed DailyPrice
    bar. Never used to construct or backfill a PriceBar row."""

    ticker: str
    price: Decimal
    quote_timestamp: datetime  # timezone-aware, UTC
    market_status: str  # "OPEN" | "CLOSED" | "UNKNOWN"
    provider: str


class MarketDataProvider(Protocol):
    name: str

    def fetch_daily_history(self, ticker: str, start_date: date, end_date: date) -> list[DailyPrice]:
        """Return daily bars ordered oldest to newest."""

    def fetch_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        """Best-effort batch fetch of fresh quotes. Implementations may omit
        any ticker they could not fetch rather than raising -- callers must
        treat a missing key as "unavailable right now," not an error. Not
        every provider supports this; the quote service falls back to the
        latest stored PriceBar when it doesn't."""

