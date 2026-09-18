from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_ai.db.session import Base
from stock_ai.news.relevance import RELEVANT


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_news_provider_external_id"),
        UniqueConstraint("provider", "url", name="uq_news_provider_url"),
        Index("ix_news_articles_ticker_published_at", "ticker", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_headline: Mapped[str | None] = mapped_column(String(512), nullable=True)
    event_category: Mapped[str] = mapped_column(String(64), default="GENERAL_NEWS", nullable=False)
    # relevant / uncertain / not_relevant for THIS ticker. Every article is
    # stored regardless; this only decides what may move News Mood. See
    # stock_ai/news/relevance.py. Never read by the ML feature pipeline.
    relevance: Mapped[str] = mapped_column(String(16), default=RELEVANT, nullable=False, server_default=text("'relevant'"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sentiment: Mapped["ArticleSentiment | None"] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ArticleSentiment(Base):
    __tablename__ = "article_sentiment"
    __table_args__ = (UniqueConstraint("article_id", "sentiment_model", "sentiment_model_version", name="uq_article_sentiment_model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False)
    sentiment_label: Mapped[str] = mapped_column(String(16), nullable=False)
    positive_probability: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    neutral_probability: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    negative_probability: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    sentiment_score: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    sentiment_model: Mapped[str] = mapped_column(String(255), nullable=False)
    sentiment_model_version: Mapped[str] = mapped_column(String(255), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    article: Mapped[NewsArticle] = relationship(back_populates="sentiment")


def ensure_news_schema(engine: Engine) -> None:
    """Back-fill nullable metadata columns for existing SQLite databases.

    The project does not use a migration framework yet; create_all() will add
    these columns for fresh test databases, and this hook keeps the local
    cached SQLite file compatible without touching existing rows.
    """
    if engine.dialect.name != "sqlite":
        return
    existing = {column["name"] for column in inspect(engine).get_columns("news_articles")}
    required = {
        "author": "VARCHAR(255)",
        "provider_sources_json": "TEXT",
        "canonical_url": "TEXT",
        "normalized_headline": "VARCHAR(512)",
        "relevance": "VARCHAR(16) NOT NULL DEFAULT 'relevant'",
    }
    with engine.begin() as connection:
        for column, ddl_type in required.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE news_articles ADD COLUMN {column} {ddl_type}"))
