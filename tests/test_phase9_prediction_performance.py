from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from stock_ai.models.predictions import PredictionRecord
from stock_ai.services.prediction_history import prediction_record_to_dict
from stock_ai.services.prediction_performance import stock_live_performance, summarize_resolved


def _resolved_record(
    ticker="NVDA",
    horizon="5d",
    abs_pct_error=0.02,
    direction_match=True,
    model_version="v1",
    prediction_date=date(2026, 1, 5),
) -> PredictionRecord:
    return PredictionRecord(
        ticker=ticker,
        horizon=horizon,
        prediction_date=prediction_date,
        model_version=model_version,
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
        actual_future_price=Decimal("103"),
        actual_return=Decimal("0.03"),
        signed_price_error=Decimal("2"),
        absolute_price_error=Decimal("2"),
        absolute_percentage_error=Decimal(str(abs_pct_error)),
        regression_direction_match=direction_match,
        signal_outcome="CORRECT",
    )


def _pending_record(ticker="NVDA", horizon="5d") -> PredictionRecord:
    return PredictionRecord(
        ticker=ticker,
        horizon=horizon,
        prediction_date=date(2026, 1, 6),
        model_version="v1",
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
        outcome_status="PENDING",
    )


def test_summarize_resolved_excludes_pending_predictions() -> None:
    records = [_resolved_record(abs_pct_error=0.02), _pending_record()]
    summary = summarize_resolved(records)
    assert summary["resolved_count"] == 1


def test_summarize_resolved_computes_average_error_and_within_thresholds() -> None:
    records = [
        _resolved_record(abs_pct_error=0.02),  # within 3%, 5%, 10%
        _resolved_record(abs_pct_error=0.04),  # within 5%, 10% only
        _resolved_record(abs_pct_error=0.12),  # none
    ]
    summary = summarize_resolved(records)
    assert summary["resolved_count"] == 3
    assert summary["average_absolute_percentage_error"] == pytest.approx((0.02 + 0.04 + 0.12) / 3)
    assert summary["within_3pct"] == pytest.approx(1 / 3)
    assert summary["within_5pct"] == pytest.approx(2 / 3)
    assert summary["within_10pct"] == pytest.approx(2 / 3)


def test_summarize_resolved_direction_match_rate() -> None:
    records = [_resolved_record(direction_match=True), _resolved_record(direction_match=True), _resolved_record(direction_match=False)]
    summary = summarize_resolved(records)
    assert summary["regression_direction_match_rate"] == pytest.approx(2 / 3)


def test_summarize_resolved_empty_returns_none_fields_not_zero() -> None:
    summary = summarize_resolved([])
    assert summary["resolved_count"] == 0
    assert summary["average_absolute_percentage_error"] is None
    assert summary["within_5pct"] is None
    assert summary["regression_direction_match_rate"] is None


def test_stock_live_performance_groups_by_horizon(db_session) -> None:
    db_session.add(_resolved_record(ticker="NVDA", horizon="5d", abs_pct_error=0.02))
    db_session.add(_resolved_record(ticker="NVDA", horizon="10d", abs_pct_error=0.06, prediction_date=date(2026, 1, 7)))
    db_session.add(_resolved_record(ticker="AMD", horizon="5d", abs_pct_error=0.30, prediction_date=date(2026, 1, 8)))  # different ticker, excluded
    db_session.commit()

    performance = stock_live_performance(db_session, "NVDA")
    assert performance["ticker"] == "NVDA"
    assert performance["horizons"]["5d"]["resolved_count"] == 1
    assert performance["horizons"]["10d"]["resolved_count"] == 1
    assert performance["horizons"]["15d"]["resolved_count"] == 0


def test_prediction_record_to_dict_exposes_model_version_for_advanced_details() -> None:
    record = _resolved_record(model_version="random_forest_5d_seed42__random_forest_raw_5d__sigmoid")
    data = prediction_record_to_dict(record)
    assert data["model_version"] == "random_forest_5d_seed42__random_forest_raw_5d__sigmoid"
    assert data["outcome_status"] == "RESOLVED"
    assert data["signal_outcome"] == "CORRECT"
    assert data["regression_direction_match"] is True
