from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stock_ai.config import Settings, get_settings
from stock_ai.data.providers.errors import ProviderConfigurationError, ProviderQuotaError, ProviderRateLimitError
from stock_ai.data.providers.news.alpha_vantage import AlphaVantageNewsProvider
from stock_ai.data.providers.news.base import NewsProvider, NormalizedArticle
from stock_ai.data.providers.news.finnhub import FinnhubNewsProvider
from stock_ai.data.providers.news.yahoo_rss import YahooRssNewsProvider
from stock_ai.models.news import NewsArticle
from stock_ai.news.dedupe import deduplicate_articles
from stock_ai.news.relevance import NOT_RELEVANT, RELEVANT, UNCERTAIN
from stock_ai.news.sentiment import FinBertSentimentAnalyzer
from stock_ai.news.services import analyze_unanalyzed_articles, upsert_articles
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.universe import daily_tracking_tickers

logger = logging.getLogger("stock_ai.news.aggregator")

CURRENT_NEWS_TICKERS = ("NVDA", "AMD", "MU", "TSLA", "IREN")
DEFAULT_CURRENT_NEWS_WINDOW_HOURS = 72
DEFAULT_MIN_REFRESH_INTERVAL_MINUTES = 60

# Routine daily ingestion is incremental: rather than re-requesting a fixed
# multi-day window every run (which re-downloads hundreds of already-stored
# stories), each provider is asked only for what has appeared since its own
# newest saved article, minus a small overlap for stories that get indexed
# late. Deduplication absorbs whatever the overlap re-delivers.
DEFAULT_DAILY_WINDOW_HOURS = 48  # used the first time a (ticker, provider) pair is seen
INCREMENTAL_OVERLAP_HOURS = 6  # re-ask this far back past the newest saved article
MAX_INCREMENTAL_LOOKBACK_HOURS = 72  # hard ceiling, so a long gap never becomes a huge fetch


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    available: bool
    status: str
    articles_received: int = 0
    error: str | None = None
    window_start: str | None = None
    window_end: str | None = None


@dataclass(frozen=True)
class CurrentNewsRefreshResult:
    ticker: str
    start_time: datetime
    end_time: datetime
    provider_results: list[ProviderStatus] = field(default_factory=list)
    articles_received: int = 0
    unique_articles: int = 0
    articles_created: int = 0
    articles_stored: int = 0
    articles_analyzed: int = 0
    relevant_saved: int = 0
    uncertain_saved: int = 0
    not_relevant_saved: int = 0
    sentiment_error: str | None = None
    skipped_due_to_recent_cache: bool = False

    @property
    def duplicates_skipped(self) -> int:
        """Stories the overlap window re-delivered that were already stored:
        everything received minus what was newly created."""
        return max(0, self.articles_received - self.articles_created)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "providers": [provider.__dict__ for provider in self.provider_results],
            "articles_received": self.articles_received,
            "unique_articles": self.unique_articles,
            "articles_created": self.articles_created,
            "articles_stored": self.articles_stored,
            "articles_analyzed": self.articles_analyzed,
            "relevant_saved": self.relevant_saved,
            "uncertain_saved": self.uncertain_saved,
            "not_relevant_saved": self.not_relevant_saved,
            "sentiment_error": self.sentiment_error,
            "duplicates_skipped": self.duplicates_skipped,
            "skipped_due_to_recent_cache": self.skipped_due_to_recent_cache,
        }


def build_current_news_providers(settings: Settings | None = None) -> tuple[list[NewsProvider], list[ProviderStatus]]:
    settings = settings or get_settings()
    providers: list[NewsProvider] = [YahooRssNewsProvider()]
    statuses: list[ProviderStatus] = [ProviderStatus(provider="yahoo_rss", available=True, status="available")]

    if settings.finnhub_api_key:
        providers.append(FinnhubNewsProvider(settings.finnhub_api_key))
        statuses.append(ProviderStatus(provider="finnhub", available=True, status="available"))
    else:
        statuses.append(ProviderStatus(provider="finnhub", available=False, status="missing_api_key", error="FINNHUB_API_KEY is not configured"))

    alpha_key = settings.alpha_vantage_api_key or settings.news_api_key
    if alpha_key:
        providers.append(AlphaVantageNewsProvider(alpha_key))
        statuses.append(ProviderStatus(provider="alpha_vantage", available=True, status="available"))
    else:
        statuses.append(ProviderStatus(provider="alpha_vantage", available=False, status="missing_api_key", error="ALPHA_VANTAGE_API_KEY is not configured"))

    return providers, statuses


