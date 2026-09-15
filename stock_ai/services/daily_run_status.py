from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.models.daily_run import DailyRunLog


def latest_daily_run_status(db: Session) -> dict | None:
    run = db.scalar(select(DailyRunLog).order_by(DailyRunLog.started_at.desc()).limit(1))
    if run is None:
        return None
    return daily_run_log_to_dict(run)


def daily_run_log_to_dict(run: DailyRunLog) -> dict:
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "latest_market_date": run.latest_market_date.isoformat() if run.latest_market_date else None,
        "tickers_processed": run.tickers_processed,
        "tickers_failed": run.tickers_failed,
        "predictions_saved": run.predictions_saved,
        "duplicates_skipped": run.duplicates_skipped,
        "outcomes_resolved": run.outcomes_resolved,
        "duration_seconds": run.duration_seconds,
        "status": run.status,
        "failures": json.loads(run.failures_json) if run.failures_json else [],
    }
