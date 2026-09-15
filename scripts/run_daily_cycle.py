"""The one official daily prediction + evaluation run.

Never retrains or changes any ML model -- see stock_ai/services/daily_cycle.py
and docs/DAILY_AUTOMATION.md.

Usage:
    python3 scripts/run_daily_cycle.py
    python3 scripts/run_daily_cycle.py --no-news
    python3 scripts/run_daily_cycle.py --years 5
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_ai.db.session import get_session_factory, init_db
from stock_ai.services.daily_cycle import run_daily_cycle


LOG_DIR = PROJECT_ROOT / "var" / "logs"


def _configure_logging() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "daily_cycle.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
    )
    return log_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the official daily prediction + evaluation cycle.")
    parser.add_argument("--years", type=int, default=5, help="Years of history to request on refresh (incremental refresh still only fetches new rows).")
    parser.add_argument("--no-news", action="store_true", help="Skip the best-effort news/FinBERT refresh step.")
    args = parser.parse_args()

    log_path = _configure_logging()
    logger = logging.getLogger("stock_ai.daily_cycle.cli")
    logger.info("Starting daily cycle (log: %s)", log_path)

    init_db()
    session_factory = get_session_factory()
    with session_factory() as db:
        result = run_daily_cycle(db, refresh_years=args.years, run_news=not args.no_news)

    summary = result.to_summary_dict()
    print(json.dumps(summary, indent=2))

    return 0 if summary["status"] in ("SUCCESS", "PARTIAL_FAILURE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
