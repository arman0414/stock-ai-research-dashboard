from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_ai.db.session import get_session_factory, init_db
from stock_ai.ml.phase6 import run_phase6_research


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 6 absolute-prediction research.")
    parser.add_argument("--horizons", nargs="*", default=["5d", "10d", "15d"])
    parser.add_argument("--min-signal-samples", type=int, default=30)
    args = parser.parse_args()

    init_db()
    session_factory = get_session_factory()
    with session_factory() as db:
        report = run_phase6_research(db, horizons=tuple(args.horizons), min_signal_samples=args.min_signal_samples)

    root = PROJECT_ROOT / "artifacts" / "benchmarks"
    root.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    path = root / f"phase6_research_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(json.dumps({"saved_to": str(path), "assessment": report["assessment"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