def latest_saved_published_at(db: Session, ticker: str, provider: str) -> datetime | None:
    """Newest stored article timestamp for one (ticker, provider) pair.

    This is what makes daily ingestion incremental -- it is the high-water
    mark each provider resumes from.
    """
    latest = db.scalar(
        select(func.max(NewsArticle.published_at)).where(
            NewsArticle.ticker == normalize_ticker(ticker),
            NewsArticle.provider == provider,
        )
    )
    return _as_aware(latest) if latest is not None else None


def last_news_refresh_for_ticker(db: Session, ticker: str) -> str | None:
    """When this ticker's saved news was last written, for the UI's
    "Last news update" line. Derived from existing rows -- no extra table."""
    latest = db.scalar(select(func.max(NewsArticle.updated_at)).where(NewsArticle.ticker == normalize_ticker(ticker)))
    return _as_aware(latest).isoformat() if latest is not None else None


def incremental_start_time(
    db: Session,
    ticker: str,
    provider: str,
    end_time: datetime,
    *,
    default_window_hours: int = DEFAULT_DAILY_WINDOW_HOURS,
    overlap_hours: int = INCREMENTAL_OVERLAP_HOURS,
    max_lookback_hours: int = MAX_INCREMENTAL_LOOKBACK_HOURS,
) -> datetime:
    """Where this provider should resume fetching for this ticker.

    First run for the pair: the default daily window. Afterwards: the newest
    saved article minus a small overlap, floored at max_lookback_hours so a
    long outage can never turn into an unbounded historical download.
    """
    floor = end_time - timedelta(hours=max_lookback_hours)
    latest = latest_saved_published_at(db, ticker, provider)
    if latest is None:
        return max(end_time - timedelta(hours=default_window_hours), floor)
    return min(max(latest - timedelta(hours=overlap_hours), floor), end_time)


def refresh_current_news(
    db: Session,
    ticker: str,
    *,
    providers: Iterable[NewsProvider] | None = None,
    settings: Settings | None = None,
    end_time: datetime | None = None,
    window_hours: int = DEFAULT_CURRENT_NEWS_WINDOW_HOURS,
    force: bool = False,
    min_refresh_interval_minutes: int = DEFAULT_MIN_REFRESH_INTERVAL_MINUTES,
    analyze_sentiment: bool = False,
    analyzer: FinBertSentimentAnalyzer | None = None,
    incremental: bool = False,
    provider_pacing_seconds: float = 0.0,
) -> CurrentNewsRefreshResult:
    normalized = normalize_ticker(ticker)
    end_time = end_time or datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=window_hours)

    if not force and _recently_refreshed(db, normalized, min_refresh_interval_minutes):
        return CurrentNewsRefreshResult(ticker=normalized, start_time=start_time, end_time=end_time, skipped_due_to_recent_cache=True)

    provider_statuses: list[ProviderStatus] = []
    if providers is None:
        providers, configured_statuses = build_current_news_providers(settings)
        provider_statuses.extend(status for status in configured_statuses if not status.available)
    else:
        providers = list(providers)

    all_articles: list[NormalizedArticle] = []
    windows_used: list[datetime] = []
    for index, provider in enumerate(providers):
        # Each provider resumes from its OWN high-water mark: Yahoo being up
        # to date must not stop Finnhub from back-filling what it missed.
        provider_start = (
            incremental_start_time(db, normalized, provider.name, end_time, default_window_hours=window_hours)
            if incremental
            else start_time
        )
        windows_used.append(provider_start)
        if provider_pacing_seconds and index:
            time.sleep(provider_pacing_seconds)
        try:
            articles = provider.fetch_news(normalized, provider_start, end_time)
        except ProviderConfigurationError as exc:
            provider_statuses.append(ProviderStatus(provider=provider.name, available=False, status="missing_api_key", error=str(exc)))
            logger.info("news refresh skipped for %s via %s: %s", normalized, provider.name, exc)
            continue
        except (ProviderQuotaError, ProviderRateLimitError) as exc:
            # Record and move on -- no retry inside this cycle, and other
            # providers still run. The next daily run picks it up.
            provider_statuses.append(ProviderStatus(provider=provider.name, available=True, status="rate_limited", error=str(exc)))
            logger.info("news provider rate-limited for %s via %s: %s", normalized, provider.name, exc)
            continue
        except Exception as exc:
            provider_statuses.append(ProviderStatus(provider=provider.name, available=True, status="failed", error=_safe_error(exc)))
            logger.info("news provider failed for %s via %s: %s", normalized, provider.name, exc)
            continue
        articles = [article for article in articles if provider_start <= _as_aware(article.published_at) <= end_time]
        all_articles.extend(articles)
        provider_statuses.append(
            ProviderStatus(
                provider=provider.name,
                available=True,
                status="ok",
                articles_received=len(articles),
                window_start=provider_start.isoformat(),
                window_end=end_time.isoformat(),
            )
        )

    if windows_used:
        start_time = min(windows_used)

    unique_articles = deduplicate_articles(all_articles)
    stored, created = upsert_articles(db, unique_articles) if unique_articles else ([], 0)

    analyzed = 0
    sentiment_error: str | None = None
    if analyze_sentiment and stored:
        try:
            # analyze_unanalyzed_articles only selects rows with no sentiment
            # row yet, so already-analyzed articles are never recomputed.
            analyzer = analyzer or FinBertSentimentAnalyzer((settings or get_settings()).finbert_model_name)
            analyzed = analyze_unanalyzed_articles(db, analyzer, ticker=normalized, limit=len(stored))
        except Exception as exc:
            # News is already saved at this point; a FinBERT failure is
            # recorded and never propagated into the prediction cycle.
            db.rollback()
            sentiment_error = _safe_error(exc)
            logger.info("FinBERT sentiment skipped for %s: %s", normalized, exc)

    return CurrentNewsRefreshResult(
        ticker=normalized,
        start_time=start_time,
        end_time=end_time,
        provider_results=provider_statuses,
        articles_received=len(all_articles),
        unique_articles=len(unique_articles),
        articles_created=created,
        articles_stored=len(stored),
        articles_analyzed=analyzed,
        relevant_saved=sum(1 for article in stored if article.relevance == RELEVANT),
        uncertain_saved=sum(1 for article in stored if article.relevance == UNCERTAIN),
        not_relevant_saved=sum(1 for article in stored if article.relevance == NOT_RELEVANT),
        sentiment_error=sentiment_error,
    )


