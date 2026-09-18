from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.data.providers.news.base import NewsProvider, NormalizedArticle
from stock_ai.models.news import ArticleSentiment, NewsArticle
from stock_ai.news.dedupe import canonical_url_key, normalized_headline_key
from stock_ai.news.events import categorize_event
from stock_ai.news.relevance import RELEVANT, classify_relevance
from stock_ai.news.sentiment import FinBertSentimentAnalyzer, SentimentResult
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.utils.json_safe import dumps_json


def upsert_articles(db: Session, articles: list[NormalizedArticle]) -> tuple[list[NewsArticle], int]:
    stored: list[NewsArticle] = []
    created_count = 0
    seen: dict[tuple[str, str], NewsArticle] = {}
    for article in articles:
        normalized_ticker = normalize_ticker(article.ticker)
        article_canonical_url = canonical_url_key(article.url)
        article_normalized_headline = normalized_headline_key(article.headline)
        key = (article.provider, article.external_id)
        existing = seen.get(key)
        if existing is None:
            existing = db.scalar(
                select(NewsArticle).where(
                    NewsArticle.provider == article.provider,
                    NewsArticle.external_id == article.external_id,
                )
            )
        if existing is None:
            existing = db.scalar(select(NewsArticle).where(NewsArticle.provider == article.provider, NewsArticle.url == article.url))
        if existing is None and article_canonical_url:
            existing = db.scalar(
                select(NewsArticle)
                .where(NewsArticle.ticker == normalized_ticker, NewsArticle.canonical_url == article_canonical_url)
                .order_by(NewsArticle.published_at.desc())
                .limit(1)
            )
        if existing is None and article_normalized_headline:
            candidates = list(
                db.scalars(
                    select(NewsArticle)
                    .where(NewsArticle.ticker == normalized_ticker, NewsArticle.normalized_headline == article_normalized_headline)
                    .order_by(NewsArticle.published_at.desc())
                    .limit(10)
                )
            )
            existing = next((candidate for candidate in candidates if _same_stored_story(candidate, article)), None)
        category = categorize_event(article.headline, article.summary)
        relevance = classify_relevance(normalized_ticker, article.headline, article.summary)
        provider_sources = _merge_provider_sources(existing.provider_sources_json if existing else None, article)
        if existing:
            existing.ticker = normalized_ticker
            existing.headline = article.headline
            existing.summary = article.summary
            existing.source = article.source
            existing.published_at = article.published_at
            existing.url = article.url
            existing.author = article.author
            existing.provider_sources_json = provider_sources
            existing.canonical_url = article_canonical_url
            existing.normalized_headline = article_normalized_headline
            existing.event_category = category
            existing.relevance = relevance
        else:
            existing = NewsArticle(
                ticker=normalized_ticker,
                headline=article.headline,
                summary=article.summary,
                source=article.source,
                published_at=article.published_at,
                url=article.url,
                provider=article.provider,
                external_id=article.external_id,
                author=article.author,
                provider_sources_json=provider_sources,
                canonical_url=article_canonical_url,
                normalized_headline=article_normalized_headline,
                event_category=category,
                relevance=relevance,
            )
            db.add(existing)
            created_count += 1
        seen[key] = existing
        seen[(article.provider, article.url)] = existing
        stored.append(existing)
    db.commit()
    for article in stored:
        db.refresh(article)
    return stored, created_count


def refresh_news(db: Session, provider: NewsProvider, ticker: str, start_date: datetime, end_date: datetime) -> dict:
    articles = provider.fetch_news(normalize_ticker(ticker), start_date, end_date)
    stored, created = upsert_articles(db, articles)
    return {
        "ticker": normalize_ticker(ticker),
        "provider": provider.name,
        "supports_historical": provider.supports_historical,
        "articles_received": len(articles),
        "articles_created": created,
        "articles_stored": len(stored),
    }


def list_articles(db: Session, ticker: str, limit: int = 50) -> list[NewsArticle]:
    return list(
        db.scalars(
            select(NewsArticle)
            .where(NewsArticle.ticker == normalize_ticker(ticker))
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
        )
    )


def analyze_unanalyzed_articles(
    db: Session,
    analyzer: FinBertSentimentAnalyzer,
    ticker: str | None = None,
    limit: int = 50,
) -> int:
    query = select(NewsArticle).outerjoin(ArticleSentiment).where(ArticleSentiment.id.is_(None)).order_by(NewsArticle.published_at.asc()).limit(limit)
    if ticker:
        query = query.where(NewsArticle.ticker == normalize_ticker(ticker))
    articles = list(db.scalars(query))
    texts = [f"{article.headline}. {article.summary or ''}" for article in articles]
    results = analyzer.analyze(texts)
    for article, result in zip(articles, results):
        persist_sentiment(db, article, result)
    db.commit()
    return len(results)


