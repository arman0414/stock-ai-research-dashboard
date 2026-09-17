from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import func, select

from stock_ai.config import get_settings
from stock_ai.data.providers.errors import ProviderConfigurationError, ProviderQuotaError
from stock_ai.data.providers.market import get_market_data_provider
from stock_ai.db.session import get_session_factory, init_db
from stock_ai.features.dataset import build_dataset_from_db
from stock_ai.features.targets import DEFAULT_HORIZONS
from stock_ai.ml.benchmark import DEFAULT_BENCHMARK_UNIVERSE
from stock_ai.models.market_data import PriceBar
from stock_ai.schemas.stocks import StockCreate
from stock_ai.services.price_history import refresh_history
from stock_ai.services.watchlist import create_stock, get_stock
from stock_ai.utils.json_safe import dumps_json


SMOKE_TICKERS = ["AAPL", "MSFT", "NVDA"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download/cache benchmark historical price data.")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_BENCHMARK_UNIVERSE)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--smoke", action="store_true", help="Use AAPL/MSFT/NVDA and validate features/training rows.")
    args = parser.parse_args()

    settings = get_settings()
    if settings.market_data_provider != "twelve_data":
        raise SystemExit(
            "Benchmark downloads should use Twelve Data as the primary historical price provider.\n"
            "Create a free Twelve Data account and set this in /Users/armanmalik/Desktop/stocks/.env:\n"
            "MARKET_DATA_PROVIDER=twelve_data\n"
            "TWELVE_DATA_API_KEY=your_key_here"
        )
    if not settings.twelve_data_api_key and not settings.market_data_api_key:
        raise SystemExit(
            "Missing Twelve Data API key.\n"
            "Create a free Twelve Data account and set this in /Users/armanmalik/Desktop/stocks/.env:\n"
            "MARKET_DATA_PROVIDER=twelve_data\n"
            "TWELVE_DATA_API_KEY=your_key_here"
        )

    tickers = SMOKE_TICKERS if args.smoke else args.tickers
    init_db()
    provider = get_market_data_provider(settings)
    session_factory = get_session_factory(settings)
    report = {"provider": provider.name, "tickers": {}, "failed": {}}

    with session_factory() as db:
        for ticker in tickers:
            if get_stock(db, ticker) is None:
                create_stock(db, StockCreate(ticker=ticker), data_source=provider.name)
            try:
                result = refresh_history(db, provider, ticker=ticker, years=args.years)
                summary = _price_summary(db, ticker, provider.name)
                report["tickers"][ticker] = {
                    "rows_received": result.rows_received,
                    "rows_stored": result.rows_stored,
                    **summary,
                }
                if args.smoke:
                    report["tickers"][ticker]["smoke"] = _feature_smoke(db, ticker)
            except ProviderQuotaError as exc:
                db.rollback()
                report["failed"][ticker] = f"quota/rate limit reached: {exc}"
                break
            except Exception as exc:
                db.rollback()
                report["failed"][ticker] = str(exc)

    print(dumps_json(report, indent=2, sort_keys=True))


def _price_summary(db, ticker: str, source: str) -> dict:
    query = select(func.count(), func.min(PriceBar.date), func.max(PriceBar.date)).where(PriceBar.ticker == ticker, PriceBar.source == source)
    count, start, end = db.execute(query).one()
    latest = db.scalar(select(PriceBar).where(PriceBar.ticker == ticker, PriceBar.source == source).order_by(PriceBar.date.desc()).limit(1))
    return {
        "stored_rows": int(count or 0),
        "first_date": start,
        "last_date": end,
        "latest_ohlcv": None
        if latest is None
        else {
            "date": latest.date,
            "open": float(latest.open),
            "high": float(latest.high),
            "low": float(latest.low),
            "close": float(latest.close),
            "volume": latest.volume,
        },
    }


def _feature_smoke(db, ticker: str) -> dict:
    dataset = build_dataset_from_db(db, ticker=ticker, include_targets=True, include_price_action=True)
    smoke_columns = ["buyer_pressure_score", "seller_pressure_score", "nearest_support", "nearest_resistance", "cmf_20", "obv", "adx_14"]
    usable = dataset.dropna(subset=smoke_columns, how="any")
    return {
        "feature_rows": int(len(dataset)),
        "price_action_usable_rows": int(len(usable)),
        "training_ready_rows_by_horizon": {
            horizon: int(dataset.dropna(subset=[f"target_return_{horizon}", f"target_class_{horizon}"]).shape[0])
            for horizon in DEFAULT_HORIZONS
        },
        "latest_price_action": None if usable.empty else {column: float(usable.iloc[-1][column]) for column in smoke_columns},
    }


if __name__ == "__main__":
    main()
