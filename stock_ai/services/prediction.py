"""Phase 7: the production absolute-prediction service.

Loads champion artifacts (classifier + calibrated_model + regressor +
metadata) trained by stock_ai/ml/champion.py, builds the latest feature row
for a ticker from cached price history, and assembles the research signal
object the future dashboard consumes. Never fits or selects anything here --
that is champion.py's job, done ahead of time with validation-only data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from stock_ai.features.context import add_context_features
from stock_ai.features.dataset import build_feature_dataset
from stock_ai.ml.champion import CHAMPION_HORIZONS, DEFAULT_ARTIFACTS_ROOT, DEFAULT_MIN_EVIDENCE, PRIMARY_RESEARCH_HORIZON, load_champion_artifact
from stock_ai.ml.phase5 import load_prices_for_tickers
from stock_ai.ml.phase6 import _compute_setup_quality
from stock_ai.ml.signal_gate import decide_signal, threshold_policy_from_metadata
from stock_ai.ml.signal_research import _predict_proba
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.services.market_context import build_market_context
from stock_ai.universe import REFERENCE_ASSETS, peer_basket_for


@dataclass
class ChampionBundle:
    horizon: str
    classifier: Any
    calibrated_model: Any
    regressor: Any
    metadata: dict


_BUNDLE_CACHE: dict[str, ChampionBundle] = {}


def load_bundle(horizon: str, artifacts_root: Path | None = None, force_reload: bool = False) -> ChampionBundle:
    if not force_reload and horizon in _BUNDLE_CACHE:
        return _BUNDLE_CACHE[horizon]
    root = artifacts_root or DEFAULT_ARTIFACTS_ROOT
    raw = load_champion_artifact(root / horizon)
    bundle = ChampionBundle(horizon=horizon, classifier=raw["classifier"], calibrated_model=raw["calibrated_model"], regressor=raw["regressor"], metadata=raw["metadata"])
    _BUNDLE_CACHE[horizon] = bundle
    return bundle


def clear_bundle_cache() -> None:
    _BUNDLE_CACHE.clear()


def build_latest_feature_row(db: Session, ticker: str) -> pd.Series | None:
    normalized = normalize_ticker(ticker)
    context_tickers = tuple(dict.fromkeys((normalized, *REFERENCE_ASSETS, *peer_basket_for(normalized))))
    prices, _ = load_prices_for_tickers(db, context_tickers)
    if prices.empty or normalized not in set(prices["ticker"]):
        return None

    base = build_feature_dataset(prices, include_targets=False, include_price_action=True)
    dataset = add_context_features(base, prices)
    ticker_rows = dataset[dataset["ticker"] == normalized].sort_values("date")
    if ticker_rows.empty:
        return None
    return ticker_rows.iloc[-1]


def build_signal_from_bundle(
    bundle: ChampionBundle,
    feature_row: pd.Series,
    current_price: float,
    ticker: str,
    as_of: str,
    min_evidence: int = DEFAULT_MIN_EVIDENCE,
) -> dict:
    metadata = bundle.metadata
    labels: list[str] = metadata["labels"]
    feature_columns: list[str] = metadata["feature_columns"]

    X = pd.DataFrame([feature_row.reindex(feature_columns)], columns=feature_columns)
    X = X.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)

    raw_proba = _predict_proba(bundle.classifier, X, len(labels))[0]
    calibrated_proba = _predict_proba(bundle.calibrated_model, X, len(labels))[0]
    predicted_index = int(calibrated_proba.argmax())
    predicted_class = labels[predicted_index]

    up_index = labels.index("UP")
    down_index = labels.index("DOWN")
    calibrated_up = float(calibrated_proba[up_index])
    calibrated_down = float(calibrated_proba[down_index])

    bullish_policy = threshold_policy_from_metadata(metadata["thresholds"]["bullish"], min_evidence=min_evidence)
    bearish_policy = threshold_policy_from_metadata(metadata["thresholds"]["bearish"], min_evidence=min_evidence)

    setup_quality_label, setup_details = _setup_quality_for_row(feature_row, metadata["setup_quality"])

    gate = decide_signal(
        predicted_class=predicted_class,
        calibrated_up_probability=calibrated_up,
        calibrated_down_probability=calibrated_down,
        bullish_policy=bullish_policy,
        bearish_policy=bearish_policy,
        setup_quality=setup_quality_label,
        require_setup_quality=False,
    )

    historical = _historical_reliability(metadata, gate["signal_status"])

    predicted_return = float(bundle.regressor.predict(X)[0])
    model_target_price = current_price * (1 + predicted_return)
    uncertainty = metadata["regression"]["uncertainty"]
    residual_low = uncertainty.get("residual_p10") or 0.0
    residual_high = uncertainty.get("residual_p90") or 0.0
    uncertainty_low = current_price * (1 + predicted_return + residual_low)
    uncertainty_high = current_price * (1 + predicted_return + residual_high)

    return {
        "ticker": normalize_ticker(ticker),
        "as_of": as_of,
        "horizon": bundle.horizon,
        "current_price": float(current_price),
        "classification": {
            "direction": predicted_class,
            "raw_probability": float(raw_proba[predicted_index]),
            "calibrated_probability": float(calibrated_proba[predicted_index]),
            "calibrated_up_probability": calibrated_up,
            "calibrated_down_probability": calibrated_down,
            "signal_status": gate["signal_status"],
            "confidence": gate["confidence"],
            "gating_reason": gate["gating_reason"],
            "historical_signal_accuracy": historical["historical_signal_accuracy"],
            "historical_signal_samples": historical["historical_signal_samples"],
            "historical_signal_precision": historical["historical_signal_precision"],
            "bullish_threshold": bullish_policy.threshold if bullish_policy.is_usable else None,
            "bearish_threshold": bearish_policy.threshold if bearish_policy.is_usable else None,
        },
        "regression": {
            "predicted_return": predicted_return,
            "model_target_price": float(model_target_price),
            "uncertainty_low": float(min(uncertainty_low, uncertainty_high)),
            "uncertainty_high": float(max(uncertainty_low, uncertainty_high)),
            "p50_abs_error": uncertainty.get("p50_abs_error"),
        },
        "setup": {
            "quality": setup_quality_label,
            **setup_details,
        },
        "model": {
            "classification_version": f"random_forest_{bundle.horizon}_seed{metadata.get('classifier_random_state')}",
            "regression_version": f"random_forest_raw_{bundle.horizon}",
            "calibration_method": metadata["calibration_method"],
            "is_primary_research_horizon": metadata.get("is_primary_research_horizon", False),
        },
    }


def predict_horizon(db: Session, ticker: str, horizon: str, artifacts_root: Path | None = None, min_evidence: int = DEFAULT_MIN_EVIDENCE) -> dict | None:
    bundle = load_bundle(horizon, artifacts_root=artifacts_root)
    feature_row = build_latest_feature_row(db, ticker)
    if feature_row is None:
        return None
    current_price = float(feature_row["close"])
    as_of = pd.to_datetime(feature_row["date"]).date().isoformat()
    return build_signal_from_bundle(bundle, feature_row, current_price, ticker, as_of, min_evidence=min_evidence)


def predict_multi_horizon(
    db: Session,
    ticker: str,
    horizons: tuple[str, ...] = CHAMPION_HORIZONS,
    artifacts_root: Path | None = None,
    min_evidence: int = DEFAULT_MIN_EVIDENCE,
) -> dict | None:
    normalized = normalize_ticker(ticker)
    feature_row = build_latest_feature_row(db, normalized)
    if feature_row is None:
        return None

    current_price = float(feature_row["close"])
    as_of = pd.to_datetime(feature_row["date"]).date().isoformat()

    predictions: dict[str, dict | None] = {}
    for horizon in horizons:
        try:
            bundle = load_bundle(horizon, artifacts_root=artifacts_root)
        except FileNotFoundError:
            predictions[horizon] = None
            continue
        predictions[horizon] = build_signal_from_bundle(bundle, feature_row, current_price, normalized, as_of, min_evidence=min_evidence)

    return {
        "ticker": normalized,
        "as_of": as_of,
        "current_price": current_price,
        "primary_research_horizon": PRIMARY_RESEARCH_HORIZON,
        "predictions": predictions,
        "market_context": build_market_context(db, normalized, feature_row),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _historical_reliability(metadata: dict, signal_status: str) -> dict:
    if signal_status == "BULLISH":
        row = metadata.get("test_evaluation", {}).get("bullish", {})
    elif signal_status == "BEARISH":
        row = metadata.get("test_evaluation", {}).get("bearish", {})
    else:
        return {"historical_signal_accuracy": None, "historical_signal_samples": None, "historical_signal_precision": None}
    return {
        "historical_signal_accuracy": row.get("precision"),
        "historical_signal_samples": row.get("sample_count"),
        "historical_signal_precision": row.get("precision"),
    }


def _setup_quality_for_row(feature_row: pd.Series, setup_meta: dict) -> tuple[str, dict]:
    stats = {key: tuple(value) for key, value in setup_meta["stats"].items()}
    row_frame = pd.DataFrame([feature_row])
    score = float(_compute_setup_quality(row_frame, stats)[0])
    low_cut = setup_meta["low_cut"]
    high_cut = setup_meta["high_cut"]

    if not np.isfinite(score):
        quality = "UNKNOWN"
    elif score >= high_cut:
        quality = "STRONG"
    elif score >= low_cut:
        quality = "MODERATE"
    else:
        quality = "WEAK"

    pressure_stats = {key: tuple(value) for key, value in setup_meta.get("pressure_stats", {}).items()}
    details = {
        "buyer_pressure": _pressure_label(feature_row.get("buyer_pressure_score"), pressure_stats.get("buyer_pressure_score")),
        "seller_pressure": _pressure_label(feature_row.get("seller_pressure_score"), pressure_stats.get("seller_pressure_score")),
        "support": _safe_float(feature_row.get("nearest_support")),
        "resistance": _safe_float(feature_row.get("nearest_resistance")),
    }
    return quality, details


def _pressure_label(value: Any, stats: tuple[float, float] | None) -> str:
    numeric = _safe_float(value)
    if stats is None or numeric is None:
        return "UNKNOWN"
    mean, std = stats
    z = (numeric - mean) / (std or 1.0)
    if z >= 0.3:
        return "STRONG"
    if z >= -0.3:
        return "MODERATE"
    return "WEAK"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(numeric) else numeric
