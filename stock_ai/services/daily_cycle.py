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

See docs/DAILY_AUTOMATION.md for the full design, scheduling, and the
model-review-not-auto-retrain policy.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.config import get_settings
from stock_ai.data.providers.errors import ProviderError
from stock_ai.data.providers.market import get_market_data_provider
from stock_ai.data.providers.news import get_news_provider
from stock_ai.ml.champion import CHAMPION_HORIZONS
from stock_ai.models.daily_run import DailyRunLog
from stock_ai.models.market_data import PriceBar
from stock_ai.news.sentiment import FinBertSentimentAnalyzer
from stock_ai.news.services import analyze_unanalyzed_articles, refresh_news
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.services import alerts as alert_service
from stock_ai.services import price_history, watchlist
from stock_ai.services.prediction import predict_multi_horizon
from stock_ai.services.prediction_history import backfill_outcomes, record_prediction_with_status
from stock_ai.universe import REFERENCE_ASSETS, daily_tracking_tickers, peer_basket_for

logger = logging.getLogger("stock_ai.daily_cycle")


@dataclass
class TickerOutcome:
    ticker: str
    predictions_saved: int = 0
    duplicates_skipped: int = 0
    error: str | None = None


@dataclass
class DailyCycleResult:
    started_at: datetime
    finished_at: datetime | None = None
    latest_market_date: date | None = None
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

    @property
    def tickers_failed(self) -> int:
        return sum(1 for outcome in self.ticker_outcomes if outcome.error)

    def to_summary_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "latest_market_date": self.latest_market_date.isoformat() if self.latest_market_date else None,
            "watchlist_size": self.watchlist_size,
            "tracked_tickers": self.tracked_tickers,
            "tracked_ticker_count": len(self.tracked_tickers),
            "predictions_attempted": self.predictions_attempted,
            "tickers_processed": len(self.ticker_outcomes),
            "tickers_failed": self.tickers_failed,
            "predictions_saved": self.predictions_saved,
            "duplicates_skipped": self.duplicates_skipped,
            "outcomes_resolved": self.outcomes_resolved,
            "alerts_evaluated": self.alerts_evaluated,
            "alerts_triggered": self.alerts_triggered,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "failures": [{"ticker": o.ticker, "error": o.error} for o in self.ticker_outcomes if o.error],
        }


DEFAULT_REQUEST_PACING_SECONDS = 2.0


