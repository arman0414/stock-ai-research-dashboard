from __future__ import annotations

import json
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from stock_ai.data.providers.errors import ProviderError, ProviderQuotaError, ProviderRateLimitError


def fetch_json_with_retries(request: Request, max_retries: int = 3, backoff_seconds: float = 1.0) -> dict:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with _open_url(request) as response:
                payload = response.read().decode("utf-8")
            if payload.lstrip().startswith("<"):
                raise ProviderError("Provider returned HTML instead of JSON")
            return json.loads(payload)
        except HTTPError as exc:
            if exc.code == 429:
                last_error = ProviderRateLimitError("Provider rate limit reached")
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
        time.sleep(backoff_seconds * (2**attempt))

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

