"""Fresh/latest CURRENT PRICE quotes -- entirely separate from:
  - Daily PriceBar rows (completed historical OHLCV candles used for ML
    features and training). This module never writes a PriceBar.
  - PredictionRecord snapshots (frozen prediction start price / Final Day
    Price). This module never reads or writes a PredictionRecord and never
    triggers a new prediction.

This is presentation/live-market functionality only: it exists so the
dashboard, forecast pages, stock detail page, and positions page can show a
fresh current price without needing the user to press Refresh, and without
hammering the market data provider on every render or 60-second poll.

Two layers of caching, for two different lifetimes:
  - QuoteCache: a short in-memory TTL cache (this process only, lost on
    restart). TTL is longer while the market is closed, since the official
    close price cannot change until the next session.
  - LatestQuote (stock_ai.models.latest_quote): ONE persisted row per
    ticker, holding the last quote that genuinely succeeded. This survives
    a page reload, a browser close, and a backend restart -- it exists so
    the dashboard can show a real last-known price instantly instead of an
    empty/blank state while a fresh provider call is (or isn't yet) in
    flight. A failed provider call NEVER writes here; it only ever holds a
    once-genuinely-successful value. We deliberately keep only the single
    latest row per ticker (no intraday history) -- see the model docstring.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.data.providers.market.base import MarketDataProvider, Quote
from stock_ai.models.latest_quote import LatestQuote
from stock_ai.models.market_data import PriceBar
from stock_ai.schemas.stocks import normalize_ticker

QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS = 60
QUOTE_CACHE_TTL_MARKET_CLOSED_SECONDS = 900  # 15 min -- the official close will not change until the next session

LIVE_QUOTE = "LIVE_QUOTE"
CACHED_QUOTE = "CACHED_QUOTE"
PERSISTED_QUOTE = "PERSISTED_QUOTE"
LAST_STORED_PRICE = "LAST_STORED_PRICE"
UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class QuoteResult:
    ticker: str
    price: float | None
    quote_timestamp: str | None  # ISO 8601, UTC -- the PROVIDER's own reported time for this price
    market_status: str  # "OPEN" | "CLOSED" | "UNKNOWN"
    is_stale: bool
    provider: str | None
    source: str  # LIVE_QUOTE | CACHED_QUOTE | PERSISTED_QUOTE | LAST_STORED_PRICE | UNAVAILABLE
    saved_at: str | None = None  # ISO 8601, UTC -- when WE last confirmed this value with the provider

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "quote_timestamp": self.quote_timestamp,
            "market_status": self.market_status,
            "is_stale": self.is_stale,
            "provider": self.provider,
            "source": self.source,
            "saved_at": self.saved_at,
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


def get_quote(db: Session, provider: MarketDataProvider, ticker: str, cache: QuoteCache | None = None, now: datetime | None = None) -> QuoteResult:
    normalized = normalize_ticker(ticker)
    return get_quotes(db, provider, [normalized], cache=cache, now=now)[normalized]


def get_quotes(db: Session, provider: MarketDataProvider, tickers: list[str], cache: QuoteCache | None = None, now: datetime | None = None) -> dict[str, QuoteResult]:
    """Returns exactly one QuoteResult per requested ticker. A provider
    failure -- total or for just one ticker in the batch -- never raises and
    never blanks/zeros the price: the affected ticker(s) fall back to the
    persisted LatestQuote (if one exists) and only then to the latest stored
    PriceBar, both marked is_stale=True.

    Lookup order per ticker:
      1. In-memory cache (this process, fastest, no I/O).
      2. Persisted LatestQuote, if saved recently enough to still be within
         the same freshness window the in-memory cache would use -- this is
         what makes a quote "instantly available" again right after a
         backend restart, without waiting on the provider.
      3. A live provider fetch -- persisted to LatestQuote on success.
      4. The persisted LatestQuote regardless of age (provider failed).
      5. The latest stored PriceBar close (provider failed, nothing ever
         persisted for this ticker).
      6. UNAVAILABLE (nothing at all is known for this ticker).
    """
    active_cache = cache if cache is not None else _default_cache
    current_time = now or datetime.now(timezone.utc)
    normalized = list(dict.fromkeys(normalize_ticker(t) for t in tickers))

    results: dict[str, QuoteResult] = {}
    to_fetch: list[str] = []
    for ticker in normalized:
        cached = active_cache.get(ticker)
        if cached is not None:
            results[ticker] = replace(cached, source=CACHED_QUOTE) if cached.source == LIVE_QUOTE else cached
            continue

        persisted = _get_persisted_quote(db, ticker)
        if persisted is not None and _is_within_ttl(persisted.saved_at, persisted.market_status, current_time):
            # Fresh enough to skip the provider entirely -- functionally
            # identical to an in-memory cache hit, just one that happens to
            # have survived a process restart.
            result = _persisted_to_result(persisted, source=CACHED_QUOTE, is_stale=False)
            active_cache.set(ticker, result)
            results[ticker] = result
            continue

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
                    saved_at=current_time.isoformat(),
                )
                active_cache.set(ticker, result)
                _save_latest_quote(db, quote, saved_at=current_time)
            else:
                persisted = _get_persisted_quote(db, ticker)
                if persisted is not None:
                    result = _persisted_to_result(persisted, source=PERSISTED_QUOTE, is_stale=True)
                else:
                    result = _fallback_to_stored_price(db, ticker, getattr(provider, "name", None))
            results[ticker] = result

    return results


def _get_persisted_quote(db: Session, ticker: str) -> LatestQuote | None:
    return db.scalar(select(LatestQuote).where(LatestQuote.ticker == ticker))


def _save_latest_quote(db: Session, quote: Quote, saved_at: datetime) -> None:
    """UPSERTs the one LatestQuote row for this ticker. Only ever called
    with a genuine successful Quote from the provider -- never with a null
    price, a zero, or an error value, and never for a failed fetch."""
    existing = _get_persisted_quote(db, quote.ticker)
    if existing is None:
        existing = LatestQuote(ticker=quote.ticker)
        db.add(existing)
    existing.price = quote.price
    existing.quote_timestamp = quote.quote_timestamp
    existing.saved_at = saved_at
    existing.market_status = quote.market_status
    existing.provider = quote.provider
    existing.is_stale = False
    db.commit()


def _is_within_ttl(saved_at: datetime, market_status: str, now: datetime) -> bool:
    ttl = QUOTE_CACHE_TTL_MARKET_CLOSED_SECONDS if market_status == "CLOSED" else QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS
    reference = saved_at if saved_at.tzinfo is not None else saved_at.replace(tzinfo=timezone.utc)
    return (now - reference).total_seconds() <= ttl


def _persisted_to_result(row: LatestQuote, source: str, is_stale: bool) -> QuoteResult:
    quote_timestamp = row.quote_timestamp if row.quote_timestamp.tzinfo is not None else row.quote_timestamp.replace(tzinfo=timezone.utc)
    saved_at = row.saved_at if row.saved_at.tzinfo is not None else row.saved_at.replace(tzinfo=timezone.utc)
    return QuoteResult(
        ticker=row.ticker,
        price=float(row.price),
        quote_timestamp=quote_timestamp.astimezone(timezone.utc).isoformat(),
        market_status=row.market_status,
        is_stale=is_stale,
        provider=row.provider,
        source=source,
        saved_at=saved_at.astimezone(timezone.utc).isoformat(),
    )


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
