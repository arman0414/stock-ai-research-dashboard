from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_ai.db.session import Base


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
    event_category: Mapped[str] = mapped_column(String(64), default="GENERAL_NEWS", nullable=False)
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
