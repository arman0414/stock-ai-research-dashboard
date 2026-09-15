from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_ai.config import PROJECT_ROOT
from stock_ai.db.session import get_session_factory, init_db
from stock_ai.features.dataset import build_dataset_from_db
from stock_ai.features.targets import DEFAULT_HORIZONS
from stock_ai.ml.training import train_all_horizons, train_horizon_models


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and compare stock AI models.")
    parser.add_argument("--ticker", required=True, help="Ticker to train on during local development.")
    parser.add_argument("--horizon", choices=list(DEFAULT_HORIZONS), default="10d")
    parser.add_argument("--all-horizons", action="store_true")
    parser.add_argument("--model", choices=["dummy", "logistic", "random_forest", "xgboost"], default=None)
    parser.add_argument("--compare-all", action="store_true", default=True)
    parser.add_argument("--save-artifacts", action="store_true")
    args = parser.parse_args()

    init_db()
    session_factory = get_session_factory()
    with session_factory() as db:
        horizons = list(DEFAULT_HORIZONS) if args.all_horizons else [args.horizon]
        dataset = build_dataset_from_db(db, args.ticker, include_targets=True, training_ready=False)
        artifact_root = PROJECT_ROOT / "artifacts" / "models" if args.save_artifacts else None

        if args.all_horizons:
            results = train_all_horizons(dataset, horizons=horizons, save_artifacts_to=artifact_root)
        else:
            classification_models = [args.model] if args.model else None
            regression_models = ["dummy", "ridge", "random_forest", "xgboost"] if args.model is None else None
            results = {
                args.horizon: train_horizon_models(
                    dataset,
                    horizon=args.horizon,
                    classification_models=classification_models,
                    regression_models=regression_models,
                    save_artifacts_to=artifact_root,
                )
            }

    report = {
        horizon: {
            "best_classifier": result.best_classifier_name,
            "best_regressor": result.best_regressor_name,
            "split": result.split_summary,
            "classification_validation": {
                name: {
                    "accuracy": metrics["accuracy"],
                    "balanced_accuracy": metrics["balanced_accuracy"],
                    "macro_f1": metrics["macro_f1"],
                }
                for name, metrics in result.classification_validation_metrics.items()
            },
            "regression_validation": {
                name: {
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "direction_accuracy": metrics["direction_accuracy"],
                }
                for name, metrics in result.regression_validation_metrics.items()
            },
        }
        for horizon, result in results.items()
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

