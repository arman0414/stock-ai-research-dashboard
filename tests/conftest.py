from __future__ import annotations

from collections.abc import Iterator

import pytest

from stock_ai.config import Settings
from stock_ai.db.session import Base, get_engine, get_session_factory
from stock_ai.models import PriceBar, WatchlistStock  # noqa: F401


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'stocks-test.sqlite3'}",
        default_watchlist=("NVDA", "AMD", "MU", "SNDK", "IREN", "PONY", "TSLA", "RDDT", "APLD", "SMCI"),
        market_data_provider="stooq",
        news_provider="yahoo_rss",
        historical_news_provider="yahoo_rss",
        market_data_api_key=None,
        twelve_data_api_key=None,
        news_api_key=None,
        alpha_vantage_api_key=None,
        finbert_model_name="ProsusAI/finbert",
        huggingface_token=None,
        email_username=None,
        email_password=None,
    )


@pytest.fixture
def db_session(test_settings: Settings) -> Iterator:
    engine = get_engine(test_settings)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_session_factory(test_settings)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