def persist_sentiment(db: Session, article: NewsArticle, result: SentimentResult) -> ArticleSentiment:
    sentiment = article.sentiment
    if sentiment is None:
        sentiment = ArticleSentiment(article_id=article.id)
        db.add(sentiment)
        article.sentiment = sentiment
    sentiment.sentiment_label = result.label
    sentiment.positive_probability = Decimal(str(result.positive_probability))
    sentiment.neutral_probability = Decimal(str(result.neutral_probability))
    sentiment.negative_probability = Decimal(str(result.negative_probability))
    sentiment.sentiment_score = Decimal(str(result.sentiment_score))
    sentiment.sentiment_model = result.model_name
    sentiment.sentiment_model_version = result.model_version
    sentiment.analyzed_at = result.analyzed_at
    return sentiment


def sentiment_summary(db: Session, ticker: str, window_hours: int = 72, as_of: datetime | None = None) -> dict:
    """News Mood over recent, unique, relevant, sentiment-analyzed articles.

    Rows are already deduplicated at save time (upsert_articles merges a story
    seen via several providers into one row), so counting rows here counts
    each story once. Only `relevance == RELEVANT` articles are counted --
    industry-only (UNCERTAIN) and unrelated stories are excluded, see
    stock_ai/news/relevance.py. This is a presentation/alerting concern only;
    the ML feature pipeline reads articles independently and is unaffected.
    """
    articles = list_articles(db, ticker, limit=500)
    as_of = as_of or datetime.now(timezone.utc)
    cutoff = as_of - timedelta(hours=window_hours)
    in_window = [article for article in articles if article.sentiment is not None and _as_aware(article.published_at) >= cutoff]
    recent = [article for article in in_window if article.relevance == RELEVANT]
    excluded = len(in_window) - len(recent)
    positives = sum(1 for article in recent if article.sentiment.sentiment_label == "POSITIVE")
    neutrals = sum(1 for article in recent if article.sentiment.sentiment_label == "NEUTRAL")
    negatives = sum(1 for article in recent if article.sentiment.sentiment_label == "NEGATIVE")
    scores = [float(article.sentiment.sentiment_score) for article in recent]
    average = sum(scores) / len(scores) if scores else 0.0
    return {
        "ticker": normalize_ticker(ticker),
        "articles_7d": len(recent),
        "positive": positives,
        "neutral": neutrals,
        "negative": negatives,
        "average_sentiment": average,
        "sentiment_direction": "POSITIVE" if average > 0.05 else "NEGATIVE" if average < -0.05 else "NEUTRAL",
        "last_updated": max((article.sentiment.analyzed_at for article in recent), default=None),
        "providers": sorted({provider for article in recent for provider in article_provider_sources(article)}),
        "excluded_unrelated": excluded,
    }


def reclassify_relevance(db: Session, ticker: str | None = None) -> dict:
    """Re-run relevance over already-saved articles, in place.

    Purely local: no provider calls and no FinBERT. Used to apply updated
    rules to rows saved before the filter existed, and safe to re-run.
    """
    query = select(NewsArticle)
    if ticker:
        query = query.where(NewsArticle.ticker == normalize_ticker(ticker))
    counts: dict[str, int] = {}
    changed = 0
    for article in db.scalars(query):
        new_state = classify_relevance(article.ticker, article.headline, article.summary)
        if article.relevance != new_state:
            article.relevance = new_state
            changed += 1
        counts[new_state] = counts.get(new_state, 0) + 1
    db.commit()
    return {"ticker": normalize_ticker(ticker) if ticker else None, "changed": changed, "counts": counts}


def article_provider_sources(article: NewsArticle) -> list[str]:
    if article.provider_sources_json:
        try:
            values = json.loads(article.provider_sources_json)
            if isinstance(values, list):
                return [str(value) for value in values if value]
        except json.JSONDecodeError:
            pass
    return [article.provider]


def _merge_provider_sources(existing_json: str | None, article: NormalizedArticle) -> str:
    values: list[str] = []
    if existing_json:
        try:
            loaded = json.loads(existing_json)
            if isinstance(loaded, list):
                values.extend(str(value) for value in loaded if value)
        except json.JSONDecodeError:
            pass
    values.extend(article.provider_sources or (article.provider,))
    values.append(article.provider)
    return dumps_json(list(dict.fromkeys(values)))


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _same_stored_story(existing: NewsArticle, article: NormalizedArticle) -> bool:
    if existing.source and article.source and existing.source.strip().lower() != article.source.strip().lower():
        return False
    return abs((_as_aware(existing.published_at) - _as_aware(article.published_at)).total_seconds()) <= 36 * 60 * 60
