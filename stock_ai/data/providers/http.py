from __future__ import annotations

import json
import ssl
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from stock_ai.data.providers.errors import ProviderError, ProviderQuotaError, ProviderRateLimitError


MAX_RETRY_AFTER_SECONDS = 60.0  # never let a provider's Retry-After stall the whole daily cycle indefinitely


def _retry_after_seconds(exc: HTTPError) -> float | None:
    """Reads the standard Retry-After header (seconds, or an HTTP-date) off
    a 429 response, if the provider sent one. Returns None if absent or
    unparseable -- callers fall back to their own exponential backoff."""
    header = exc.headers.get("Retry-After") if exc.headers is not None else None
    if not header:
        return None
    try:
        return max(0.0, min(float(header), MAX_RETRY_AFTER_SECONDS))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        retry_at = parsedate_to_datetime(header)
        if retry_at is None:
            return None
        from datetime import datetime, timezone

        delta = (retry_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, min(delta, MAX_RETRY_AFTER_SECONDS))
    except (TypeError, ValueError):
        return None


def fetch_json_with_retries(request: Request, max_retries: int = 3, backoff_seconds: float = 1.0) -> Any:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        retry_after: float | None = None
        try:
            with _open_url(request) as response:
                payload = response.read().decode("utf-8")
            if payload.lstrip().startswith("<"):
                raise ProviderError("Provider returned HTML instead of JSON")
            return json.loads(payload)
        except HTTPError as exc:
            if exc.code == 429:
                last_error = ProviderRateLimitError("Provider rate limit reached")
                retry_after = _retry_after_seconds(exc)
            elif 500 <= exc.code < 600:
                last_error = ProviderError(f"Transient provider HTTP error: {exc.code}")
            else:
                raise ProviderError(f"Provider HTTP error: {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            last_error = ProviderError(f"Provider network error: {exc}")
        except json.JSONDecodeError as exc:
            raise ProviderError("Provider returned malformed JSON") from exc

        if attempt >= max_retries:
            break
        # Respect the provider's own requested wait time when it gives one
        # (e.g. Retry-After on a 429); otherwise fall back to exponential
        # backoff. Never blindly hammer a rate-limited endpoint.
        time.sleep(retry_after if retry_after is not None else backoff_seconds * (2**attempt))

    if isinstance(last_error, ProviderRateLimitError):
        raise last_error
    raise ProviderError(str(last_error or "Provider request failed"))


def detect_quota_message(payload: dict) -> None:
    text = " ".join(str(value) for value in payload.values()).lower()
    if "quota" in text or "api call frequency" in text or "rate limit" in text:
        raise ProviderQuotaError(text)


def _open_url(request: Request):
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    try:
        return urlopen(request, timeout=30, context=context)
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        return urlopen(request, timeout=30, context=ssl._create_unverified_context())
