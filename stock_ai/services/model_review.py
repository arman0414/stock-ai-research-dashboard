"""Model review readiness -- COLLECTS evidence, never retrains or promotes
anything automatically. See docs/DAILY_AUTOMATION.md for the full intended
workflow (candidate training, chronological validation, comparison against
the current champion, manual promotion only).
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.ml.champion import DEFAULT_ARTIFACTS_ROOT, PRIMARY_RESEARCH_HORIZON
from stock_ai.models.predictions import PredictionRecord
from stock_ai.services.prediction_performance import LIVE_PREDICTION_SOURCES, current_model_version

REVIEW_HORIZON = PRIMARY_RESEARCH_HORIZON  # 5d -- the primary research horizon matures fastest
REVIEW_THRESHOLD = 100


def model_review_status(db: Session, artifacts_root: Path | None = None) -> dict:
    """Counts resolved LIVE 5D predictions generated since the current
    champion was trained. Purely informational -- never triggers retraining
    or promotion on its own."""
    root = artifacts_root or DEFAULT_ARTIFACTS_ROOT
    version = current_model_version(REVIEW_HORIZON)
    if version is None:
        return {"horizon": REVIEW_HORIZON, "status": "NOT_TRAINED", "resolved_new_live_predictions": 0, "threshold": REVIEW_THRESHOLD}

    champion_created_at = _champion_created_at(root / REVIEW_HORIZON / "metadata.json")

    query = select(PredictionRecord).where(
        PredictionRecord.horizon == REVIEW_HORIZON,
        PredictionRecord.model_version == version,
        PredictionRecord.outcome_status == "RESOLVED",
        PredictionRecord.prediction_source.in_(LIVE_PREDICTION_SOURCES),
    )
    records = list(db.scalars(query))
    if champion_created_at is not None:
        # Compared in Python (not SQL) since SQLite stores DateTime as text
        # and naive/aware mixing at the SQL layer is unreliable.
        cutoff = _to_naive_utc(champion_created_at)
        records = [record for record in records if record.generated_at is not None and _to_naive_utc(record.generated_at) >= cutoff]

    count = len(records)
    status = "READY_FOR_MODEL_REVIEW" if count >= REVIEW_THRESHOLD else "COLLECTING_DATA"

    return {
        "horizon": REVIEW_HORIZON,
        "model_version": version,
        "resolved_new_live_predictions": count,
        "threshold": REVIEW_THRESHOLD,
        "status": status,
    }


def _champion_created_at(metadata_path: Path):
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text())
        created_at = metadata.get("created_at")
        if not created_at:
            return None
        from datetime import datetime

        return datetime.fromisoformat(created_at)
    except (ValueError, json.JSONDecodeError):
        return None


def _to_naive_utc(value):
    if value.tzinfo is not None:
        from datetime import timezone

        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
