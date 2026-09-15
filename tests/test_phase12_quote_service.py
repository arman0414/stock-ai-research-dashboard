"""CURRENT PRICE quote service -- entirely presentation-only. These tests
prove: fresh fetches, the TTL cache (open vs. closed market), stale/fallback
behavior on provider failure, batch quotes, partial batch failure, and --
critically -- that none of this ever touches PriceBar or PredictionRecord,
nor creates a new official prediction.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from stock_ai.data.providers.market.base import Quote
from stock_ai.models.market_data import PriceBar
from stock_ai.models.predictions import PredictionRecord
from stock_ai.services.quote_service import (
    CACHED_QUOTE,
    LAST_STORED_PRICE,
    LIVE_QUOTE,
    QUOTE_CACHE_TTL_MARKET_CLOSED_SECONDS,
    QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS,
    UNAVAILABLE,
    QuoteCache,
    get_quote,
    get_quotes,
)


class ProviderErrorLike(Exception):
    pass


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _StubProvider:
    name = "stub"

    def __init__(self, quotes: dict[str, Quote] | Exception | None = None):
        self._quotes = quotes
        self.calls: list[list[str]] = []

    def fetch_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        self.calls.append(list(tickers))
        if isinstance(self._quotes, Exception):
            raise self._quotes
        return dict(self._quotes or {})


def _quote(ticker: str, price: float, market_status: str = "OPEN", ts: datetime | None = None) -> Quote:
    return Quote(ticker=ticker, price=Decimal(str(price)), quote_timestamp=ts or datetime(2026, 9, 15, 14, 48, tzinfo=timezone.utc), market_status=market_status, provider="stub")


def _seed_price_bar(db_session, ticker: str, on: date, close: float) -> None:
    db_session.add(PriceBar(ticker=ticker, date=on, open=close, high=close, low=close, close=close, adjusted_close=close, volume=1000, source="test"))
    db_session.commit()


def test_get_quote_returns_live_quote_from_provider(db_session):
    provider = _StubProvider({"NVDA": _quote("NVDA", 214.30)})
    cache = QuoteCache(clock=_FakeClock())

    result = get_quote(db_session, provider, "nvda", cache=cache)

    assert result.ticker == "NVDA"
    assert result.price == 214.30
    assert result.source == LIVE_QUOTE
    assert result.is_stale is False
    assert result.quote_timestamp == "2026-09-15T14:48:00+00:00"
    assert result.market_status == "OPEN"


def test_repeated_calls_within_ttl_use_the_cache_not_the_provider(db_session):
    clock = _FakeClock()
    provider = _StubProvider({"NVDA": _quote("NVDA", 214.30)})
    cache = QuoteCache(clock=clock)

    get_quote(db_session, provider, "NVDA", cache=cache)
    clock.advance(QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS - 1)
    second = get_quote(db_session, provider, "NVDA", cache=cache)

    assert len(provider.calls) == 1  # provider hit only once
    assert second.source == CACHED_QUOTE
    assert second.price == 214.30


def test_cache_expires_after_ttl_and_refetches(db_session):
    clock = _FakeClock()
    provider = _StubProvider({"NVDA": _quote("NVDA", 214.30)})
    cache = QuoteCache(clock=clock)

    get_quote(db_session, provider, "NVDA", cache=cache)
    clock.advance(QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS + 1)
    provider._quotes = {"NVDA": _quote("NVDA", 215.10)}
    second = get_quote(db_session, provider, "NVDA", cache=cache)

    assert len(provider.calls) == 2
    assert second.source == LIVE_QUOTE
    assert second.price == 215.10


def test_closed_market_quote_uses_a_much_longer_cache_ttl(db_session):
    clock = _FakeClock()
    provider = _StubProvider({"NVDA": _quote("NVDA", 214.30, market_status="CLOSED")})
    cache = QuoteCache(clock=clock)

    get_quote(db_session, provider, "NVDA", cache=cache)
    # Well past the open-market TTL, but well within the closed-market TTL.
    clock.advance(QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS + 30)
    second = get_quote(db_session, provider, "NVDA", cache=cache)

    assert len(provider.calls) == 1
    assert second.source == CACHED_QUOTE
    assert QUOTE_CACHE_TTL_MARKET_CLOSED_SECONDS > QUOTE_CACHE_TTL_MARKET_OPEN_SECONDS


def test_provider_failure_falls_back_to_latest_stored_price_not_zero_or_blank(db_session):
    _seed_price_bar(db_session, "NVDA", date(2026, 9, 14), 213.90)
    provider = _StubProvider(ProviderErrorLike("rate limited"))
    cache = QuoteCache(clock=_FakeClock())

    result = get_quote(db_session, provider, "NVDA", cache=cache)

    assert result.price == 213.90  # never 0, never None when a stored price exists
    assert result.is_stale is True
    assert result.source == LAST_STORED_PRICE


def test_no_stored_price_and_provider_failure_returns_unavailable_not_zero(db_session):
    provider = _StubProvider(ProviderErrorLike("down"))
    cache = QuoteCache(clock=_FakeClock())

    result = get_quote(db_session, provider, "ZZZZ", cache=cache)

    assert result.price is None
    assert result.source == UNAVAILABLE
    assert result.is_stale is True


def test_batch_quotes_return_one_result_per_ticker(db_session):
    provider = _StubProvider({"NVDA": _quote("NVDA", 214.30), "AMD": _quote("AMD", 160.10)})
    cache = QuoteCache(clock=_FakeClock())

    results = get_quotes(db_session, provider, ["NVDA", "AMD"], cache=cache)

    assert set(results) == {"NVDA", "AMD"}
    assert len(provider.calls) == 1  # ONE batched request, not one per ticker
    assert provider.calls[0] == ["NVDA", "AMD"]


def test_partial_batch_failure_does_not_fail_the_whole_batch(db_session):
    _seed_price_bar(db_session, "MU", date(2026, 9, 14), 105.50)
    # The provider only returns NVDA and TSLA -- MU is missing from the
    # response (its own per-symbol failure inside the batch).
    provider = _StubProvider({"NVDA": _quote("NVDA", 214.30), "TSLA": _quote("TSLA", 430.00)})
    cache = QuoteCache(clock=_FakeClock())

    results = get_quotes(db_session, provider, ["NVDA", "MU", "TSLA"], cache=cache)

    assert results["NVDA"].source == LIVE_QUOTE
    assert results["TSLA"].source == LIVE_QUOTE
    assert results["MU"].source == LAST_STORED_PRICE
    assert results["MU"].is_stale is True
    assert results["MU"].price == 105.50


def test_quote_fetch_never_writes_a_price_bar_row(db_session):
    provider = _StubProvider({"NVDA": _quote("NVDA", 214.30)})
    cache = QuoteCache(clock=_FakeClock())

    get_quote(db_session, provider, "NVDA", cache=cache)

    assert list(db_session.scalars(select(PriceBar).where(PriceBar.ticker == "NVDA"))) == []


def test_quote_fetch_never_touches_prediction_records(db_session):
    from stock_ai.services.prediction_history import record_prediction

    signal = {
        "ticker": "NVDA",
        "as_of": "2026-09-15",
        "horizon": "5d",
        "current_price": 210.96,
        "classification": {"direction": "UP", "raw_probability": 0.7, "calibrated_probability": 0.55, "signal_status": "NO_STRONG_SIGNAL", "confidence": "LOW"},
        "regression": {"predicted_return": 0.01, "model_target_price": 213.0, "uncertainty_low": 200.0, "uncertainty_high": 220.0},
        "model": {"classification_version": "random_forest_5d_seed42", "regression_version": "random_forest_raw_5d", "calibration_method": "sigmoid"},
    }
    record_prediction(db_session, signal, prediction_source="LIVE_DAILY")
    before = list(db_session.scalars(select(PredictionRecord)))
    assert len(before) == 1
    frozen_start_price = before[0].current_price

    provider = _StubProvider({"NVDA": _quote("NVDA", 999.99)})  # wildly different "current" price
    cache = QuoteCache(clock=_FakeClock())
    get_quote(db_session, provider, "NVDA", cache=cache)
    get_quote(db_session, provider, "NVDA", cache=cache)

    after = list(db_session.scalars(select(PredictionRecord)))
    assert len(after) == 1  # no new prediction snapshot was created
    assert after[0].current_price == frozen_start_price  # the frozen start price is untouched by the live quote
