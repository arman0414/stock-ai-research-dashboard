"""Phase 11: limiting the automated LIVE_DAILY prediction experiment to a
small, independently-configurable DAILY_TRACKING_TICKERS list -- separate
from the user watchlist and the training/reference universe. See
stock_ai/services/daily_cycle.py's module docstring for the three-concepts
design and docs/DAILY_AUTOMATION.md for the operational picture.
"""
from __future__ import annotations

from datetime import date

import pytest

from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.universe import DAILY_TRACKING_TICKERS_DEFAULT, daily_tracking_tickers, parse_ticker_list


def test_daily_tracking_tickers_default_is_the_five_stock_list(monkeypatch):
    monkeypatch.delenv("DAILY_TRACKING_TICKERS", raising=False)
    assert daily_tracking_tickers() == ("NVDA", "AMD", "MU", "TSLA", "IREN")
    assert DAILY_TRACKING_TICKERS_DEFAULT == daily_tracking_tickers()


def test_daily_tracking_tickers_reads_the_env_var(monkeypatch):
    monkeypatch.setenv("DAILY_TRACKING_TICKERS", "NVDA,TSLA,PONY,IREN,RDDT")
    assert daily_tracking_tickers() == ("NVDA", "TSLA", "PONY", "IREN", "RDDT")


def test_daily_tracking_tickers_empty_env_var_falls_back_to_the_default_not_the_watchlist(monkeypatch):
    """An empty string must never silently expand tracking to the full
    watchlist -- it must fall back to the explicit 5-stock default."""
    monkeypatch.setenv("DAILY_TRACKING_TICKERS", "")
    assert daily_tracking_tickers() == DAILY_TRACKING_TICKERS_DEFAULT


def test_parse_ticker_list_normalizes_and_dedupes():
    assert parse_ticker_list("nvda, amd ,nvda,MU", ("X",)) == ("NVDA", "AMD", "MU")


def test_settings_exposes_daily_tracking_tickers(monkeypatch):
    from stock_ai.config import get_settings

    get_settings.cache_clear()
    try:
        monkeypatch.setenv("DAILY_TRACKING_TICKERS", "NVDA,AMD")
        settings = get_settings()
        assert settings.daily_tracking_tickers == ("NVDA", "AMD")
    finally:
        get_settings.cache_clear()


def _resolved_record(db_session, ticker: str, horizon: str = "5d", prediction_source: str = "LIVE_DAILY", model_version: str = "v1", prediction_date=date(2026, 1, 1)):
    from decimal import Decimal

    from stock_ai.models.predictions import PredictionRecord

    record = PredictionRecord(
        ticker=normalize_ticker(ticker),
        horizon=horizon,
        prediction_date=prediction_date,
        model_version=model_version,
        prediction_source=prediction_source,
        current_price=Decimal("100"),
        predicted_class="UP",
        raw_probability=Decimal("0.7"),
        calibrated_probability=Decimal("0.6"),
        signal_status="BULLISH",
        confidence="MEDIUM",
        predicted_return=Decimal("0.05"),
        model_target_price=Decimal("105"),
        uncertainty_low=Decimal("95"),
        uncertainty_high=Decimal("115"),
        classification_version="random_forest_5d_seed42",
        regression_version="random_forest_raw_5d",
        calibration_method="sigmoid",
        outcome_status="RESOLVED",
        actual_future_price=Decimal("104"),
        absolute_prediction_difference_pct=Decimal("1.0"),
        regression_direction_match=True,
    )
    db_session.add(record)
    db_session.commit()
    return record


def test_model_live_performance_excludes_non_tracked_tickers(db_session, monkeypatch):
    from stock_ai.services import prediction_performance

    monkeypatch.setattr(prediction_performance, "daily_tracking_tickers", lambda: ("NVDA",))
    monkeypatch.setattr(prediction_performance, "current_model_version", lambda horizon: "v1" if horizon == "5d" else None)

    _resolved_record(db_session, "NVDA", model_version="v1", prediction_date=date(2026, 1, 1))
    _resolved_record(db_session, "AAPL", model_version="v1", prediction_date=date(2026, 1, 2))  # not tracked

    result = prediction_performance.model_live_performance(db_session)

    assert result["tracked_tickers"] == ["NVDA"]
    assert result["horizons"]["5d"]["resolved_count"] == 1  # AAPL excluded


def test_model_review_status_excludes_non_tracked_tickers(db_session, monkeypatch):
    import stock_ai.services.model_review as model_review_module

    monkeypatch.setattr(model_review_module, "current_model_version", lambda horizon: "v1")
    monkeypatch.setattr(model_review_module, "daily_tracking_tickers", lambda: ("NVDA",))

    _resolved_record(db_session, "NVDA", model_version="v1", prediction_date=date(2026, 1, 1))
    _resolved_record(db_session, "AAPL", model_version="v1", prediction_date=date(2026, 1, 2))  # not tracked

    status = model_review_module.model_review_status(db_session, artifacts_root=None)

    assert status["resolved_new_live_predictions"] == 1
