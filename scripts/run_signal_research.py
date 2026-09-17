from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_ai.db.session import get_session_factory, init_db
from stock_ai.ml.signal_research import run_signal_research, save_champion_metadata, save_signal_research_report
from stock_ai.utils.json_safe import dumps_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run short-horizon model and signal-quality research.")
    parser.add_argument("--horizons", nargs="*", default=["5d", "10d", "15d"])
    parser.add_argument("--min-signal-samples", type=int, default=30)
    args = parser.parse_args()

    init_db()
    session_factory = get_session_factory()
    with session_factory() as db:
        report = run_signal_research(db, horizons=tuple(args.horizons), min_signal_samples=args.min_signal_samples)

    report_path = save_signal_research_report(report)
    champions_path = save_champion_metadata(report)
    print(
        dumps_json(
            {
                "saved_to": str(report_path),
                "champions_saved_to": str(champions_path),
                "assessment": report["assessment"],
                "champions": report["champions"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
