from __future__ import annotations

import re
import string
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from stock_ai.data.providers.news.base import NormalizedArticle

_PUBLISHER_SUFFIXES = (
    "reuters",
    "bloomberg",
    "cnbc",
    "yahoo finance",
    "marketwatch",
    "seeking alpha",
    "the motley fool",
    "investor's business daily",
)

_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"cmpid", "guccounter", "ncid", "ref", "source", "src"}


def canonical_url_key(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower() or None
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+$", "", parsed.path or "/")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS and not key.lower().startswith(_TRACKING_QUERY_PREFIXES)
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((parsed.scheme.lower() or "https", netloc, path, query, "")).lower()


def normalized_headline_key(headline: str | None) -> str | None:
    if not headline:
        return None
    value = headline.strip().lower()
    for separator in (" - ", " | ", " — "):
        if separator in value:
            base, suffix = value.rsplit(separator, 1)
            if suffix.strip() in _PUBLISHER_SUFFIXES:
                value = base
                break
    value = value.translate(str.maketrans("", "", string.punctuation))
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def deduplicate_articles(articles: list[NormalizedArticle]) -> list[NormalizedArticle]:
    unique: list[NormalizedArticle] = []
    by_url: dict[tuple[str, str], int] = {}
    by_provider_id: dict[tuple[str, str, str], int] = {}
    by_headline: dict[tuple[str, str], int] = {}

    for article in sorted(articles, key=lambda item: item.published_at, reverse=True):
        ticker = article.ticker.upper()
        url_key = canonical_url_key(article.url)
        headline_key = normalized_headline_key(article.headline)
        provider_id_key = (ticker, article.provider, article.external_id)

        existing_index: int | None = None
        if url_key and (ticker, url_key) in by_url:
            existing_index = by_url[(ticker, url_key)]
        elif provider_id_key in by_provider_id:
            existing_index = by_provider_id[provider_id_key]
        elif headline_key and (ticker, headline_key) in by_headline:
            candidate = unique[by_headline[(ticker, headline_key)]]
            if _same_story_window(candidate, article):
                existing_index = by_headline[(ticker, headline_key)]

        if existing_index is None:
            index = len(unique)
            sources = tuple(dict.fromkeys((*(article.provider_sources or ()), article.provider)))
            unique.append(replace(article, provider_sources=sources))
            if url_key:
                by_url[(ticker, url_key)] = index
            by_provider_id[provider_id_key] = index
            if headline_key:
                by_headline[(ticker, headline_key)] = index
            continue

        merged = _merge_duplicate(unique[existing_index], article)
        unique[existing_index] = merged
        if url_key:
            by_url[(ticker, url_key)] = existing_index
        by_provider_id[provider_id_key] = existing_index
        if headline_key:
            by_headline[(ticker, headline_key)] = existing_index

    return sorted(unique, key=lambda item: item.published_at)


def _same_story_window(first: NormalizedArticle, second: NormalizedArticle) -> bool:
    if first.source and second.source and first.source.strip().lower() != second.source.strip().lower():
        return False
    delta_seconds = abs((first.published_at - second.published_at).total_seconds())
    return delta_seconds <= 36 * 60 * 60


def _merge_duplicate(existing: NormalizedArticle, duplicate: NormalizedArticle) -> NormalizedArticle:
    providers = tuple(dict.fromkeys((*(existing.provider_sources or (existing.provider,)), *(duplicate.provider_sources or (duplicate.provider,)))))
    return replace(
        existing,
        summary=existing.summary or duplicate.summary,
        source=existing.source or duplicate.source,
        author=existing.author or duplicate.author,
        provider_sources=providers,
    )