@dataclass
class DailyNewsRefreshResult:
    """Aggregate of one daily sweep over the tracked tickers."""

    started_at: datetime
    tickers: list[str] = field(default_factory=list)
    ticker_results: list[CurrentNewsRefreshResult] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    @property
    def articles_received(self) -> int:
        return sum(result.articles_received for result in self.ticker_results)

    @property
    def articles_created(self) -> int:
        return sum(result.articles_created for result in self.ticker_results)

    @property
    def articles_analyzed(self) -> int:
        return sum(result.articles_analyzed for result in self.ticker_results)

    @property
    def duplicates_skipped(self) -> int:
        return sum(result.duplicates_skipped for result in self.ticker_results)

    @property
    def relevant_saved(self) -> int:
        return sum(result.relevant_saved for result in self.ticker_results)

    @property
    def irrelevant_or_uncertain_saved(self) -> int:
        return sum(result.uncertain_saved + result.not_relevant_saved for result in self.ticker_results)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "tickers": self.tickers,
            "articles_received": self.articles_received,
            "articles_created": self.articles_created,
            "articles_analyzed": self.articles_analyzed,
            "relevant_saved": self.relevant_saved,
            "irrelevant_or_uncertain_saved": self.irrelevant_or_uncertain_saved,
            "duplicates_skipped": self.duplicates_skipped,
            "per_ticker": [result.to_dict() for result in self.ticker_results],
            "errors": self.errors,
        }

    def to_text_summary(self) -> str:
        lines = ["NEWS REFRESH", ""]
        for result in self.ticker_results:
            lines.append(result.ticker)
            if result.skipped_due_to_recent_cache:
                lines.append("  skipped (refreshed recently)")
            for provider in result.provider_results:
                detail = f"{provider.articles_received} received" if provider.status == "ok" else provider.status.replace("_", " ")
                lines.append(f"  {provider.provider}: {detail}")
            lines.append(f"  Received: {result.articles_received}")
            lines.append(f"  New unique: {result.articles_created}")
            lines.append(f"  Relevant: {result.relevant_saved}")
            lines.append(f"  Irrelevant/uncertain: {result.uncertain_saved + result.not_relevant_saved}")
            lines.append(f"  Sentiment analyzed: {result.articles_analyzed}")
            if result.sentiment_error:
                lines.append(f"  Sentiment error: {result.sentiment_error}")
            lines.append("")
        lines.append("TOTAL")
        lines.append(f"  Received: {self.articles_received}")
        lines.append(f"  New unique: {self.articles_created}")
        lines.append(f"  Relevant: {self.relevant_saved}")
        lines.append(f"  Sentiment analyzed: {self.articles_analyzed}")
        lines.append(f"  Duplicates skipped: {self.duplicates_skipped}")
        return "\n".join(lines)


