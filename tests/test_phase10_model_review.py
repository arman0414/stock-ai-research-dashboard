from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

import stock_ai.services.model_review as model_review_module
from stock_ai.models.predictions import PredictionRecord
from stock_ai.services.model_review import REVIEW_THRESHOLD, model_review_status


def _record(
    generated_at: datetime,
    model_version: str,
    horizon: str = "5d",
    prediction_source: str = "LIVE_DAILY",
    outcome_status: str = "RESOLVED",
    prediction_date: date = date(2026, 1, 1),
) -> PredictionRecord:
    record = PredictionRecord(
        ticker="NVDA",
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
        outcome_status=outcome_status,
    )
    record.generated_at = generated_at
    return record


def test_status_is_not_trained_when_no_champion_exists(db_session, monkeypatch):
    monkeypatch.setattr(model_review_module, "current_model_version", lambda horizon: None)
    status = model_review_status(db_session)
    assert status["status"] == "NOT_TRAINED"
    assert status["resolved_new_live_predictions"] == 0


def test_status_is_collecting_data_below_threshold(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(model_review_module, "current_model_version", lambda horizon: "v1")
    metadata_dir = tmp_path / "5d"
    metadata_dir.mkdir()
    (metadata_dir / "metadata.json").write_text(json.dumps({"created_at": "2025-01-01T00:00:00+00:00"}))

    for i in range(37):
        db_session.add(_record(generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc), model_version="v1", prediction_date=date(2026, 1, 1) + timedelta(days=i)))
    db_session.commit()

    status = model_review_status(db_session, artifacts_root=tmp_path)
    assert status["resolved_new_live_predictions"] == 37
    assert status["status"] == "COLLECTING_DATA"
    assert status["threshold"] == REVIEW_THRESHOLD


def test_status_is_ready_for_review_at_threshold(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(model_review_module, "current_model_version", lambda horizon: "v1")
    metadata_dir = tmp_path / "5d"
    metadata_dir.mkdir()
    (metadata_dir / "metadata.json").write_text(json.dumps({"created_at": "2025-01-01T00:00:00+00:00"}))

    for i in range(REVIEW_THRESHOLD):
        db_session.add(_record(generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc), model_version="v1", prediction_date=date(2026, 1, 1) + timedelta(days=i)))
    db_session.commit()

    status = model_review_status(db_session, artifacts_root=tmp_path)
    assert status["status"] == "READY_FOR_MODEL_REVIEW"


def test_predictions_generated_before_the_champion_was_trained_do_not_count(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(model_review_module, "current_model_version", lambda horizon: "v1")
    metadata_dir = tmp_path / "5d"
    metadata_dir.mkdir()
    (metadata_dir / "metadata.json").write_text(json.dumps({"created_at": "2026-06-01T00:00:00+00:00"}))

    # All generated BEFORE the champion's created_at -- must not count as "new" evidence.
    for i in range(50):
        db_session.add(_record(generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc), model_version="v1", prediction_date=date(2026, 1, 1) + timedelta(days=i)))
    db_session.commit()

    status = model_review_status(db_session, artifacts_root=tmp_path)
    assert status["resolved_new_live_predictions"] == 0
    assert status["status"] == "COLLECTING_DATA"


def test_only_resolved_live_records_count_not_pending_or_replay(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(model_review_module, "current_model_version", lambda horizon: "v1")
    metadata_dir = tmp_path / "5d"
    metadata_dir.mkdir()
    (metadata_dir / "metadata.json").write_text(json.dumps({"created_at": "2025-01-01T00:00:00+00:00"}))

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(_record(generated_at=now, model_version="v1", outcome_status="PENDING", prediction_date=date(2026, 1, 1)))
    db_session.add(_record(generated_at=now, model_version="v1", prediction_source="BACKFILLED_REPLAY", prediction_date=date(2026, 1, 2)))
    db_session.add(_record(generated_at=now, model_version="v1", horizon="10d", prediction_date=date(2026, 1, 3)))  # wrong horizon -- review is 5D-scoped
    db_session.add(_record(generated_at=now, model_version="v1", prediction_date=date(2026, 1, 4)))  # this one counts
    db_session.commit()

    status = model_review_status(db_session, artifacts_root=tmp_path)
    assert status["resolved_new_live_predictions"] == 1
