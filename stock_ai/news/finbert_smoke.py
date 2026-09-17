from __future__ import annotations

from stock_ai.config import get_settings
from stock_ai.news.sentiment import FinBertSentimentAnalyzer
from stock_ai.utils.json_safe import dumps_json


def main() -> None:
    settings = get_settings()
    analyzer = FinBertSentimentAnalyzer(settings.finbert_model_name)
    headlines = [
        "Apple shares rise after stronger than expected earnings",
        "Tesla stock falls after company cuts delivery outlook",
        "Microsoft announces new AI partnership",
    ]
    try:
        results = analyzer.analyze(headlines)
    except Exception as exc:
        raise SystemExit(
            f"FinBERT runtime smoke test failed: {exc}\n"
            "If this is a network/model download issue, install/cache ProsusAI/finbert locally or set HUGGINGFACE_TOKEN if required."
        )
    print(
        dumps_json(
            [
                {
                    "headline": headline,
                    "label": result.label,
                    "positive_probability": result.positive_probability,
                    "neutral_probability": result.neutral_probability,
                    "negative_probability": result.negative_probability,
                    "sentiment_score": result.sentiment_score,
                    "model": result.model_name,
                }
                for headline, result in zip(headlines, results)
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
