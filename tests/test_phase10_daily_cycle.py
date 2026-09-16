from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

import stock_ai.services.daily_cycle as daily_cycle
from stock_ai.data.providers.errors import ProviderError
from stock_ai.models.daily_run import DailyRunLog
from stock_ai.models.market_data import PriceBar
from stock_ai.models.predictions import PredictionRecord
from stock_ai.models.watchlist import WatchlistStock
from stock_ai.schemas.stocks import RefreshResult
from stock_ai.services.daily_cycle import run_daily_cycle
from stock_ai.universe import DAILY_TRACKING_TICKERS_DEFAULT

# Every test freezes "the expected completed market session" explicitly
# (see _freeze_expected_session) rather than relying on the real NYSE
# calendar + wall clock, so tests stay deterministic regardless of what day
# they happen to run on. The calendar itself is covered by
# tests/test_market_calendar.py.
DEFAULT_SESSION = date(2026, 1, 5)


def _fake_signal(ticker: str, horizon: str, as_of: str, current_price: float = 100.0, seed_suffix: str = "42") -> dict:
    return {
        "ticker": ticker,
        "as_of": as_of,
        "horizon": horizon,
        "current_price": current_price,
        "classification": {
            "direction": "UP",
            "raw_probability": 0.7,
            "calibrated_probability": 0.55,
            "signal_status": "NO_STRONG_SIGNAL",
            "confidence": "LOW",
        },
        "regression": {
            "predicted_return": 0.02,
            "model_target_price": current_price * 1.02,
            "uncertainty_low": current_price * 0.9,
            "uncertainty_high": current_price * 1.15,
        },
        "model": {
            "classification_version": f"random_forest_{horizon}_seed{seed_suffix}",
            "regression_version": f"random_forest_raw_{horizon}",
            "calibration_method": "sigmoid",
        },
    }


def _fake_multi(ticker: str, as_of: str, current_price: float = 100.0, seed_suffix: str = "42") -> dict:
    return {
        "ticker": ticker,
        "as_of": as_of,
        "current_price": current_price,
        "primary_research_horizon": "5d",
        "predictions": {
            "5d": _fake_signal(ticker, "5d", as_of, current_price, seed_suffix),
            "10d": _fake_signal(ticker, "10d", as_of, current_price, seed_suffix),
            "15d": _fake_signal(ticker, "15d", as_of, current_price, seed_suffix),
        },
    }


def _stub_refresh(db, provider, ticker, years=5, end_date=None, latest_date=DEFAULT_SESSION):
    return RefreshResult(ticker=ticker, source="test", start_date=date(2026, 1, 1), end_date=latest_date, rows_received=1, rows_stored=1, latest_price=100, latest_price_date=latest_date)


def _seed_watchlist(db_session, tickers: list[str]) -> None:
    for ticker in tickers:
        db_session.add(WatchlistStock(ticker=ticker, data_source="test"))
    db_session.commit()


def _seed_price_bar(db_session, ticker: str, on: date) -> None:
    db_session.add(PriceBar(ticker=ticker, date=on, open=100, high=100, low=100, close=100, adjusted_close=100, volume=1000, source="test"))
    db_session.commit()


def _set_tracking_tickers(monkeypatch, tickers: list[str]) -> None:
    """Overrides which tickers the daily LIVE_DAILY experiment tracks --
    decoupled from watchlist seeding, exactly like production where
    DAILY_TRACKING_TICKERS is independent of the watchlist."""
    monkeypatch.setattr(daily_cycle, "daily_tracking_tickers", lambda: tuple(tickers))


