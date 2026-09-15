from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SentimentResult:
    label: str
    positive_probability: float
    neutral_probability: float
    negative_probability: float
    sentiment_score: float
    model_name: str
    model_version: str
    analyzed_at: datetime


class FinBertSentimentAnalyzer:
    def __init__(self, model_name: str = "ProsusAI/finbert") -> None:
        self.model_name = model_name
        self.model_version = model_name
        self._pipeline = None

    def analyze(self, texts: list[str]) -> list[SentimentResult]:
        if not texts:
            return []
        pipeline = self._get_pipeline()
        raw_results = pipeline(texts, truncation=True)
        return [parse_finbert_output(result, self.model_name, self.model_version) for result in raw_results]

    def _get_pipeline(self):
        if self._pipeline is None:
            from transformers import pipeline

            self._pipeline = pipeline("text-classification", model=self.model_name, tokenizer=self.model_name, top_k=None, device=-1)
        return self._pipeline


def parse_finbert_output(raw_result, model_name: str = "ProsusAI/finbert", model_version: str = "ProsusAI/finbert") -> SentimentResult:
    scores = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
    rows = raw_result if isinstance(raw_result, list) else [raw_result]
    for row in rows:
        label = str(row["label"]).lower()
        if label in scores:
            scores[label] = float(row["score"])
    sentiment_score = scores["positive"] - scores["negative"]
    label = max(scores.items(), key=lambda item: item[1])[0].upper()
    return SentimentResult(
        label=label,
        positive_probability=scores["positive"],
        neutral_probability=scores["neutral"],
        negative_probability=scores["negative"],
        sentiment_score=sentiment_score,
        model_name=model_name,
        model_version=model_version,
        analyzed_at=datetime.now(timezone.utc),
    )