def refresh_tracked_news(
    db: Session,
    *,
    tickers: Iterable[str] | None = None,
    settings: Settings | None = None,
    providers: Iterable[NewsProvider] | None = None,
    end_time: datetime | None = None,
    analyze_sentiment: bool = True,
    analyzer: FinBertSentimentAnalyzer | None = None,
    force: bool = False,
    ticker_pacing_seconds: float = 0.0,
    provider_pacing_seconds: float = 0.0,
    min_refresh_interval_minutes: int = DEFAULT_MIN_REFRESH_INTERVAL_MINUTES,
) -> DailyNewsRefreshResult:
    """Routine daily news ingestion for the DAILY TRACKING LIST only.

    Deliberately scoped to daily_tracking_tickers() -- never the user's full
    watchlist -- and incremental per (ticker, provider). Every ticker is
    isolated: one ticker's provider failure never stops the rest.
    """
    settings = settings or get_settings()
    end_time = end_time or datetime.now(timezone.utc)
    tracked = [normalize_ticker(t) for t in (tickers if tickers is not None else daily_tracking_tickers())]
    tracked = list(dict.fromkeys(tracked))

    # One analyzer for the whole sweep: loading FinBERT is the expensive
    # part, and re-creating it per ticker would reload the model five times.
    # Best-effort -- if it cannot be constructed (torch/transformers missing),
    # news is still fetched and saved, just without sentiment.
    if analyze_sentiment and analyzer is None:
        try:
            analyzer = FinBertSentimentAnalyzer(settings.finbert_model_name)
        except Exception as exc:
            logger.info("FinBERT unavailable for daily news refresh: %s", exc)
            analyzer = None

    result = DailyNewsRefreshResult(started_at=end_time, tickers=tracked)
    for index, ticker in enumerate(tracked):
        if ticker_pacing_seconds and index:
            time.sleep(ticker_pacing_seconds)
        try:
            ticker_result = refresh_current_news(
                db,
                ticker,
                providers=providers,
                settings=settings,
                end_time=end_time,
                force=force,
                min_refresh_interval_minutes=min_refresh_interval_minutes,
                analyze_sentiment=analyze_sentiment,
                analyzer=analyzer,
                incremental=True,
                provider_pacing_seconds=provider_pacing_seconds,
            )
        except Exception as exc:  # one bad ticker must never end the sweep
            db.rollback()
            logger.info("daily news refresh failed for %s: %s", ticker, exc)
            result.errors.append({"ticker": ticker, "error": _safe_error(exc)})
            continue
        result.ticker_results.append(ticker_result)

    logger.info(
        "daily news refresh: tickers=%d received=%d created=%d analyzed=%d duplicates=%d errors=%d",
        len(tracked),
        result.articles_received,
        result.articles_created,
        result.articles_analyzed,
        result.duplicates_skipped,
        len(result.errors),
    )
    return result


def provider_health(db: Session, settings: Settings | None = None) -> dict:
    providers, statuses = build_current_news_providers(settings)
    configured = {status.provider: status for status in statuses}
    for provider in providers:
        configured.setdefault(provider.name, ProviderStatus(provider=provider.name, available=True, status="available"))
    return {
        "providers": [
            {
                "provider": status.provider,
                "available": status.available,
                "status": status.status,
                "last_news_refresh": _last_refresh_for_provider(db, status.provider),
                "error": status.error,
            }
            for status in configured.values()
        ]
    }


def _recently_refreshed(db: Session, ticker: str, min_refresh_interval_minutes: int) -> bool:
    if min_refresh_interval_minutes <= 0:
        return False
    latest_updated = db.scalar(select(func.max(NewsArticle.updated_at)).where(NewsArticle.ticker == ticker))
    if latest_updated is None:
        return False
    latest = latest_updated.replace(tzinfo=timezone.utc) if latest_updated.tzinfo is None else latest_updated.astimezone(timezone.utc)
    return latest >= datetime.now(timezone.utc) - timedelta(minutes=min_refresh_interval_minutes)


def _last_refresh_for_provider(db: Session, provider: str) -> str | None:
    latest = db.scalar(select(func.max(NewsArticle.updated_at)).where(NewsArticle.provider == provider))
    if latest is None:
        return None
    aware = latest.replace(tzinfo=timezone.utc) if latest.tzinfo is None else latest.astimezone(timezone.utc)
    return aware.isoformat()


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    return message if message else exc.__class__.__name__


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
