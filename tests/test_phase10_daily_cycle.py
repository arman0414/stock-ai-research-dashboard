from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

import stock_ai.services.daily_cycle as daily_cycle
from stock_ai.models.daily_run import DailyRunLog
from stock_ai.models.market_data import PriceBar
from stock_ai.models.predictions import PredictionRecord
from stock_ai.models.watchlist import WatchlistStock
from stock_ai.schemas.stocks import RefreshResult
from stock_ai.services.daily_cycle import run_daily_cycle
from stock_ai.universe import DAILY_TRACKING_TICKERS_DEFAULT


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


def _stub_refresh(db, provider, ticker, years=5, end_date=None, latest_date=date(2026, 1, 5)):
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
    _seed_watchlist(db_session, tracked)
    for ticker in tracked:
        _seed_price_bar(db_session, ticker, date(2026, 1, 5))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert set(result.tracked_tickers) == set(tracked)
    assert result.predictions_attempted == 15
    assert result.predictions_saved == 15
    assert result.status == "SUCCESS"

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
    _seed_watchlist(db_session, ["NVDA", "PONY"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))
    _seed_price_bar(db_session, "PONY", date(2026, 1, 5))

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
    # Deliberately NOT added to the watchlist.
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
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))

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
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))

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
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    first = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)
    second = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert first.predictions_saved == 3
    assert second.predictions_saved == 0
    assert second.duplicates_skipped == 3
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert len(rows) == 3  # never five, never six -- refresh does not multiply predictions


def test_weekend_or_holiday_reuses_last_completed_session_as_of_date(db_session, monkeypatch):
    """No calendar-based weekend detection is needed: as_of always comes from
    the latest stored PriceBar, so a weekend run (no new bar) naturally
    reproduces Friday's as_of date and hits the same uniqueness key --
    zero new predictions, exactly like any other duplicate-day run."""
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 2))  # Friday

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-02"))
    friday_result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    # Saturday: refresh_history finds no new bar, so predict_multi_horizon
    # (driven by the latest stored bar) reports the SAME as_of as Friday.
    saturday_result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert friday_result.predictions_saved == 3
    assert saturday_result.predictions_saved == 0
    assert saturday_result.duplicates_skipped == 3


def test_no_feature_ready_data_creates_no_prediction_and_records_the_reason(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["PONY"])
    _seed_watchlist(db_session, ["PONY"])
    _seed_price_bar(db_session, "PONY", date(2026, 1, 5))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: None)

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.predictions_saved == 0
    assert result.tickers_failed == 1
    assert result.ticker_outcomes[0].error == "no feature-ready price history"
    assert list(db_session.scalars(select(PredictionRecord))) == []


def test_one_ticker_failure_does_not_abort_the_batch(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA", "PONY"])
    _seed_watchlist(db_session, ["NVDA", "PONY"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))
    _seed_price_bar(db_session, "PONY", date(2026, 1, 5))

    def flaky_refresh(db, provider, ticker, years=5, end_date=None):
        if ticker == "PONY":
            raise ValueError("PONY market data unavailable")
        return _stub_refresh(db, provider, ticker, years, end_date)

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", flaky_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.status == "PARTIAL_FAILURE"
    assert result.tickers_failed == 1
    assert result.predictions_saved == 3  # NVDA still succeeded
    nvda_rows = list(db_session.scalars(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA")))
    assert len(nvda_rows) == 3
    pony_error = next(o.error for o in result.ticker_outcomes if o.ticker == "PONY")
    assert "PONY market data unavailable" in pony_error


def test_daily_cycle_resolves_matured_predictions_in_the_same_run(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))
    run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    # Add the 5 future trading rows the 5D prediction needs to resolve.
    for offset in range(1, 6):
        db_session.add(PriceBar(ticker="NVDA", date=date(2026, 1, 5 + offset), open=105, high=105, low=105, close=105, adjusted_close=105, volume=1000, source="test"))
    db_session.commit()

    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-11"))
    second_result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert second_result.outcomes_resolved >= 1
    five_day_row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA", PredictionRecord.horizon == "5d", PredictionRecord.prediction_date == date(2026, 1, 5)))
    assert five_day_row.outcome_status == "RESOLVED"
    assert five_day_row.final_day_date == date(2026, 1, 10)  # the exact 5th future trading row


def test_immature_predictions_remain_pending(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.outcomes_resolved == 0
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert all(row.outcome_status == "PENDING" for row in rows)


def test_daily_cycle_writes_a_daily_run_log_row(db_session, monkeypatch):
    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    log = db_session.scalar(select(DailyRunLog).order_by(DailyRunLog.id.desc()))
    assert log is not None
    assert log.status == "SUCCESS"
    assert log.predictions_saved == 3
    assert log.tickers_processed == 1
    assert log.finished_at is not None


def test_duplicates_remain_idempotent_across_the_full_tracking_list(db_session, monkeypatch):
    tracked = ["NVDA", "AMD", "MU", "TSLA", "IREN"]
    _set_tracking_tickers(monkeypatch, tracked)
    _seed_watchlist(db_session, tracked)
    for ticker in tracked:
        _seed_price_bar(db_session, ticker, date(2026, 1, 5))

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
    _seed_watchlist(db_session, ["NVDA", "PONY"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))
    _seed_price_bar(db_session, "PONY", date(2026, 1, 5))

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


def test_provider_failure_is_logged_without_leaking_into_an_exception(db_session, monkeypatch):
    from stock_ai.data.providers.errors import ProviderError

    _set_tracking_tickers(monkeypatch, ["NVDA"])
    _seed_watchlist(db_session, ["NVDA"])

    def failing_refresh(db, provider, ticker, years=5, end_date=None):
        raise ProviderError("rate limited")

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", failing_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: None)

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.status == "FAILURE"  # the only tracked ticker failed
    assert "rate limited" in result.ticker_outcomes[0].error
