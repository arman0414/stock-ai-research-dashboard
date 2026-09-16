from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

import stock_ai.data.providers.http as http_module
from stock_ai.data.providers.errors import ProviderError, ProviderRateLimitError


def _http_error(code: int, headers: dict | None = None) -> HTTPError:
    return HTTPError(url="https://example.test", code=code, msg="error", hdrs=headers or {}, fp=None)


def test_retries_and_eventually_succeeds(monkeypatch):
    attempts = {"count": 0}

    def fake_open_url(request):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _http_error(500)
        return io.BytesIO(json.dumps({"ok": True}).encode("utf-8"))

    monkeypatch.setattr(http_module, "_open_url", fake_open_url)
    monkeypatch.setattr(http_module.time, "sleep", lambda seconds: None)

    result = http_module.fetch_json_with_retries(request=object(), max_retries=3, backoff_seconds=0.01)
    assert result == {"ok": True}
    assert attempts["count"] == 3


def test_gives_up_after_max_retries_and_raises_rate_limit_error(monkeypatch):
    def always_rate_limited(request):
        raise _http_error(429)

    monkeypatch.setattr(http_module, "_open_url", always_rate_limited)
    monkeypatch.setattr(http_module.time, "sleep", lambda seconds: None)

    with pytest.raises(ProviderRateLimitError):
        http_module.fetch_json_with_retries(request=object(), max_retries=2, backoff_seconds=0.01)


def test_respects_retry_after_header_in_seconds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(http_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    call_count = {"n": 0}

    def fake_open_url(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _http_error(429, headers={"Retry-After": "5"})
        return io.BytesIO(json.dumps({"ok": True}).encode("utf-8"))

    monkeypatch.setattr(http_module, "_open_url", fake_open_url)

    result = http_module.fetch_json_with_retries(request=object(), max_retries=2, backoff_seconds=1.0)

    assert result == {"ok": True}
    assert sleeps == [5.0]  # used the provider's requested wait, not the exponential-backoff formula


def test_caps_an_excessive_retry_after_value(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(http_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    call_count = {"n": 0}

    def fake_open_url(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _http_error(429, headers={"Retry-After": "999999"})
        return io.BytesIO(json.dumps({"ok": True}).encode("utf-8"))

    monkeypatch.setattr(http_module, "_open_url", fake_open_url)

    http_module.fetch_json_with_retries(request=object(), max_retries=2, backoff_seconds=1.0)

    assert sleeps == [http_module.MAX_RETRY_AFTER_SECONDS]


def test_falls_back_to_exponential_backoff_when_no_retry_after_header(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(http_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    def always_rate_limited(request):
        raise _http_error(429)

    monkeypatch.setattr(http_module, "_open_url", always_rate_limited)

    with pytest.raises(ProviderRateLimitError):
        http_module.fetch_json_with_retries(request=object(), max_retries=2, backoff_seconds=1.0)

    assert sleeps == [1.0, 2.0]  # 1.0 * 2**0, 1.0 * 2**1


def test_non_retryable_http_error_raises_immediately(monkeypatch):
    call_count = {"n": 0}

    def fake_open_url(request):
        call_count["n"] += 1
        raise _http_error(404)

    monkeypatch.setattr(http_module, "_open_url", fake_open_url)

    with pytest.raises(ProviderError):
        http_module.fetch_json_with_retries(request=object(), max_retries=3, backoff_seconds=0.01)

    assert call_count["n"] == 1  # never retried a non-transient client error