def run_daily_cycle(db: Session, refresh_years: int = 5, run_news: bool = True, request_pacing_seconds: float = DEFAULT_REQUEST_PACING_SECONDS) -> DailyCycleResult:
    start_time = time.perf_counter()
    result = DailyCycleResult(started_at=datetime.now(timezone.utc))

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
        # retry/backoff in fetch_json_with_retries(). Spacing requests out is
        # cheap insurance against that, on top of (not instead of) the
        # incremental-only refresh that already limits how much data each
        # request asks for.
        _refresh_context_assets(db, provider, tracked_tickers, refresh_years, request_pacing_seconds)

        for ticker in tracked_tickers:
            outcome = _process_ticker(db, provider, ticker, refresh_years=refresh_years, run_news=run_news)
            result.ticker_outcomes.append(outcome)
            result.predictions_saved += outcome.predictions_saved
            result.duplicates_skipped += outcome.duplicates_skipped
            if outcome.error:
                logger.warning("daily_cycle: %s failed: %s", ticker, outcome.error)
            if request_pacing_seconds:
                time.sleep(request_pacing_seconds)

            latest_ticker_date = _latest_price_date(db, ticker)
            if latest_ticker_date and (result.latest_market_date is None or latest_ticker_date > result.latest_market_date):
                result.latest_market_date = latest_ticker_date

        # Resolution is deliberately NOT scoped to tracked_tickers: an older
        # LIVE_DAILY snapshot for a ticker that has since been removed from
        # daily tracking must still mature and resolve normally.
        resolve_summary = backfill_outcomes(db)
        result.outcomes_resolved = resolve_summary["updated"]

        # Alerts remain a full-watchlist concern, unrelated to daily tracking.
        alert_summary = _evaluate_watchlist_alerts(db, watchlist_tickers)
        result.alerts_evaluated = alert_summary["evaluated"]
        result.alerts_triggered = alert_summary["triggered"]

        result.status = "SUCCESS" if result.tickers_failed == 0 else ("PARTIAL_FAILURE" if result.tickers_failed < len(tracked_tickers) else "FAILURE")

    except Exception as exc:  # a truly unexpected failure -- still record what we can
        logger.exception("daily_cycle: unexpected failure")
        result.status = "FAILURE"
        result.ticker_outcomes.append(TickerOutcome(ticker="__cycle__", error=str(exc)))

    result.finished_at = datetime.now(timezone.utc)
    result.duration_seconds = time.perf_counter() - start_time

    run_log.finished_at = result.finished_at
    run_log.latest_market_date = result.latest_market_date
    run_log.tickers_processed = len(result.ticker_outcomes)
    run_log.tickers_failed = result.tickers_failed
    run_log.predictions_saved = result.predictions_saved
    run_log.duplicates_skipped = result.duplicates_skipped
    run_log.outcomes_resolved = result.outcomes_resolved
    run_log.duration_seconds = result.duration_seconds
    run_log.status = result.status
    failures = [{"ticker": o.ticker, "error": o.error} for o in result.ticker_outcomes if o.error]
    run_log.failures_json = json.dumps(failures) if failures else None
    db.commit()

    logger.info(
        "daily_cycle finished: status=%s market_date=%s processed=%d failed=%d saved=%d duplicates=%d resolved=%d duration=%.1fs",
        result.status,
        result.latest_market_date,
        len(result.ticker_outcomes),
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


def _process_ticker(db: Session, provider, ticker: str, refresh_years: int, run_news: bool) -> TickerOutcome:
    outcome = TickerOutcome(ticker=ticker)
    try:
        _refresh_tracked_ticker_history(db, provider, ticker, refresh_years)
    except ValueError as exc:
        outcome.error = str(exc)
        return outcome
    except ProviderError as exc:
        outcome.error = f"market data provider error: {exc}"
        return outcome

    if run_news:
        _refresh_news_best_effort(db, ticker)

    try:
        multi = predict_multi_horizon(db, ticker)
    except FileNotFoundError:
        outcome.error = "champion models not trained yet"
        return outcome
    except Exception as exc:
        outcome.error = f"prediction failed: {exc}"
        return outcome

    if multi is None:
        outcome.error = "no feature-ready price history"
        return outcome

    for horizon in CHAMPION_HORIZONS:
        signal = multi["predictions"].get(horizon)
        if signal is None:
            continue
        try:
            _record, created = record_prediction_with_status(db, signal, prediction_source="LIVE_DAILY")
        except Exception as exc:
            outcome.error = f"failed to save {horizon} snapshot: {exc}"
            continue
        if created:
            outcome.predictions_saved += 1
        else:
            outcome.duplicates_skipped += 1

    return outcome


def _refresh_news_best_effort(db: Session, ticker: str) -> None:
    """News + FinBERT are best-effort: a missing provider key, an unreachable
    feed, or a missing torch/transformers install must never abort the
    prediction cycle for a ticker."""
    try:
        provider = get_news_provider()
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        refresh_news(db, provider, ticker, start, end)
    except Exception as exc:
        logger.info("daily_cycle: news refresh skipped for %s: %s", ticker, exc)
        return

    try:
        analyzer = FinBertSentimentAnalyzer(get_settings().finbert_model_name)
        analyze_unanalyzed_articles(db, analyzer, ticker=ticker)
    except Exception as exc:
        logger.info("daily_cycle: FinBERT sentiment skipped for %s: %s", ticker, exc)


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
