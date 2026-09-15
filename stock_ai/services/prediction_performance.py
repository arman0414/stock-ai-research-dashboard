"""Live forward-performance aggregation -- computed ONLY from resolved,
non-replay PredictionRecord rows. This is deliberately kept separate from
stock_ai/ml/champion.py's historical backtest metrics: the two answer
different questions ("how did the model do on held-out historical data" vs
"how has the model actually done on real predictions made and later checked
against real future prices") and must never be combined into one number.

BACKFILLED_REPLAY rows are excluded everywhere in this module -- they exist
(if ever generated) purely for research/analysis, never as evidence of live
performance, per the Phase 10 "never mix LIVE and BACKFILLED_REPLAY
invisibly" rule.
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
from stock_ai.universe import daily_tracking_tickers

LIVE_PREDICTION_SOURCES = ("LIVE_DAILY", "MANUAL_LIVE")


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
    resolved = [r for r in records if r.outcome_status == "RESOLVED" and r.prediction_source in LIVE_PREDICTION_SOURCES]
    count = len(resolved)
    if count == 0:
        return {
            "resolved_count": 0,
            "within_2pct": None,
            "within_5pct": None,
            "within_10pct": None,
            "more_than_10pct_off": None,
            "direction_correct_rate": None,
            "average_miss_pct": None,
        }

    abs_diff_pcts = [float(r.absolute_prediction_difference_pct) for r in resolved if r.absolute_prediction_difference_pct is not None]
    direction_matches = [r.regression_direction_match for r in resolved if r.regression_direction_match is not None]

    return {
        "resolved_count": count,
        "within_2pct": _fraction_within(abs_diff_pcts, 2),
        "within_5pct": _fraction_within(abs_diff_pcts, 5),
        "within_10pct": _fraction_within(abs_diff_pcts, 10),
        "more_than_10pct_off": _fraction_above(abs_diff_pcts, 10),
        "direction_correct_rate": (sum(1 for match in direction_matches if match) / len(direction_matches)) if direction_matches else None,
        "average_miss_pct": mean(abs_diff_pcts) if abs_diff_pcts else None,
    }


def stock_live_performance(db: Session, ticker: str) -> dict:
    normalized = normalize_ticker(ticker)
    horizons = {}
    for horizon in CHAMPION_HORIZONS:
        records = list(
            db.scalars(
                select(PredictionRecord).where(
                    PredictionRecord.ticker == normalized,
                    PredictionRecord.horizon == horizon,
                    PredictionRecord.prediction_source.in_(LIVE_PREDICTION_SOURCES),
                )
            )
        )
        horizons[horizon] = summarize_resolved(records)
    return {"ticker": normalized, "horizons": horizons}


def model_live_performance(db: Session) -> dict:
    """Aggregate, model-wide live performance -- scoped to the CURRENT daily
    tracking list (DAILY_TRACKING_TICKERS) so results from tickers no longer
    being tracked never blend into "how is live testing going right now".
    Those older tickers' own records still resolve and remain fully visible
    via stock_live_performance() for their own stock detail page -- they are
    just excluded from this cross-ticker aggregate."""
    tracked = [normalize_ticker(t) for t in daily_tracking_tickers()]
    horizons = {}
    for horizon in CHAMPION_HORIZONS:
        version = current_model_version(horizon)
        if version is None:
            horizons[horizon] = {"status": "NOT_TRAINED"}
            continue
        records = list(
            db.scalars(
                select(PredictionRecord).where(
                    PredictionRecord.horizon == horizon,
                    PredictionRecord.model_version == version,
                    PredictionRecord.prediction_source.in_(LIVE_PREDICTION_SOURCES),
                    PredictionRecord.ticker.in_(tracked),
                )
            )
        )
        horizons[horizon] = {"model_version": version, **summarize_resolved(records)}
    return {"tracked_tickers": tracked, "horizons": horizons}


def _fraction_within(values: list[float], threshold: float) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value <= threshold) / len(values)


def _fraction_above(values: list[float], threshold: float) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value > threshold) / len(values)
