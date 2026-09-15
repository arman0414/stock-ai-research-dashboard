from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_ai.db.session import get_session_factory, init_db
from stock_ai.ml.champion import CHAMPION_HORIZONS, DEFAULT_MIN_EVIDENCE, DEFAULT_SEEDS, save_champion_report, train_champion_models


def main() -> None:
    parser = argparse.ArgumentParser(description="Train calibrated champion models for the production prediction path.")
    parser.add_argument("--horizons", nargs="*", default=list(CHAMPION_HORIZONS))
    parser.add_argument("--seeds", nargs="*", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--min-evidence", type=int, default=DEFAULT_MIN_EVIDENCE)
    args = parser.parse_args()

    init_db()
    session_factory = get_session_factory()
    with session_factory() as db:
        report = train_champion_models(db, horizons=tuple(args.horizons), seeds=tuple(args.seeds), min_evidence=args.min_evidence)

    report_path = save_champion_report(report)
    print(json.dumps({"saved_report_to": str(report_path)}, indent=2))
    for horizon, horizon_report in report["horizons"].items():
        print(f"--- {horizon} ---")
        print(json.dumps({
            "calibration_method": horizon_report["calibration_method"],
            "bullish_threshold": horizon_report["thresholds"]["bullish"]["threshold"],
            "bullish_status": horizon_report["thresholds"]["bullish"]["status"],
            "bearish_threshold": horizon_report["thresholds"]["bearish"]["threshold"],
            "bearish_status": horizon_report["thresholds"]["bearish"]["status"],
        }, indent=2))


if __name__ == "__main__":
    main()