def _freeze_expected_session(monkeypatch, session: date = DEFAULT_SESSION) -> None:
    """Pins "the expected completed NYSE session" to a fixed date, decoupled
    from the real calendar/wall clock, so tests control freshness precisely."""
    monkeypatch.setattr(daily_cycle, "latest_completed_trading_session", lambda now: session)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Every test in this file must stay fully offline -- guards against an
    accidental real market-data/news call slipping through a missed mock."""
    monkeypatch.setattr(daily_cycle, "get_market_data_provider", lambda: object())
    monkeypatch.setattr(daily_cycle.price_history, "refresh_price_bars", lambda *a, **k: None)


def test_daily_cycle_processes_exactly_the_configured_tracking_tickers(db_session, monkeypatch):
    """5 tracked tickers x 3 horizons = 15 official snapshots per market day."""
    tracked = ["NVDA", "AMD", "MU", "TSLA", "IREN"]
    _set_tracking_tickers(monkeypatch, tracked)
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, tracked)
    for ticker in tracked:
        _seed_price_bar(db_session, ticker, DEFAULT_SESSION)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert set(result.tracked_tickers) == set(tracked)
    assert result.predictions_attempted == 15
    assert result.predictions_saved == 15
    assert result.status == "SUCCESS"
    assert result.session_complete is True

    rows = list(db_session.scalars(select(PredictionRecord)))
    assert len(rows) == 15
    assert {row.ticker for row in rows} == set(tracked)
    assert {row.horizon for row in rows} == {"5d", "10d", "15d"}
    assert all(row.prediction_source == "LIVE_DAILY" for row in rows)


def test_missing_daily_tracking_tickers_env_uses_five_stock_default(monkeypatch):
    monkeypatch.delenv("DAILY_TRACKING_TICKERS", raising=False)
    assert daily_cycle.daily_tracking_tickers() == DAILY_TRACKING_TICKERS_DEFAULT
    assert DAILY_TRACKING_TICKERS_DEFAULT == ("NVDA", "AMD", "MU", "TSLA", "IREN")


def test_watchlist_can_contain_more_stocks_without_tracking_them(db_session, monkeypatch):
    # PONY is on the watchlist (dashboard-visible) but NOT in the tracking
    # list -- it must never get a LIVE_DAILY prediction.
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA", "PONY"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)
    _seed_price_bar(db_session, "PONY", DEFAULT_SESSION)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert [o.ticker for o in result.ticker_outcomes] == ["NVDA"]
    tickers_with_predictions = {row.ticker for row in db_session.scalars(select(PredictionRecord))}
    assert tickers_with_predictions == {"NVDA"}


def test_tracked_ticker_not_on_watchlist_is_still_processed(db_session, monkeypatch):
    """The tracking list is independent of watchlist membership: a tracked
    ticker with no WatchlistStock row must still get its predictions,
    refreshed the same way a context asset would be."""
    _set_tracking_tickers(monkeypatch, ["PONY"])
    _freeze_expected_session(monkeypatch)
    # Deliberately NOT added to the watchlist. refresh_price_bars (mocked
    # to a no-op by the autouse fixture) is used instead of refresh_history,
    # so we seed the bar directly to represent "the provider already has it".
    _seed_price_bar(db_session, "PONY", DEFAULT_SESSION)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.predictions_saved == 3
    assert result.status == "SUCCESS"
    from stock_ai.services.watchlist import get_stock

    assert get_stock(db_session, "PONY") is None


def test_context_assets_are_not_counted_as_tracked_prediction_stocks(db_session, monkeypatch):
    """SPY/QQQ/sector assets and NVDA's peer basket (AMD, MU, SNDK, SMCI) get
    refreshed for feature calculation but never get their own predictions or
    show up in ticker_outcomes."""
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)

    context_refreshed: list[str] = []

    def _track_context_refresh(db, provider, ticker, years=5, end_date=None):
        context_refreshed.append(ticker)
        return None

    monkeypatch.setattr(daily_cycle.price_history, "refresh_price_bars", _track_context_refresh)
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert [o.ticker for o in result.ticker_outcomes] == ["NVDA"]
    # NVDA's peers and the reference assets were refreshed for context...
    assert "SPY" in context_refreshed
    assert "AMD" in context_refreshed
    # ...but never received a prediction of their own.
    tickers_with_predictions = {row.ticker for row in db_session.scalars(select(PredictionRecord))}
    assert tickers_with_predictions == {"NVDA"}


def test_old_unresolved_predictions_for_untracked_tickers_still_resolve(db_session, monkeypatch):
    """AAPL is no longer in the tracking list, but an older PENDING AAPL
    LIVE_DAILY snapshot must still mature and resolve normally -- and must
    NOT get a new snapshot created."""
    from decimal import Decimal

    from stock_ai.services.prediction_history import record_prediction

    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)

    record_prediction(
        db_session,
        _fake_signal("AAPL", "5d", "2026-01-05", current_price=150.0),
        prediction_source="LIVE_DAILY",
    )
    # 5 future trading sessions so the AAPL 5D prediction is due to resolve.
    for offset in range(1, 6):
        db_session.add(PriceBar(ticker="AAPL", date=date(2026, 1, 5 + offset), open=155, high=155, low=155, close=155, adjusted_close=155, volume=1000, source="test"))
    db_session.commit()

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.outcomes_resolved >= 1
    aapl_rows = list(db_session.scalars(select(PredictionRecord).where(PredictionRecord.ticker == "AAPL")))
    assert len(aapl_rows) == 1  # still exactly one -- no new AAPL snapshot was created
    assert aapl_rows[0].outcome_status == "RESOLVED"
    assert aapl_rows[0].actual_future_price == Decimal("155")


def test_running_daily_cycle_twice_on_the_same_market_date_is_idempotent(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    first = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)
    second = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert first.predictions_saved == 3
    assert second.predictions_saved == 0
    assert second.duplicates_skipped == 3
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert len(rows) == 3  # never five, never six -- refresh does not multiply predictions


def test_no_feature_ready_data_creates_no_prediction_and_records_the_reason(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["PONY"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["PONY"])
    _seed_price_bar(db_session, "PONY", DEFAULT_SESSION)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: None)

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.predictions_saved == 0
    assert result.tickers_failed == 1  # a genuine, non-freshness-related failure
    assert result.ticker_outcomes[0].error == "no feature-ready price history"
    assert list(db_session.scalars(select(PredictionRecord))) == []


def test_one_ticker_transient_failure_does_not_abort_the_batch(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA", "PONY"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA", "PONY"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)
    _seed_price_bar(db_session, "PONY", DEFAULT_SESSION)

    def flaky_refresh(db, provider, ticker, years=5, end_date=None):
        if ticker == "PONY":
            raise ProviderError("PONY market data unavailable")
        return _stub_refresh(db, provider, ticker, years, end_date)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", flaky_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    # A transient provider error is retryable -- WAITING, never a hard
    # FAILURE -- and must never block NVDA from succeeding.
    assert result.status == "WAITING_FOR_MARKET_DATA"
    assert result.tickers_failed == 0
    assert result.tickers_waiting == 1
    assert result.tickers_current == 1
    assert result.predictions_saved == 3  # NVDA still succeeded
    nvda_rows = list(db_session.scalars(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA")))
    assert len(nvda_rows) == 3
    pony_outcome = next(o for o in result.ticker_outcomes if o.ticker == "PONY")
    assert pony_outcome.status == "WAITING"
    assert "PONY market data unavailable" in pony_outcome.error


def test_daily_cycle_resolves_matured_predictions_in_the_same_run(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))
    run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    # Add the 5 future trading rows the 5D prediction needs to resolve.
    for offset in range(1, 6):
        db_session.add(PriceBar(ticker="NVDA", date=date(2026, 1, 5 + offset), open=105, high=105, low=105, close=105, adjusted_close=105, volume=1000, source="test"))
    db_session.commit()

    _freeze_expected_session(monkeypatch, date(2026, 1, 11))
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-11"))
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", lambda db, provider, ticker, years=5, end_date=None: _stub_refresh(db, provider, ticker, years, end_date, latest_date=date(2026, 1, 11)))
    second_result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert second_result.outcomes_resolved >= 1
    five_day_row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA", PredictionRecord.horizon == "5d", PredictionRecord.prediction_date == date(2026, 1, 5)))
    assert five_day_row.outcome_status == "RESOLVED"
    assert five_day_row.final_day_date == date(2026, 1, 10)  # the exact 5th future trading row


def test_immature_predictions_remain_pending(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.outcomes_resolved == 0
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert all(row.outcome_status == "PENDING" for row in rows)


def test_daily_cycle_writes_a_daily_run_log_row(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    log = db_session.scalar(select(DailyRunLog).order_by(DailyRunLog.id.desc()))
    assert log is not None
    assert log.status == "SUCCESS"
    assert log.predictions_saved == 3
    assert log.predictions_attempted == 3
    assert log.tickers_processed == 1
    assert log.tickers_current == 1
    assert log.tickers_waiting == 0
    assert log.expected_market_session == DEFAULT_SESSION
    assert log.finished_at is not None


def test_duplicates_remain_idempotent_across_the_full_tracking_list(db_session, monkeypatch):
    tracked = ["NVDA", "AMD", "MU", "TSLA", "IREN"]
    _set_tracking_tickers(monkeypatch, tracked)
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, tracked)
    for ticker in tracked:
        _seed_price_bar(db_session, ticker, DEFAULT_SESSION)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    first = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)
    second = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert first.predictions_saved == 15
    assert second.predictions_saved == 0
    assert second.duplicates_skipped == 15
    assert len(list(db_session.scalars(select(PredictionRecord)))) == 15


def test_news_refresh_uses_the_current_not_historical_news_provider_for_tracked_tickers_only(db_session, monkeypatch):
    """Routine daily news refresh must use the "current/recent" news
    provider (Yahoo RSS by config) never the historical/backfill provider
    (Alpha Vantage) -- and only for tracked tickers, mirroring price/predict."""
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA", "PONY"])
    _seed_price_bar(db_session, "NVDA", DEFAULT_SESSION)
    _seed_price_bar(db_session, "PONY", DEFAULT_SESSION)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    news_calls: list[tuple] = []

    def _fake_get_news_provider(*args, **kwargs):
        news_calls.append((args, kwargs))
        raise RuntimeError("no real network in tests")  # best-effort: caught and skipped

    monkeypatch.setattr(daily_cycle, "get_news_provider", _fake_get_news_provider)

    run_daily_cycle(db_session, run_news=True, request_pacing_seconds=0)

    # Called exactly once (for NVDA, the only tracked ticker) -- never for
    # PONY (watchlist-only, not tracked), and with no `historical=True` flag.
    assert len(news_calls) == 1
    args, kwargs = news_calls[0]
    assert not args
    assert kwargs.get("historical") is not True


def test_rate_limited_provider_error_is_retryable_not_a_hard_failure(db_session, monkeypatch):
    from stock_ai.data.providers.errors import ProviderError as _ProviderError

    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch)
    _seed_watchlist(db_session, ["NVDA"])

    def failing_refresh(db, provider, ticker, years=5, end_date=None):
        raise _ProviderError("rate limited")

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", failing_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: None)

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.status == "WAITING_FOR_MARKET_DATA"  # retryable, never a hard FAILURE
    assert result.tickers_failed == 0
    assert result.tickers_waiting == 1
    assert "rate limited" in result.ticker_outcomes[0].error


# ---------------------------------------------------------------------------
# Data-freshness gating: the core of this phase. A LIVE_DAILY prediction may
# only be created when a tracked ticker's latest stored PriceBar date is at
# least the expected completed NYSE session -- never fabricated, never a
# calendar-day guess.
# ---------------------------------------------------------------------------


def test_stale_data_blocks_official_prediction_creation(db_session, monkeypatch):
    """Expected session Sep 15, but the latest stored bar is only Sep 14 --
    no official prediction may be created; the ticker is marked WAITING."""
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch, date(2026, 9, 15))
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 9, 14))  # one day behind

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", lambda db, provider, ticker, years=5, end_date=None: _stub_refresh(db, provider, ticker, years, end_date, latest_date=date(2026, 9, 14)))
    predict_called = {"count": 0}

    def _predict(db, ticker):
        predict_called["count"] += 1
        return _fake_multi(ticker, "2026-09-14")

    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", _predict)

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert predict_called["count"] == 0  # never even attempted -- no fabrication risk
    assert result.predictions_saved == 0
    assert result.status == "WAITING_FOR_MARKET_DATA"
    outcome = result.ticker_outcomes[0]
    assert outcome.status == "WAITING"
    assert outcome.latest_data_session == date(2026, 9, 14)
    assert "expected 2026-09-15" in outcome.error
    assert list(db_session.scalars(select(PredictionRecord))) == []


def test_fresh_data_allows_official_prediction_creation(db_session, monkeypatch):
    """Expected session Sep 15, latest stored bar is Sep 15 -- the official
    prediction IS allowed to be created."""
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch, date(2026, 9, 15))
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 9, 15))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", lambda db, provider, ticker, years=5, end_date=None: _stub_refresh(db, provider, ticker, years, end_date, latest_date=date(2026, 9, 15)))
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-09-15"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.predictions_saved == 3
    assert result.status == "SUCCESS"
    outcome = result.ticker_outcomes[0]
    assert outcome.status == "CURRENT"
    assert outcome.latest_data_session == date(2026, 9, 15)
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert {row.prediction_date for row in rows} == {date(2026, 9, 15)}


def test_stale_ticker_does_not_block_a_fresh_ticker(db_session, monkeypatch):
    """NVDA: only Sep 14 data (waiting). AMD: Sep 15 data (eligible). AMD
    must still get its official prediction even though NVDA is stale."""
    _set_tracking_tickers(monkeypatch, ["NVDA", "AMD"])
    _freeze_expected_session(monkeypatch, date(2026, 9, 15))
    _seed_watchlist(db_session, ["NVDA", "AMD"])
    _seed_price_bar(db_session, "NVDA", date(2026, 9, 14))
    _seed_price_bar(db_session, "AMD", date(2026, 9, 15))

    def refresh_by_ticker(db, provider, ticker, years=5, end_date=None):
        latest = date(2026, 9, 14) if ticker == "NVDA" else date(2026, 9, 15)
        return _stub_refresh(db, provider, ticker, years, end_date, latest_date=latest)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", refresh_by_ticker)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-09-15"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    nvda_outcome = next(o for o in result.ticker_outcomes if o.ticker == "NVDA")
    amd_outcome = next(o for o in result.ticker_outcomes if o.ticker == "AMD")
    assert nvda_outcome.status == "WAITING"
    assert amd_outcome.status == "CURRENT"
    assert result.predictions_saved == 3  # AMD's 3 horizons only
    assert result.status == "WAITING_FOR_MARKET_DATA"  # not fully complete
    assert result.session_complete is False

    tickers_with_predictions = {row.ticker for row in db_session.scalars(select(PredictionRecord))}
    assert tickers_with_predictions == {"AMD"}


def test_rate_limited_ticker_retries_successfully_on_a_later_run(db_session, monkeypatch):
    """Run 1: NVDA is rate-limited (WAITING). Run 2 (a later retry, same
    expected session): NVDA succeeds. No duplicate predictions are created
    for tickers that already succeeded."""
    _set_tracking_tickers(monkeypatch, ["NVDA", "AMD"])
    _freeze_expected_session(monkeypatch, date(2026, 9, 15))
    _seed_watchlist(db_session, ["NVDA", "AMD"])
    _seed_price_bar(db_session, "AMD", date(2026, 9, 15))
    # NVDA has no price bar yet -- refresh will attempt to fetch it.

    def rate_limited_refresh(db, provider, ticker, years=5, end_date=None):
        if ticker == "NVDA":
            raise ProviderError("rate limited")
        return _stub_refresh(db, provider, ticker, years, end_date, latest_date=date(2026, 9, 15))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", rate_limited_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-09-15"))

    first = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)
    assert first.status == "WAITING_FOR_MARKET_DATA"
    nvda_first = next(o for o in first.ticker_outcomes if o.ticker == "NVDA")
    assert nvda_first.status == "WAITING"
    assert first.predictions_saved == 3  # AMD succeeded
    assert not first.session_complete

    # Retry: the rate limit has cleared and NVDA's data is now available.
    _seed_price_bar(db_session, "NVDA", date(2026, 9, 15))
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", lambda db, provider, ticker, years=5, end_date=None: _stub_refresh(db, provider, ticker, years, end_date, latest_date=date(2026, 9, 15)))

    second = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    nvda_second = next(o for o in second.ticker_outcomes if o.ticker == "NVDA")
    amd_second = next(o for o in second.ticker_outcomes if o.ticker == "AMD")
    assert nvda_second.status == "CURRENT"
    assert nvda_second.predictions_saved == 3  # NVDA's predictions created for the first time on retry
    assert amd_second.status == "CURRENT"
    assert amd_second.duplicates_skipped == 3  # AMD's already-existing predictions were NOT duplicated
    assert amd_second.predictions_saved == 0
    assert second.status == "SUCCESS"
    assert second.session_complete is True

    rows = list(db_session.scalars(select(PredictionRecord)))
    assert len(rows) == 6  # 3 (AMD, from run 1) + 3 (NVDA, from run 2) -- never more


def test_incomplete_daily_run_remains_retryable(db_session, monkeypatch):
    """A day where not every tracked ticker is CURRENT yet is incomplete --
    but nothing about that state prevents a later run from finishing it."""
    _set_tracking_tickers(monkeypatch, ["NVDA", "AMD"])
    _freeze_expected_session(monkeypatch, date(2026, 9, 15))
    _seed_watchlist(db_session, ["NVDA", "AMD"])
    _seed_price_bar(db_session, "AMD", date(2026, 9, 15))
    _seed_price_bar(db_session, "NVDA", date(2026, 9, 14))  # stale

    monkeypatch.setattr(
        daily_cycle.price_history,
        "refresh_history",
        lambda db, provider, ticker, years=5, end_date=None: _stub_refresh(db, provider, ticker, years, end_date, latest_date=date(2026, 9, 14) if ticker == "NVDA" else date(2026, 9, 15)),
    )
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-09-15"))

    first = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)
    assert first.session_complete is False

    # NVDA's data becomes available; retrying completes the day.
    _seed_price_bar(db_session, "NVDA", date(2026, 9, 15))
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", lambda db, provider, ticker, years=5, end_date=None: _stub_refresh(db, provider, ticker, years, end_date, latest_date=date(2026, 9, 15)))

    second = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)
    assert second.session_complete is True
    assert second.status == "SUCCESS"


def test_daily_status_reports_expected_vs_latest_session(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _freeze_expected_session(monkeypatch, date(2026, 9, 15))
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 9, 14))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", lambda db, provider, ticker, years=5, end_date=None: _stub_refresh(db, provider, ticker, years, end_date, latest_date=date(2026, 9, 14)))
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-09-14"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)
    summary = result.to_summary_dict()

    assert summary["expected_market_session"] == "2026-09-15"
    assert summary["latest_market_date"] == "2026-09-14"
    assert summary["status"] == "WAITING_FOR_MARKET_DATA"
    assert summary["tickers_current"] == 0
    assert summary["tickers_waiting"] == 1
    assert summary["ticker_statuses"][0]["status"] == "WAITING"
    assert summary["ticker_statuses"][0]["latest_data_session"] == "2026-09-14"
