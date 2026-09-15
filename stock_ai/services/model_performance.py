"""Phase 8: read-only summary of already-trained champion metadata for the
Model Performance page. Never trains, retrains, or changes any threshold --
purely reads stock_ai/ml/champion.py's saved metadata.json files."""
from __future__ import annotations

import json
from pathlib import Path

from stock_ai.ml.champion import CHAMPION_HORIZONS, DEFAULT_ARTIFACTS_ROOT


STATUS_LABELS = {
    "5d": "Best Current Horizon",
    "10d": "Secondary",
    "15d": "Lower Confidence",
}


def get_model_performance_summary(artifacts_root: Path | None = None) -> dict:
    root = artifacts_root or DEFAULT_ARTIFACTS_ROOT
    horizons = {}
    for horizon in CHAMPION_HORIZONS:
        metadata_path = root / horizon / "metadata.json"
        if not metadata_path.exists():
            horizons[horizon] = {"status": "NOT_TRAINED"}
            continue
        metadata = json.loads(metadata_path.read_text())
        horizons[horizon] = _summarize_horizon(horizon, metadata)
    return {"horizons": horizons}


def _summarize_horizon(horizon: str, metadata: dict) -> dict:
    regression_test = metadata.get("regression", {}).get("test", {})
    thresholds = metadata.get("thresholds", {})
    test_evaluation = metadata.get("test_evaluation", {})
    multi_seed = metadata.get("multi_seed_robustness", {})

    return {
        "status_label": STATUS_LABELS.get(horizon, "Experimental"),
        "is_primary_research_horizon": metadata.get("is_primary_research_horizon", False),
        "calibration_method": metadata.get("calibration_method"),
        "calibration_selection_metrics": metadata.get("calibration_selection_metrics"),
        "bullish_threshold": thresholds.get("bullish", {}).get("threshold"),
        "bullish_status": thresholds.get("bullish", {}).get("status"),
        "bearish_threshold": thresholds.get("bearish", {}).get("threshold"),
        "bearish_status": thresholds.get("bearish", {}).get("status"),
        "bullish_test_precision": test_evaluation.get("bullish", {}).get("precision"),
        "bullish_test_sample_count": test_evaluation.get("bullish", {}).get("sample_count"),
        "bearish_test_precision": test_evaluation.get("bearish", {}).get("precision"),
        "bearish_test_sample_count": test_evaluation.get("bearish", {}).get("sample_count"),
        "target_price_mae": regression_test.get("target_price_mae"),
        "regression_mae": regression_test.get("mae"),
        "within_5pct": regression_test.get("within_5pct"),
        "within_10pct": regression_test.get("within_10pct"),
        "direction_accuracy": regression_test.get("direction_accuracy"),
        "reliability_test_calibrated": metadata.get("reliability_tables", {}).get("test_calibrated"),
        "multi_seed_balanced_accuracy_mean": multi_seed.get("balanced_accuracy", {}).get("mean"),
        "multi_seed_balanced_accuracy_std": multi_seed.get("balanced_accuracy", {}).get("std"),
    }
