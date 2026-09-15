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
    abs_diff_pct=2.0,
    direction_match=True,
    model_version="v1",
    prediction_date=date(2026, 1, 5),
    prediction_source="LIVE_DAILY",
) -> PredictionRecord:
    return PredictionRecord(
        ticker=ticker,
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
        actual_future_price=Decimal("103"),
        actual_return=Decimal("0.03"),
        signed_price_error=Decimal("2"),
        absolute_price_error=Decimal("2"),
        absolute_percentage_error=Decimal("0.02"),
        regression_direction_match=direction_match,
        signal_outcome="CORRECT",
        signed_price_difference=Decimal("-2"),
        signed_prediction_difference_pct=Decimal(str(-abs_diff_pct)),
        absolute_prediction_difference_pct=Decimal(str(abs_diff_pct)),
    )


def _pending_record(ticker="NVDA", horizon="5d", prediction_source="LIVE_DAILY") -> PredictionRecord:
    return PredictionRecord(
        ticker=ticker,
        horizon=horizon,
        prediction_date=date(2026, 1, 6),
        model_version="v1",
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
        outcome_status="PENDING",
    )


def test_summarize_resolved_excludes_pending_predictions() -> None:
    records = [_resolved_record(abs_diff_pct=2.0), _pending_record()]
    summary = summarize_resolved(records)
    assert summary["resolved_count"] == 1


def test_summarize_resolved_excludes_backfilled_replay() -> None:
    """The core Phase 10 rule: a BACKFILLED_REPLAY row must never count
    toward live performance, no matter how it got resolved."""
    records = [_resolved_record(abs_diff_pct=1.0, prediction_source="LIVE_DAILY"), _resolved_record(abs_diff_pct=50.0, prediction_source="BACKFILLED_REPLAY")]
    summary = summarize_resolved(records)
    assert summary["resolved_count"] == 1
    assert summary["average_miss_pct"] == pytest.approx(1.0)


def test_summarize_resolved_includes_both_live_sources() -> None:
    records = [_resolved_record(abs_diff_pct=1.0, prediction_source="LIVE_DAILY"), _resolved_record(abs_diff_pct=3.0, prediction_source="MANUAL_LIVE")]
    summary = summarize_resolved(records)
    assert summary["resolved_count"] == 2


def test_summarize_resolved_computes_accuracy_bands_at_2_5_10_percent() -> None:
    records = [
        _resolved_record(abs_diff_pct=1.5),  # within 2%
        _resolved_record(abs_diff_pct=4.0),  # within 5% (not 2%)
        _resolved_record(abs_diff_pct=8.0),  # within 10% (not 5%)
        _resolved_record(abs_diff_pct=15.0),  # more than 10% off
    ]
    summary = summarize_resolved(records)
    assert summary["resolved_count"] == 4
    assert summary["within_2pct"] == pytest.approx(1 / 4)
    assert summary["within_5pct"] == pytest.approx(2 / 4)
    assert summary["within_10pct"] == pytest.approx(3 / 4)
    assert summary["more_than_10pct_off"] == pytest.approx(1 / 4)


def test_summarize_resolved_boundary_values_are_inclusive() -> None:
    records = [_resolved_record(abs_diff_pct=2.0), _resolved_record(abs_diff_pct=5.0), _resolved_record(abs_diff_pct=10.0)]
    summary = summarize_resolved(records)
    assert summary["within_2pct"] == pytest.approx(1 / 3)
    assert summary["within_5pct"] == pytest.approx(2 / 3)
    assert summary["within_10pct"] == pytest.approx(3 / 3)
    assert summary["more_than_10pct_off"] == pytest.approx(0)


def test_summarize_resolved_direction_correct_rate() -> None:
    records = [_resolved_record(direction_match=True), _resolved_record(direction_match=True), _resolved_record(direction_match=False)]
    summary = summarize_resolved(records)
    assert summary["direction_correct_rate"] == pytest.approx(2 / 3)


def test_summarize_resolved_average_miss_pct() -> None:
    records = [_resolved_record(abs_diff_pct=2.0), _resolved_record(abs_diff_pct=4.0), _resolved_record(abs_diff_pct=6.0)]
    summary = summarize_resolved(records)
    assert summary["average_miss_pct"] == pytest.approx(4.0)


def test_summarize_resolved_empty_returns_none_fields_not_zero() -> None:
    summary = summarize_resolved([])
    assert summary["resolved_count"] == 0
    assert summary["average_miss_pct"] is None
    assert summary["within_5pct"] is None
    assert summary["direction_correct_rate"] is None


def test_stock_live_performance_groups_by_horizon(db_session) -> None:
    db_session.add(_resolved_record(ticker="NVDA", horizon="5d", abs_diff_pct=2.0))
    db_session.add(_resolved_record(ticker="NVDA", horizon="10d", abs_diff_pct=6.0, prediction_date=date(2026, 1, 7)))
    db_session.add(_resolved_record(ticker="AMD", horizon="5d", abs_diff_pct=30.0, prediction_date=date(2026, 1, 8)))  # different ticker, excluded
    db_session.commit()

    performance = stock_live_performance(db_session, "NVDA")
    assert performance["ticker"] == "NVDA"
    assert performance["horizons"]["5d"]["resolved_count"] == 1
    assert performance["horizons"]["10d"]["resolved_count"] == 1
    assert performance["horizons"]["15d"]["resolved_count"] == 0


def test_stock_live_performance_excludes_backfilled_replay_at_query_level(db_session) -> None:
    db_session.add(_resolved_record(ticker="NVDA", horizon="5d", abs_diff_pct=2.0, prediction_source="LIVE_DAILY"))
    db_session.add(_resolved_record(ticker="NVDA", horizon="5d", abs_diff_pct=99.0, prediction_source="BACKFILLED_REPLAY", prediction_date=date(2026, 1, 9)))
    db_session.commit()

    performance = stock_live_performance(db_session, "NVDA")
    assert performance["horizons"]["5d"]["resolved_count"] == 1
    assert performance["horizons"]["5d"]["average_miss_pct"] == pytest.approx(2.0)


def test_prediction_record_to_dict_exposes_model_version_and_source_for_advanced_details() -> None:
    record = _resolved_record(model_version="random_forest_5d_seed42__random_forest_raw_5d__sigmoid", prediction_source="LIVE_DAILY")
    data = prediction_record_to_dict(record)
    assert data["model_version"] == "random_forest_5d_seed42__random_forest_raw_5d__sigmoid"
    assert data["prediction_source"] == "LIVE_DAILY"
    assert data["outcome_status"] == "RESOLVED"
    assert data["signal_outcome"] == "CORRECT"
    assert data["regression_direction_match"] is True
    assert data["signed_price_difference"] == pytest.approx(-2.0)
    assert data["absolute_prediction_difference_pct"] == pytest.approx(2.0)
