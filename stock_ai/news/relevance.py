"""Conservative, deterministic relevance classification for News Mood.

Providers' company-news endpoints are associative, not exact: asking Finnhub
for NVDA's company news also returns stories that merely appeared alongside
NVDA coverage -- a SpaceX valuation piece, "Why Bitcoin Is Up Today", a
podcasting retrospective. Those are worth keeping in the archive, but letting
them move NVDA's News Mood turns the mood into a market-wide average instead
of a read on the company.

So every article is classified once, at save time, into one of three states:

  RELEVANT     -- the company itself is named: its ticker, a company-name
                  alias, or a brand/product/executive uniquely tied to it
                  (CUDA, Blackwell, Jensen Huang). Counts toward News Mood.
  UNCERTAIN    -- no direct mention, but the story is about the company's
                  industry (AI chips, robotaxis). Saved and browsable, but
                  NOT counted toward News Mood -- there is no strong evidence
                  it is about this company.
  NOT_RELEVANT -- neither signal. Saved, never counted.

Nothing is ever deleted; this only decides what may move the mood.

Deliberately rule-based, with no LLM dependency: classification must be
reproducible, offline, and cheap enough to re-run over the whole archive.

This flag affects ONLY the News Mood summary shown in the UI and used by news
alert rules. It is never consulted by the ML feature pipeline
(stock_ai/features/news_features.py), so model inputs are unchanged.
"""
from __future__ import annotations

import re

from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.universe import (
    AI_INFRASTRUCTURE,
    AUTONOMOUS_EV,
    DIGITAL_PLATFORM,
    SEMICONDUCTOR_AI_HARDWARE,
    ticker_group,
)

RELEVANT = "relevant"
UNCERTAIN = "uncertain"
NOT_RELEVANT = "not_relevant"

RELEVANCE_STATES = (RELEVANT, UNCERTAIN, NOT_RELEVANT)

# Company names and aliases per ticker, matched case-insensitively.
# Deliberately high-precision: a loose alias here would silently mis-scope a
# mood, which is worse than missing one story.
COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "NVDA": ("nvidia",),
    "AMD": ("advanced micro devices",),
    "MU": ("micron", "micron technology"),
    "TSLA": ("tesla",),
    # Existing saved rows and the watchlist use "IREN"; the company was
    # formerly Iris Energy, which still appears in older coverage.
    "IREN": ("iris energy", "iren limited"),
    "SNDK": ("sandisk",),
    "PONY": ("pony ai", "pony.ai"),
    "RDDT": ("reddit",),
    "APLD": ("applied digital",),
    "SMCI": ("super micro", "supermicro", "super micro computer"),
}

# Brands, products, and people uniquely identifying the company. A story about
# "Blackwell" or "CUDA" is about Nvidia even if it never writes "Nvidia".
BRAND_TERMS: dict[str, tuple[str, ...]] = {
    "NVDA": ("cuda", "blackwell", "geforce", "rtx", "jensen huang", "h100", "h200", "gb200", "grace hopper", "dgx"),
    "AMD": ("ryzen", "radeon", "epyc", "instinct", "lisa su", "mi300", "mi350"),
    "MU": ("crucial", "sanjay mehrotra"),
    "TSLA": ("elon musk", "cybertruck", "model y", "model 3", "full self-driving", "optimus", "gigafactory"),
    "IREN": ("childes",),
    "SMCI": ("charles liang",),
    "RDDT": ("steve huffman",),
}

# Industry vocabulary per peer group -> UNCERTAIN, never RELEVANT on its own.
_INDUSTRY_TERMS: dict[str, tuple[str, ...]] = {
    SEMICONDUCTOR_AI_HARDWARE: (
        "semiconductor",
        "semiconductors",
        "chip",
        "chips",
        "chipmaker",
        "chipmakers",
        "gpu",
        "gpus",
        "ai chip",
        "ai chips",
        "ai accelerator",
        "foundry",
        "wafer",
        "hbm",
        "dram",
        "nand",
        "memory chip",
        "data center",
        "datacenter",
        "ai infrastructure",
    ),
    AI_INFRASTRUCTURE: (
        "data center",
        "datacenter",
        "ai infrastructure",
        "bitcoin mining",
        "crypto mining",
        "hpc",
        "high performance computing",
        "cloud computing",
        "gpu",
        "gpus",
    ),
    AUTONOMOUS_EV: (
        "electric vehicle",
        "electric vehicles",
        "ev maker",
        "ev sales",
        "robotaxi",
        "self-driving",
        "autonomous driving",
        "autonomous vehicle",
    ),
    DIGITAL_PLATFORM: (
        "social media",
        "digital advertising",
        "ad revenue",
        "online platform",
    ),
}


def _boundary(term: str, flags: int = 0) -> re.Pattern[str]:
    # Plain \b is wrong next to "$NVDA" and "pony.ai"; these lookarounds treat
    # only letters/digits as word characters, so punctuation never blocks a match.
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", flags)


def _contains_ci(text: str, term: str) -> bool:
    return _boundary(term, re.IGNORECASE).search(text) is not None


def _contains_symbol(text: str, ticker: str) -> bool:
    """Ticker symbols match case-SENSITIVELY, optionally $-prefixed.

    Short tickers like MU and PONY are ordinary English words in lowercase
    ("mu", "pony"); requiring the uppercase symbol avoids false positives
    without missing real cashtags, which are always written uppercase.
    """
    return _boundary(ticker).search(text) is not None or _boundary(f"${ticker}").search(text) is not None


def company_aliases_for(ticker: str) -> tuple[str, ...]:
    return COMPANY_ALIASES.get(normalize_ticker(ticker), ())


def brand_terms_for(ticker: str) -> tuple[str, ...]:
    return BRAND_TERMS.get(normalize_ticker(ticker), ())


def industry_terms_for(ticker: str) -> tuple[str, ...]:
    return _INDUSTRY_TERMS.get(ticker_group(ticker), ())


def classify_relevance(ticker: str, headline: str | None, summary: str | None = None) -> str:
    """Classify one article for one ticker: RELEVANT, UNCERTAIN, or NOT_RELEVANT.

    Only headline and summary are inspected -- those are the fields every
    provider populates, and a URL slug is too noisy to trust.
    """
    normalized = normalize_ticker(ticker)
    text = " ".join(part for part in (headline or "", summary or "") if part).strip()
    if not text:
        return NOT_RELEVANT

    if _contains_symbol(text, normalized):
        return RELEVANT
    for alias in company_aliases_for(normalized):
        if _contains_ci(text, alias):
            return RELEVANT
    for brand in brand_terms_for(normalized):
        if _contains_ci(text, brand):
            return RELEVANT

    for term in industry_terms_for(normalized):
        if _contains_ci(text, term):
            return UNCERTAIN

    return NOT_RELEVANT


def is_mood_eligible(ticker: str, headline: str | None, summary: str | None = None) -> bool:
    """Whether an article may contribute to this ticker's News Mood.

    Only RELEVANT qualifies: UNCERTAIN articles are industry stories with no
    evidence they concern this company, so they are saved but never counted.
    """
    return classify_relevance(ticker, headline, summary) == RELEVANT
