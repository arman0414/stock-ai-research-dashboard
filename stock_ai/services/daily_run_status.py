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
    predictions_failed_or_waiting = run.predictions_attempted - run.predictions_saved - run.duplicates_skipped
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "latest_market_date": run.latest_market_date.isoformat() if run.latest_market_date else None,
        "expected_market_session": run.expected_market_session.isoformat() if run.expected_market_session else None,
        "tickers_processed": run.tickers_processed,
        "tickers_current": run.tickers_current,
        "tickers_waiting": run.tickers_waiting,
        "tickers_failed": run.tickers_failed,
        "predictions_attempted": run.predictions_attempted,
        "predictions_saved": run.predictions_saved,
        "duplicates_skipped": run.duplicates_skipped,
        "predictions_failed_or_waiting": max(predictions_failed_or_waiting, 0),
        "outcomes_resolved": run.outcomes_resolved,
        "duration_seconds": run.duration_seconds,
        "status": run.status,
        "failures": json.loads(run.failures_json) if run.failures_json else [],
    }
