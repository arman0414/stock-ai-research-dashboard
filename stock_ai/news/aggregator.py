from __future__ import annotations

import logging
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
from stock_ai.news.sentiment import FinBertSentimentAnalyzer
from stock_ai.news.services import analyze_unanalyzed_articles, upsert_articles
from stock_ai.schemas.stocks import normalize_ticker

logger = logging.getLogger("stock_ai.news.aggregator")

CURRENT_NEWS_TICKERS = ("NVDA", "AMD", "MU", "TSLA", "IREN")
DEFAULT_CURRENT_NEWS_WINDOW_HOURS = 72
DEFAULT_MIN_REFRESH_INTERVAL_MINUTES = 60


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    available: bool
    status: str
    articles_received: int = 0
    error: str | None = None


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
    skipped_due_to_recent_cache: bool = False

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
    for provider in providers:
        try:
            articles = provider.fetch_news(normalized, start_time, end_time)
        except ProviderConfigurationError as exc:
            provider_statuses.append(ProviderStatus(provider=provider.name, available=False, status="missing_api_key", error=str(exc)))
            logger.info("news refresh skipped for %s via %s: %s", normalized, provider.name, exc)
            continue
        except (ProviderQuotaError, ProviderRateLimitError) as exc:
            provider_statuses.append(ProviderStatus(provider=provider.name, available=True, status="rate_limited", error=str(exc)))
            logger.info("news provider rate-limited for %s via %s: %s", normalized, provider.name, exc)
            continue
        except Exception as exc:
            provider_statuses.append(ProviderStatus(provider=provider.name, available=True, status="failed", error=_safe_error(exc)))
            logger.info("news provider failed for %s via %s: %s", normalized, provider.name, exc)
            continue
        articles = [article for article in articles if start_time <= _as_aware(article.published_at) <= end_time]
        all_articles.extend(articles)
        provider_statuses.append(ProviderStatus(provider=provider.name, available=True, status="ok", articles_received=len(articles)))

    unique_articles = deduplicate_articles(all_articles)
    stored, created = upsert_articles(db, unique_articles) if unique_articles else ([], 0)

    analyzed = 0
    if analyze_sentiment and stored:
        try:
            analyzer = analyzer or FinBertSentimentAnalyzer((settings or get_settings()).finbert_model_name)
            analyzed = analyze_unanalyzed_articles(db, analyzer, ticker=normalized, limit=len(stored))
        except Exception as exc:
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
    )


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
