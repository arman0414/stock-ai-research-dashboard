from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.data.providers.news.base import NewsProvider, NormalizedArticle
from stock_ai.models.news import ArticleSentiment, NewsArticle
from stock_ai.news.events import categorize_event
from stock_ai.news.sentiment import FinBertSentimentAnalyzer, SentimentResult
from stock_ai.schemas.stocks import normalize_ticker


def upsert_articles(db: Session, articles: list[NormalizedArticle]) -> tuple[list[NewsArticle], int]:
    stored: list[NewsArticle] = []
    created_count = 0
    seen: dict[tuple[str, str], NewsArticle] = {}
    for article in articles:
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
        category = categorize_event(article.headline, article.summary)
        if existing:
            existing.ticker = normalize_ticker(article.ticker)
            existing.headline = article.headline
            existing.summary = article.summary
            existing.source = article.source
            existing.published_at = article.published_at
            existing.url = article.url
            existing.event_category = category
        else:
            existing = NewsArticle(
                ticker=normalize_ticker(article.ticker),
                headline=article.headline,
                summary=article.summary,
                source=article.source,
                published_at=article.published_at,
                url=article.url,
                provider=article.provider,
                external_id=article.external_id,
                event_category=category,
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


def sentiment_summary(db: Session, ticker: str) -> dict:
    articles = list_articles(db, ticker, limit=500)
    analyzed = [article for article in articles if article.sentiment is not None]
    recent = analyzed[:]
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
    }
