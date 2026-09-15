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


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Every test in this file must stay fully offline -- guards against an
    accidental real market-data/news call slipping through a missed mock."""
    monkeypatch.setattr(daily_cycle, "get_market_data_provider", lambda: object())
    monkeypatch.setattr(daily_cycle.price_history, "refresh_price_bars", lambda *a, **k: None)


def test_daily_cycle_creates_5d_10d_15d_snapshots_for_watchlist_only(db_session, monkeypatch):
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.watchlist_size == 1
    assert result.predictions_saved == 3
    assert result.status == "SUCCESS"

    rows = list(db_session.scalars(select(PredictionRecord)))
    assert {row.horizon for row in rows} == {"5d", "10d", "15d"}
    assert all(row.prediction_source == "LIVE_DAILY" for row in rows)
    assert all(row.ticker == "NVDA" for row in rows)


def test_daily_cycle_does_not_process_tickers_outside_the_watchlist(db_session, monkeypatch):
    # Only NVDA is in the watchlist -- AMD must never get a prediction even
    # though it's part of the broader training/reference universe.
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    tickers_with_predictions = {row.ticker for row in db_session.scalars(select(PredictionRecord))}
    assert tickers_with_predictions == {"NVDA"}


def test_running_daily_cycle_twice_on_the_same_market_date_is_idempotent(db_session, monkeypatch):
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


def test_immature_predictions_remain_pending(db_session, monkeypatch):
    _seed_watchlist(db_session, ["NVDA"])
    _seed_price_bar(db_session, "NVDA", date(2026, 1, 5))
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", _stub_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: _fake_multi(ticker, "2026-01-05"))

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.outcomes_resolved == 0
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert all(row.outcome_status == "PENDING" for row in rows)


def test_daily_cycle_writes_a_daily_run_log_row(db_session, monkeypatch):
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


def test_provider_failure_is_logged_without_leaking_into_an_exception(db_session, monkeypatch):
    from stock_ai.data.providers.errors import ProviderError

    _seed_watchlist(db_session, ["NVDA"])

    def failing_refresh(db, provider, ticker, years=5, end_date=None):
        raise ProviderError("rate limited")

    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", failing_refresh)
    monkeypatch.setattr(daily_cycle, "predict_multi_horizon", lambda db, ticker: None)

    result = run_daily_cycle(db_session, run_news=False, request_pacing_seconds=0)

    assert result.status == "FAILURE"  # the only ticker failed
    assert "rate limited" in result.ticker_outcomes[0].error
