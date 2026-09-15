"""Fresh/latest CURRENT PRICE quotes -- entirely separate from:
  - Daily PriceBar rows (completed historical OHLCV candles used for ML
    features and training). This module never writes a PriceBar.
  - PredictionRecord snapshots (frozen prediction start price). This module
    never reads or writes a PredictionRecord and never triggers a new
    prediction.

This is presentation/live-market functionality only: it exists so the
dashboard, forecast pages, stock detail page, and positions page can show a
fresh current price without needing the user to press Refresh, and without
hammering the market data provider on every render or 60-second poll.

A short in-memory TTL cache (QuoteCache) absorbs repeated requests for the
same ticker within the TTL window. TTL is intentionally longer while the
market is closed, since the official close price cannot change until the
next session.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.data.providers.market.base import MarketDataProvider, Quote
from stock_ai.models.market_data import PriceBar
from stock_ai.schemas.stocks import normalize_ticker

QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS = 60
QUOTE_CACHE_TTL_MARKET_CLOSED_SECONDS = 900  # 15 min -- the official close will not change until the next session

LIVE_QUOTE = "LIVE_QUOTE"
CACHED_QUOTE = "CACHED_QUOTE"
LAST_STORED_PRICE = "LAST_STORED_PRICE"
UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class QuoteResult:
    ticker: str
    price: float | None
    quote_timestamp: str | None  # ISO 8601, UTC
    market_status: str  # "OPEN" | "CLOSED" | "UNKNOWN"
    is_stale: bool
    provider: str | None
    source: str  # LIVE_QUOTE | CACHED_QUOTE | LAST_STORED_PRICE | UNAVAILABLE

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "quote_timestamp": self.quote_timestamp,
            "market_status": self.market_status,
            "is_stale": self.is_stale,
            "provider": self.provider,
            "source": self.source,
        }


class QuoteCache:
    """A small in-memory TTL cache -- never persisted, never shared across
    processes. `clock` is injectable so tests can control cache age without
    real sleeps."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, tuple[QuoteResult, float]] = {}

    def get(self, ticker: str) -> QuoteResult | None:
        entry = self._entries.get(ticker)
        if entry is None:
            return None
        result, cached_at = entry
        ttl = QUOTE_CACHE_TTL_MARKET_CLOSED_SECONDS if result.market_status == "CLOSED" else QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS
        if self._clock() - cached_at > ttl:
            return None
        return result

    def set(self, ticker: str, result: QuoteResult) -> None:
        self._entries[ticker] = (result, self._clock())

    def clear(self) -> None:
        self._entries.clear()


_default_cache = QuoteCache()


def default_cache() -> QuoteCache:
    return _default_cache


def get_quote(db: Session, provider: MarketDataProvider, ticker: str, cache: QuoteCache | None = None) -> QuoteResult:
    normalized = normalize_ticker(ticker)
    return get_quotes(db, provider, [normalized], cache=cache)[normalized]


def get_quotes(db: Session, provider: MarketDataProvider, tickers: list[str], cache: QuoteCache | None = None) -> dict[str, QuoteResult]:
    """Returns exactly one QuoteResult per requested ticker. A provider
    failure -- total or for just one ticker in the batch -- never raises:
    the affected ticker(s) fall back to the latest stored PriceBar with
    is_stale=True rather than breaking the whole batch."""
    active_cache = cache if cache is not None else _default_cache
    normalized = list(dict.fromkeys(normalize_ticker(t) for t in tickers))

    results: dict[str, QuoteResult] = {}
    to_fetch: list[str] = []
    for ticker in normalized:
        cached = active_cache.get(ticker)
        if cached is not None:
            results[ticker] = replace(cached, source=CACHED_QUOTE) if cached.source == LIVE_QUOTE else cached
        else:
            to_fetch.append(ticker)

    if to_fetch:
        fetched: dict[str, Quote] = {}
        fetch_quotes = getattr(provider, "fetch_quotes", None)
        if fetch_quotes is not None:
            try:
                fetched = fetch_quotes(to_fetch) or {}
            except Exception:
                fetched = {}

        for ticker in to_fetch:
            quote = fetched.get(ticker)
            if quote is not None:
                result = QuoteResult(
                    ticker=ticker,
                    price=float(quote.price),
                    quote_timestamp=quote.quote_timestamp.astimezone(timezone.utc).isoformat(),
                    market_status=quote.market_status,
                    is_stale=False,
                    provider=quote.provider,
                    source=LIVE_QUOTE,
                )
                active_cache.set(ticker, result)
            else:
                result = _fallback_to_stored_price(db, ticker, getattr(provider, "name", None))
            results[ticker] = result

    return results


def _fallback_to_stored_price(db: Session, ticker: str, provider_name: str | None) -> QuoteResult:
    bar = db.scalar(select(PriceBar).where(PriceBar.ticker == ticker).order_by(PriceBar.date.desc()).limit(1))
    if bar is None:
        return QuoteResult(ticker=ticker, price=None, quote_timestamp=None, market_status="UNKNOWN", is_stale=True, provider=None, source=UNAVAILABLE)
    return QuoteResult(
        ticker=ticker,
        price=float(bar.close),
        quote_timestamp=datetime(bar.date.year, bar.date.month, bar.date.day, tzinfo=timezone.utc).isoformat(),
        market_status="UNKNOWN",
        is_stale=True,
        provider=provider_name,
        source=LAST_STORED_PRICE,
    )
