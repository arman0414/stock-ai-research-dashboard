from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from stock_ai.universe import DAILY_TRACKING_TICKERS_DEFAULT, FOCUS_STOCKS, parse_ticker_list


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    database_url: str
    default_watchlist: tuple[str, ...]
    daily_tracking_tickers: tuple[str, ...]
    daily_cycle_request_pacing_seconds: float
    market_data_provider: str
    news_provider: str
    historical_news_provider: str
    market_data_api_key: str | None
    twelve_data_api_key: str | None
    news_api_key: str | None
    alpha_vantage_api_key: str | None
    finbert_model_name: str
    huggingface_token: str | None
    email_username: str | None
    email_password: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file(PROJECT_ROOT / ".env")

    default_database = f"sqlite:///{PROJECT_ROOT / 'var' / 'data' / 'stocks.sqlite3'}"

    return Settings(
        database_url=os.getenv("DATABASE_URL", default_database),
        default_watchlist=parse_ticker_list(os.getenv("DEFAULT_WATCHLIST"), FOCUS_STOCKS),
        daily_tracking_tickers=parse_ticker_list(os.getenv("DAILY_TRACKING_TICKERS"), DAILY_TRACKING_TICKERS_DEFAULT),
        daily_cycle_request_pacing_seconds=float(os.getenv("DAILY_CYCLE_REQUEST_PACING_SECONDS", "2.0")),
        market_data_provider=os.getenv("MARKET_DATA_PROVIDER", "stooq").lower(),
        news_provider=os.getenv("NEWS_PROVIDER", "yahoo_rss").lower(),
        historical_news_provider=os.getenv("HISTORICAL_NEWS_PROVIDER", os.getenv("NEWS_PROVIDER", "yahoo_rss")).lower(),
        market_data_api_key=os.getenv("MARKET_DATA_API_KEY") or None,
        twelve_data_api_key=os.getenv("TWELVE_DATA_API_KEY") or None,
        news_api_key=os.getenv("NEWS_API_KEY") or None,
        alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY") or None,
        finbert_model_name=os.getenv("FINBERT_MODEL_NAME", "ProsusAI/finbert"),
        huggingface_token=os.getenv("HUGGINGFACE_TOKEN") or None,
        email_username=os.getenv("EMAIL_USERNAME") or None,
        email_password=os.getenv("EMAIL_PASSWORD") or None,
    )
