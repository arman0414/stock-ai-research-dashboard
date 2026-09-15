from __future__ import annotations

import json
from pathlib import Path

from stock_ai.services.model_performance import get_model_performance_summary


def _write_metadata(root: Path, horizon: str, **overrides) -> None:
    base = {
        "is_primary_research_horizon": horizon == "5d",
        "calibration_method": "sigmoid",
        "calibration_selection_metrics": {"sigmoid": {"multiclass_brier": 0.5}},
        "thresholds": {
            "bullish": {"threshold": 0.55, "status": "VALIDATED"},
            "bearish": {"threshold": 1.01, "status": "INSUFFICIENT_EVIDENCE"},
        },
        "test_evaluation": {
            "bullish": {"precision": 0.42, "sample_count": 600},
            "bearish": {"precision": None, "sample_count": 0},
        },
        "regression": {"test": {"mae": 0.06, "target_price_mae": 19.5, "within_5pct": 0.59, "within_10pct": 0.82, "direction_accuracy": 0.51}},
        "reliability_tables": {"test_calibrated": [{"bucket": "0.40-0.50", "count": 100}]},
        "multi_seed_robustness": {"balanced_accuracy": {"mean": 0.41, "std": 0.006}},
    }
    base.update(overrides)
    horizon_dir = root / horizon
    horizon_dir.mkdir(parents=True, exist_ok=True)
    (horizon_dir / "metadata.json").write_text(json.dumps(base))


def test_summary_reads_saved_metadata_without_touching_models(tmp_path) -> None:
    _write_metadata(tmp_path, "5d")
    _write_metadata(tmp_path, "10d")
    _write_metadata(tmp_path, "15d")

    summary = get_model_performance_summary(artifacts_root=tmp_path)

    assert set(summary["horizons"].keys()) == {"5d", "10d", "15d"}
    five_d = summary["horizons"]["5d"]
    assert five_d["status_label"] == "Best Current Horizon"
    assert five_d["is_primary_research_horizon"] is True
    assert five_d["calibration_method"] == "sigmoid"
    assert five_d["bullish_threshold"] == 0.55
    assert five_d["bullish_status"] == "VALIDATED"
    assert five_d["bearish_status"] == "INSUFFICIENT_EVIDENCE"
    assert five_d["target_price_mae"] == 19.5

    assert summary["horizons"]["10d"]["status_label"] == "Secondary"
    assert summary["horizons"]["15d"]["status_label"] == "Lower Confidence"


def test_summary_reports_not_trained_when_metadata_missing(tmp_path) -> None:
    _write_metadata(tmp_path, "5d")
    summary = get_model_performance_summary(artifacts_root=tmp_path)
    assert summary["horizons"]["10d"] == {"status": "NOT_TRAINED"}
    assert summary["horizons"]["15d"] == {"status": "NOT_TRAINED"}


def test_summary_never_overstates_bearish_when_insufficient_evidence(tmp_path) -> None:
    _write_metadata(tmp_path, "5d")
    summary = get_model_performance_summary(artifacts_root=tmp_path)
    five_d = summary["horizons"]["5d"]
    assert five_d["bearish_test_precision"] is None
    assert five_d["bearish_test_sample_count"] == 0
