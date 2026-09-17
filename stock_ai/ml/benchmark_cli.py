from __future__ import annotations

import argparse

from stock_ai.db.session import get_session_factory, init_db
from stock_ai.features.targets import DEFAULT_HORIZONS
from stock_ai.ml.benchmark import (
    DEFAULT_BENCHMARK_UNIVERSE,
    compare_benchmarks,
    load_multi_stock_news,
    load_multi_stock_prices,
    run_benchmark,
    save_benchmark_report,
)
from stock_ai.utils.json_safe import dumps_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-stock stock AI benchmark reports.")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_BENCHMARK_UNIVERSE)
    parser.add_argument("--horizons", nargs="*", choices=list(DEFAULT_HORIZONS), default=list(DEFAULT_HORIZONS))
    parser.add_argument("--feature-groups", nargs="*", default=["technical", "technical_price_action"])
    parser.add_argument("--fast", action="store_true", help="Use smaller model lists for quick smoke benchmarks.")
    args = parser.parse_args()

    init_db()
    session_factory = get_session_factory()
    with session_factory() as db:
        prices, skipped = load_multi_stock_prices(db, args.tickers)
        if prices.empty:
            raise SystemExit(f"No benchmarkable price history found. Skipped: {skipped}")
        news = load_multi_stock_news(db, args.tickers)

    classification_models = ["dummy", "logistic"] if args.fast else None
    regression_models = ["dummy", "ridge"] if args.fast else None
    reports = {}
    for group in args.feature_groups:
        reports[group] = run_benchmark(
            prices,
            feature_group=group,
            horizons=args.horizons,
            news_articles=news,
            classification_models=classification_models,
            regression_models=regression_models,
        )
    report = {
        "universe": args.tickers,
        "skipped": skipped,
        "article_count": len(news),
        "reports": reports,
        "comparison": compare_benchmarks(
            reports["technical"],
            reports.get("technical_price_action", reports["technical"]),
            reports.get("technical_price_action_news"),
        )
        if "technical" in reports
        else {},
    }
    path = save_benchmark_report(report, prefix="phase4_benchmark")
    print(dumps_json({"saved_to": str(path), "skipped": skipped}, indent=2))


if __name__ == "__main__":
    main()
