"""Live forward-performance aggregation -- computed ONLY from resolved
PredictionRecord rows (outcome_status == "RESOLVED"). This is deliberately
kept separate from stock_ai/ml/champion.py's historical backtest metrics:
the two answer different questions ("how did the model do on held-out
historical data" vs "how has the model actually done on real predictions
made and later checked against real future prices") and must never be
combined into one number.
"""
from __future__ import annotations

from statistics import mean
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.ml.champion import CHAMPION_HORIZONS
from stock_ai.models.predictions import PredictionRecord
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.services.prediction import load_bundle, model_identity
from stock_ai.services.prediction_history import compute_model_version


def current_model_version(horizon: str) -> str | None:
    """The model_version live-performance should be scoped to for this
    horizon, so a future champion retrain never silently blends old and new
    results under one number. Returns None if no champion is trained yet."""
    try:
        bundle = load_bundle(horizon)
    except FileNotFoundError:
        return None
    return compute_model_version(model_identity(bundle))


def summarize_resolved(records: Iterable[PredictionRecord]) -> dict:
    resolved = [record for record in records if record.outcome_status == "RESOLVED"]
    count = len(resolved)
    if count == 0:
        return {
            "resolved_count": 0,
            "average_absolute_percentage_error": None,
            "within_3pct": None,
            "within_5pct": None,
            "within_10pct": None,
            "regression_direction_match_rate": None,
        }

    abs_pct_errors = [float(r.absolute_percentage_error) for r in resolved if r.absolute_percentage_error is not None]
    direction_matches = [r.regression_direction_match for r in resolved if r.regression_direction_match is not None]

    return {
        "resolved_count": count,
        "average_absolute_percentage_error": mean(abs_pct_errors) if abs_pct_errors else None,
        "within_3pct": _fraction_within(abs_pct_errors, 0.03),
        "within_5pct": _fraction_within(abs_pct_errors, 0.05),
        "within_10pct": _fraction_within(abs_pct_errors, 0.10),
        "regression_direction_match_rate": (sum(1 for m in direction_matches if m) / len(direction_matches)) if direction_matches else None,
    }


def stock_live_performance(db: Session, ticker: str) -> dict:
    normalized = normalize_ticker(ticker)
    horizons = {}
    for horizon in CHAMPION_HORIZONS:
        records = list(
            db.scalars(select(PredictionRecord).where(PredictionRecord.ticker == normalized, PredictionRecord.horizon == horizon))
        )
        horizons[horizon] = summarize_resolved(records)
    return {"ticker": normalized, "horizons": horizons}


def model_live_performance(db: Session) -> dict:
    horizons = {}
    for horizon in CHAMPION_HORIZONS:
        version = current_model_version(horizon)
        if version is None:
            horizons[horizon] = {"status": "NOT_TRAINED"}
            continue
        records = list(
            db.scalars(select(PredictionRecord).where(PredictionRecord.horizon == horizon, PredictionRecord.model_version == version))
        )
        horizons[horizon] = {"model_version": version, **summarize_resolved(records)}
    return {"horizons": horizons}


def _fraction_within(values: list[float], threshold: float) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value <= threshold) / len(values)
