from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_ai.db.session import get_session_factory, init_db
from stock_ai.ml.config import ModelConfig, XGBoostConfig
from stock_ai.ml.phase5 import run_phase5_focus_experiments, save_phase5_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 5 focus-stock experiments from cached price data.")
    parser.add_argument("--horizons", nargs="*", default=["5d", "10d", "15d", "21d", "63d"])
    parser.add_argument("--fast", action="store_true", help="Use lightweight models for a quicker local run.")
    args = parser.parse_args()

    init_db()
    config = ModelConfig(xgboost=XGBoostConfig(n_estimators=20, max_depth=3, learning_rate=0.07, random_state=42, n_jobs=1))
    classification_models = ["dummy", "logistic"] if args.fast else ["dummy", "logistic", "random_forest", "xgboost"]
    regression_models = ["dummy", "ridge"] if args.fast else ["dummy", "ridge", "random_forest", "xgboost"]

    session_factory = get_session_factory()
    with session_factory() as db:
        report = run_phase5_focus_experiments(
            db,
            horizons=args.horizons,
            classification_models=classification_models,
            regression_models=regression_models,
            config=config,
        )

    path = save_phase5_report(report)
    print(json.dumps({"saved_to": str(path), "validation_selection": report["validation_selection"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

