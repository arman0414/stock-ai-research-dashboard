"""The one official daily prediction + evaluation cycle.

This module NEVER retrains, recalibrates, or changes any ML model, threshold,
or feature. It only:
  1. refreshes cached market/news data,
  2. runs the EXISTING champion models to produce 5D/10D/15D predictions,
  3. freezes one official LIVE_DAILY snapshot per (ticker, horizon, market
     as_of date, model_version) -- the existing Phase 9/10 uniqueness rule is
     authoritative, so running this twice on the same market day is a no-op,
  4. resolves any predictions that have matured,
  5. re-evaluates alert rules,
  6. records a DailyRunLog row and a human-readable log line.

There are three independent ticker concepts in this codebase, and this
module only touches one of them:
  - USER WATCHLIST (stock_ai.services.watchlist) -- what's visible on the
    dashboard. Untouched by this module except for alert evaluation, which
    still runs over the full watchlist exactly as before.
  - TRAINING / REFERENCE UNIVERSE (stock_ai.universe) -- what models are
    trained/researched against. Never read or written here.
  - DAILY LIVE TRACKING LIST (stock_ai.universe.daily_tracking_tickers(),
    configured via the DAILY_TRACKING_TICKERS env var) -- the fixed, small
    set of tickers this module creates official LIVE_DAILY prediction
    snapshots for. ONLY these tickers get predictions and count toward
    "tickers_processed" / "predictions_saved" in the run summary, regardless
    of how large the watchlist is.

Context assets (SPY/QQQ/sector ETFs, peer tickers of the tracked tickers) are
refreshed as a best-effort side step because the champion models' features
need them -- they are never treated as "processed tickers" and never get
their own LIVE_DAILY predictions unless explicitly added to
DAILY_TRACKING_TICKERS.

Outcome resolution (backfill_outcomes) is NOT scoped to the tracking list: it
resolves every pending prediction in the database, including older snapshots
for tickers that are no longer in DAILY_TRACKING_TICKERS. Removing a ticker
from daily tracking only stops new snapshots -- it never abandons old ones.

DATA FRESHNESS (this is the important part of this phase): a LIVE_DAILY
prediction may only be created from a ticker's PriceBar row that IS the
expected, already-fully-closed NYSE session (see stock_ai.market_calendar).
If a ticker's latest stored bar is still behind that expected session --
because the provider hasn't published it yet, or because a request was
rate-limited -- that ticker is marked WAITING (never FAILED, never silently
given a stale/fabricated prediction) and is naturally retried the next time
this cycle runs, thanks to the existing (ticker, horizon, prediction_date,
model_version) uniqueness rule: a retry can only ever fill in what's
missing, never create a duplicate or backfill a day using information from
a later day.

See docs/DAILY_AUTOMATION.md for the full design, scheduling, and the
model-review-not-auto-retrain policy.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.config import get_settings
from stock_ai.data.providers.errors import ProviderError
from stock_ai.data.providers.market import get_market_data_provider
from stock_ai.market_calendar import latest_completed_trading_session
from stock_ai.ml.champion import CHAMPION_HORIZONS
from stock_ai.models.daily_run import DailyRunLog
from stock_ai.models.market_data import PriceBar
from stock_ai.news.aggregator import DailyNewsRefreshResult, refresh_tracked_news
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.services import alerts as alert_service
from stock_ai.services import price_history, watchlist
from stock_ai.services.prediction import predict_multi_horizon
from stock_ai.services.prediction_history import backfill_outcomes, record_prediction_with_status
from stock_ai.universe import REFERENCE_ASSETS, daily_tracking_tickers, peer_basket_for
from stock_ai.utils.json_safe import dumps_json

logger = logging.getLogger("stock_ai.daily_cycle")

STATUS_CURRENT = "CURRENT"
STATUS_WAITING = "WAITING"
STATUS_FAILED = "FAILED"


@dataclass
class TickerOutcome:
    ticker: str
    status: str = STATUS_WAITING
    latest_data_session: date | None = None
    predictions_saved: int = 0
    duplicates_skipped: int = 0
    error: str | None = None


@dataclass
class DailyCycleResult:
    started_at: datetime
    finished_at: datetime | None = None
    latest_market_date: date | None = None
    expected_market_session: date | None = None
    watchlist_size: int = 0
    tracked_tickers: list[str] = field(default_factory=list)
    predictions_attempted: int = 0
    ticker_outcomes: list[TickerOutcome] = field(default_factory=list)
    predictions_saved: int = 0
    duplicates_skipped: int = 0
    outcomes_resolved: int = 0
    alerts_evaluated: int = 0
    alerts_triggered: int = 0
    status: str = "RUNNING"
    duration_seconds: float | None = None
    news: DailyNewsRefreshResult | None = None

    @property
    def tickers_current(self) -> int:
        return sum(1 for outcome in self.ticker_outcomes if outcome.status == STATUS_CURRENT)

    @property
    def tickers_waiting(self) -> int:
        return sum(1 for outcome in self.ticker_outcomes if outcome.status == STATUS_WAITING)

    @property
    def tickers_failed(self) -> int:
        """Permanent-ish failures only (e.g. no feature-ready data, champion
        not trained) -- NOT tickers merely waiting on fresh market data or
        hit by a transient/rate-limited provider error. Those are retryable
        and must never inflate this count into a false "FAILURE" run status."""
        return sum(1 for outcome in self.ticker_outcomes if outcome.status == STATUS_FAILED)

    @property
    def session_complete(self) -> bool:
        return len(self.tracked_tickers) > 0 and self.tickers_current == len(self.tracked_tickers)

    def to_summary_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "latest_market_date": self.latest_market_date.isoformat() if self.latest_market_date else None,
            "expected_market_session": self.expected_market_session.isoformat() if self.expected_market_session else None,
            "session_complete": self.session_complete,
            "watchlist_size": self.watchlist_size,
            "tracked_tickers": self.tracked_tickers,
            "tracked_ticker_count": len(self.tracked_tickers),
            "predictions_attempted": self.predictions_attempted,
            "tickers_processed": len(self.ticker_outcomes),
            "tickers_current": self.tickers_current,
            "tickers_waiting": self.tickers_waiting,
            "tickers_failed": self.tickers_failed,
            "predictions_saved": self.predictions_saved,
            "duplicates_skipped": self.duplicates_skipped,
            "outcomes_resolved": self.outcomes_resolved,
            "alerts_evaluated": self.alerts_evaluated,
            "alerts_triggered": self.alerts_triggered,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "news": self.news.to_dict() if self.news else None,
            "ticker_statuses": [
                {"ticker": o.ticker, "status": o.status, "latest_data_session": o.latest_data_session.isoformat() if o.latest_data_session else None, "error": o.error}
                for o in self.ticker_outcomes
            ],
            "failures": [{"ticker": o.ticker, "status": o.status, "error": o.error} for o in self.ticker_outcomes if o.error],
        }


DEFAULT_REQUEST_PACING_SECONDS = 2.0


def run_daily_cycle(db: Session, refresh_years: int = 5, run_news: bool = True, request_pacing_seconds: float | None = None) -> DailyCycleResult:
    if request_pacing_seconds is None:
        request_pacing_seconds = get_settings().daily_cycle_request_pacing_seconds

    start_time = time.perf_counter()
    result = DailyCycleResult(started_at=datetime.now(timezone.utc))
    result.expected_market_session = latest_completed_trading_session(result.started_at)

    run_log = DailyRunLog(status="RUNNING")
    db.add(run_log)
    db.commit()
    db.refresh(run_log)

    try:
        provider = get_market_data_provider()
        watchlist_stocks = watchlist.list_stocks(db)
        watchlist_tickers = [normalize_ticker(stock.ticker) for stock in watchlist_stocks]
        result.watchlist_size = len(watchlist_tickers)

        # The daily LIVE_DAILY prediction experiment is intentionally scoped
        # to a small, fixed tracking list -- independent of how large the
        # watchlist is. See the module docstring for why.
        tracked_tickers = list(dict.fromkeys(normalize_ticker(t) for t in daily_tracking_tickers()))
        result.tracked_tickers = tracked_tickers
        result.predictions_attempted = len(tracked_tickers) * len(CHAMPION_HORIZONS)

        # A small, deliberate pause between price-data requests. Twelve
        # Data's free tier enforces a per-minute request quota; refreshing
        # many tickers back-to-back can exceed it even with the existing
        # retry/backoff (now Retry-After-aware) in fetch_json_with_retries().
        # Spacing requests out is cheap insurance against that, on top of
        # (not instead of) the incremental-only refresh that already limits
        # how much data each request asks for.
        _refresh_context_assets(db, provider, tracked_tickers, refresh_years, request_pacing_seconds)

        # News runs as its own step, BEFORE the per-ticker market-data
        # freshness gate below. News is a separate research/context layer: a
        # ticker WAITING on an unpublished price bar must still collect
        # today's stories rather than skipping them until the bar lands.
        if run_news:
            result.news = _refresh_news_best_effort(db, tracked_tickers, request_pacing_seconds)

        for ticker in tracked_tickers:
            outcome = _process_ticker(db, provider, ticker, refresh_years=refresh_years, expected_session=result.expected_market_session)
            result.ticker_outcomes.append(outcome)
            result.predictions_saved += outcome.predictions_saved
            result.duplicates_skipped += outcome.duplicates_skipped
            if outcome.status == STATUS_WAITING:
                logger.info("daily_cycle: %s waiting for market data: %s", ticker, outcome.error)
            elif outcome.status == STATUS_FAILED:
                logger.warning("daily_cycle: %s failed: %s", ticker, outcome.error)
            if request_pacing_seconds:
                time.sleep(request_pacing_seconds)

            if outcome.latest_data_session and (result.latest_market_date is None or outcome.latest_data_session > result.latest_market_date):
                result.latest_market_date = outcome.latest_data_session

        # Resolution is deliberately NOT scoped to tracked_tickers: an older
        # LIVE_DAILY snapshot for a ticker that has since been removed from
        # daily tracking must still mature and resolve normally.
        resolve_summary = backfill_outcomes(db)
        result.outcomes_resolved = resolve_summary["updated"]

        # Alerts remain a full-watchlist concern, unrelated to daily tracking.
        alert_summary = _evaluate_watchlist_alerts(db, watchlist_tickers)
        result.alerts_evaluated = alert_summary["evaluated"]
        result.alerts_triggered = alert_summary["triggered"]

        if result.tickers_current == len(tracked_tickers):
            result.status = "SUCCESS"
        elif result.tickers_failed == 0:
            # Nobody permanently failed -- the rest are just waiting on
            # fresh market data or a transient provider hiccup, which the
            # next run will naturally retry.
            result.status = "WAITING_FOR_MARKET_DATA"
        elif result.tickers_current > 0:
            result.status = "PARTIAL_FAILURE"
        else:
            result.status = "FAILURE"

    except Exception as exc:  # a truly unexpected failure -- still record what we can
        logger.exception("daily_cycle: unexpected failure")
        result.status = "FAILURE"
        result.ticker_outcomes.append(TickerOutcome(ticker="__cycle__", status=STATUS_FAILED, error=str(exc)))

    result.finished_at = datetime.now(timezone.utc)
    result.duration_seconds = time.perf_counter() - start_time

    run_log.finished_at = result.finished_at
    run_log.latest_market_date = result.latest_market_date
    run_log.expected_market_session = result.expected_market_session
    run_log.tickers_processed = len(result.ticker_outcomes)
    run_log.tickers_current = result.tickers_current
    run_log.tickers_waiting = result.tickers_waiting
    run_log.tickers_failed = result.tickers_failed
    run_log.predictions_attempted = result.predictions_attempted
    run_log.predictions_saved = result.predictions_saved
    run_log.duplicates_skipped = result.duplicates_skipped
    run_log.outcomes_resolved = result.outcomes_resolved
    run_log.duration_seconds = result.duration_seconds
    run_log.status = result.status
    failures = [{"ticker": o.ticker, "status": o.status, "error": o.error} for o in result.ticker_outcomes if o.error]
    run_log.failures_json = dumps_json(failures) if failures else None
    db.commit()

    logger.info(
        "daily_cycle finished: status=%s expected_session=%s latest_market_date=%s current=%d waiting=%d failed=%d saved=%d duplicates=%d resolved=%d duration=%.1fs",
        result.status,
        result.expected_market_session,
        result.latest_market_date,
        result.tickers_current,
        result.tickers_waiting,
        result.tickers_failed,
        result.predictions_saved,
        result.duplicates_skipped,
        result.outcomes_resolved,
        result.duration_seconds,
    )

    return result


def _refresh_context_assets(db: Session, provider, tracked_tickers: list[str], refresh_years: int, request_pacing_seconds: float = 0.0) -> None:
    """Refreshes reference/sector assets and peer tickers needed by the
    tracked tickers' features. These never get their own LIVE_DAILY
    prediction snapshots -- see the module docstring."""
    context_tickers: set[str] = set(REFERENCE_ASSETS)
    for ticker in tracked_tickers:
        context_tickers.update(peer_basket_for(ticker))
    context_only = sorted(context_tickers - set(tracked_tickers))

    for ticker in context_only:
        try:
            price_history.refresh_price_bars(db, provider=provider, ticker=ticker, years=refresh_years)
        except Exception as exc:  # best-effort: a stale peer/context asset must never abort the run
            db.rollback()
            logger.warning("daily_cycle: context asset %s refresh failed: %s", ticker, exc)
        if request_pacing_seconds:
            time.sleep(request_pacing_seconds)


def _refresh_tracked_ticker_history(db: Session, provider, ticker: str, refresh_years: int):
    """A tracked ticker does not need to be on the user's watchlist -- if it
    happens to be, refresh the watchlist-aware way (updates Stock.data_source
    / last_refreshed_at); otherwise refresh price bars directly, exactly like
    a context asset. Keeps the tracking list and the watchlist independent."""
    if watchlist.get_stock(db, ticker) is not None:
        return price_history.refresh_history(db, provider=provider, ticker=ticker, years=refresh_years)
    return price_history.refresh_price_bars(db, provider=provider, ticker=ticker, years=refresh_years)


def _process_ticker(db: Session, provider, ticker: str, refresh_years: int, expected_session: date) -> TickerOutcome:
    outcome = TickerOutcome(ticker=ticker)
    try:
        _refresh_tracked_ticker_history(db, provider, ticker, refresh_years)
    except ValueError as exc:
        # Retryable: e.g. a transient watchlist-membership race. Never a
        # reason to give up on the ticker permanently.
        outcome.status = STATUS_WAITING
        outcome.error = str(exc)
        return outcome
    except ProviderError as exc:
        # Rate limit / transient provider error -- exactly the "temporary
        # provider error" case that must be retried on the next run, never
        # treated as a permanent failure.
        outcome.status = STATUS_WAITING
        outcome.error = f"market data provider error: {exc}"
        return outcome

    latest_ticker_date = _latest_price_date(db, ticker)
    outcome.latest_data_session = latest_ticker_date

    if latest_ticker_date is None:
        outcome.status = STATUS_WAITING
        outcome.error = "no price history yet"
        return outcome

    if latest_ticker_date < expected_session:
        # The provider hasn't published the expected session's bar yet (or
        # our refresh above didn't get it, e.g. mid-outage). Do NOT create a
        # prediction from stale data, and do NOT fabricate the date --
        # simply wait for a later run to retry.
        outcome.status = STATUS_WAITING
        outcome.error = f"latest stored data is {latest_ticker_date.isoformat()}, expected {expected_session.isoformat()}"
        return outcome

    try:
        multi = predict_multi_horizon(db, ticker)
    except FileNotFoundError:
        outcome.status = STATUS_FAILED
        outcome.error = "champion models not trained yet"
        return outcome
    except Exception as exc:
        outcome.status = STATUS_FAILED
        outcome.error = f"prediction failed: {exc}"
        return outcome

    if multi is None:
        outcome.status = STATUS_FAILED
        outcome.error = "no feature-ready price history"
        return outcome

    outcome.status = STATUS_CURRENT
    for horizon in CHAMPION_HORIZONS:
        signal = multi["predictions"].get(horizon)
        if signal is None:
            continue
        try:
            _record, created = record_prediction_with_status(db, signal, prediction_source="LIVE_DAILY")
        except Exception as exc:
            outcome.status = STATUS_FAILED
            outcome.error = f"failed to save {horizon} snapshot: {exc}"
            continue
        if created:
            outcome.predictions_saved += 1
        else:
            outcome.duplicates_skipped += 1

    return outcome


def _refresh_news_best_effort(db: Session, tracked_tickers: list[str], request_pacing_seconds: float) -> DailyNewsRefreshResult | None:
    """News + FinBERT are best-effort: a missing provider key, an unreachable
    feed, or a missing torch/transformers install must never abort the
    prediction cycle.

    This runs as its own step, BEFORE and independently of the per-ticker
    market-data freshness gate. News is a separate research/context layer: a
    ticker still WAITING on an unpublished price bar should keep collecting
    today's stories rather than silently skipping them until the bar lands.
    """
    try:
        return refresh_tracked_news(
            db,
            tickers=tracked_tickers,
            analyze_sentiment=True,
            ticker_pacing_seconds=request_pacing_seconds,
            provider_pacing_seconds=request_pacing_seconds,
        )
    except Exception as exc:
        db.rollback()
        logger.info("daily_cycle: news refresh step skipped: %s", exc)
        return None


def _evaluate_watchlist_alerts(db: Session, watchlist_tickers: list[str]) -> dict:
    evaluated = 0
    triggered = 0
    for ticker in watchlist_tickers:
        for rule in alert_service.list_alert_rules(db, ticker=ticker):
            if not rule.is_active:
                continue
            try:
                status = alert_service.evaluate_alert_rule(db, rule)
            except Exception as exc:
                logger.info("daily_cycle: alert evaluation failed for rule %s: %s", rule.id, exc)
                continue
            evaluated += 1
            if status["is_triggered"]:
                triggered += 1
    return {"evaluated": evaluated, "triggered": triggered}


def _latest_price_date(db: Session, ticker: str) -> date | None:
    return db.scalar(select(PriceBar.date).where(PriceBar.ticker == normalize_ticker(ticker)).order_by(PriceBar.date.desc()).limit(1))
