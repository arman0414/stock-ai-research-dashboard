from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_ai.db.session import get_session_factory, init_db
from stock_ai.services.prediction_history import backfill_outcomes
from stock_ai.utils.json_safe import dumps_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill in actual outcomes for predictions old enough to have matured. Not scheduled -- run manually or wire into a cron later.")
    parser.add_argument("--ticker", default=None, help="Limit to one ticker; default backfills all pending predictions")
    args = parser.parse_args()

    init_db()
    session_factory = get_session_factory()
    with session_factory() as db:
        result = backfill_outcomes(db, ticker=args.ticker)

    print(dumps_json(result, indent=2))


if __name__ == "__main__":
    main()
