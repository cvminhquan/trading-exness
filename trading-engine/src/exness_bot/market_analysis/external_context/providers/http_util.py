"""HTTP helpers for free external providers — timeouts, size limits, no secrets."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from exness_bot.market_analysis.external_context.providers.base import (
    ProviderFetchStatus,
)
from exness_bot.market_analysis.integration.errors import classify_provider_exception

DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_BODY_BYTES = 2_000_000


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_BODY_BYTES,
) -> tuple[int, bytes]:
    req = Request(
        url,
        headers={
            "User-Agent": "exness-bot-external-context/16.3.7 (read-only)",
            "Accept": "*/*",
            **(headers or {}),
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout) as resp:
        status = int(getattr(resp, "status", 200) or 200)
        raw = resp.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("response_too_large")
        return status, raw


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    status, raw = http_get(url, headers=headers, timeout=timeout)
    if status >= 400:
        raise RuntimeError(f"http_{status}")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("json_not_object")
    return data


def map_http_exception(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return ProviderFetchStatus.TIMEOUT.value
    if isinstance(exc, HTTPError):
        if exc.code in {401, 403}:
            return ProviderFetchStatus.AUTH_ERROR.value
        if exc.code == 429:
            return ProviderFetchStatus.RATE_LIMIT.value
        return ProviderFetchStatus.UPSTREAM_UNAVAILABLE.value
    if isinstance(exc, URLError):
        return ProviderFetchStatus.NETWORK_ERROR.value
    category = classify_provider_exception(exc)
    mapping = {
        "AUTH_ERROR": ProviderFetchStatus.AUTH_ERROR.value,
        "RATE_LIMIT": ProviderFetchStatus.RATE_LIMIT.value,
        "TIMEOUT": ProviderFetchStatus.TIMEOUT.value,
        "NETWORK_ERROR": ProviderFetchStatus.NETWORK_ERROR.value,
        "INVALID_RESPONSE": ProviderFetchStatus.INVALID_RESPONSE.value,
        "MODEL_UNAVAILABLE": ProviderFetchStatus.UPSTREAM_UNAVAILABLE.value,
    }
    return mapping.get(category, ProviderFetchStatus.UNKNOWN_PROVIDER_ERROR.value)
