from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_ai.data.providers.market import get_market_data_provider
from stock_ai.db.session import get_session_factory, init_db
from stock_ai.ml.benchmark import (
    DEFAULT_BENCHMARK_UNIVERSE,
    compare_benchmarks,
    load_multi_stock_news,
    load_multi_stock_prices,
    run_benchmark,
    save_benchmark_report,
)
from stock_ai.ml.config import ModelConfig, XGBoostConfig
from stock_ai.schemas.stocks import StockCreate
from stock_ai.services.price_history import refresh_history
from stock_ai.services.watchlist import create_stock, get_stock


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh price data and run Phase 4 benchmarks.")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_BENCHMARK_UNIVERSE)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--horizons", nargs="*", default=["5d", "10d"])
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--include-news", action="store_true")
    args = parser.parse_args()

    init_db()
    provider = get_market_data_provider()
    session_factory = get_session_factory()
    refresh_status = {}
    with session_factory() as db:
        for ticker in args.tickers:
            if get_stock(db, ticker) is None:
                create_stock(db, StockCreate(ticker=ticker))
            try:
                result = refresh_history(db, provider, ticker=ticker, years=args.years)
                refresh_status[ticker] = {"rows_received": result.rows_received, "latest_price_date": str(result.latest_price_date)}
            except Exception as exc:
                db.rollback()
                refresh_status[ticker] = {"error": str(exc)}
        prices, skipped = load_multi_stock_prices(db, args.tickers)
        news = load_multi_stock_news(db, args.tickers)

    if prices.empty:
        path = save_benchmark_report(
            {
                "status": "failed",
                "reason": "No usable price data available from configured provider",
                "universe": args.tickers,
                "refresh_status": refresh_status,
                "skipped": skipped,
            },
            prefix="phase4_real_data_failed",
        )
        raise SystemExit(f"No usable price data. Failure report saved to {path}. Refresh status: {refresh_status}")

    config = ModelConfig(xgboost=XGBoostConfig(n_estimators=20, max_depth=3, learning_rate=0.07, random_state=42, n_jobs=1))
    classification_models = ["dummy", "logistic"] if args.fast else ["dummy", "logistic", "random_forest", "xgboost"]
    regression_models = ["dummy", "ridge"] if args.fast else ["dummy", "ridge", "random_forest", "xgboost"]
    technical = run_benchmark(
        prices,
        "technical",
        horizons=args.horizons,
        config=config,
        classification_models=classification_models,
        regression_models=regression_models,
    )
    price_action = run_benchmark(
        prices,
        "technical_price_action",
        horizons=args.horizons,
        config=config,
        classification_models=classification_models,
        regression_models=regression_models,
    )
    news_report = None
    if args.include_news and news:
        news_report = run_benchmark(
            prices,
            "technical_price_action_news",
            horizons=args.horizons,
            news_articles=news,
            config=config,
            classification_models=classification_models,
            regression_models=regression_models,
        )
    report = {
        "universe": args.tickers,
        "refresh_status": refresh_status,
        "skipped": skipped,
        "article_count": len(news),
        "technical": technical,
        "technical_price_action": price_action,
        "technical_price_action_news": news_report,
        "comparison": compare_benchmarks(technical, price_action, news_report),
    }
    path = save_benchmark_report(report, prefix="phase4_real_data")
    print(json.dumps({"saved_to": str(path), "skipped": skipped, "article_count": len(news)}, indent=2))


if __name__ == "__main__":
    main()
