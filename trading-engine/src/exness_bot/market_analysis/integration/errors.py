"""Stable provider error categories — never leak secrets."""

from __future__ import annotations

import re
from typing import Any

ProviderErrorCategory = str

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer\s+\S+|AIza[0-9A-Za-z_-]{10,})"
)


def sanitize_error_message(category: str, detail: str | None = None) -> str:
    """Return a stable, non-secret error token for logs/API."""
    base = category.strip().upper() or "UNKNOWN_PROVIDER_ERROR"
    if detail:
        cleaned = _SECRET_RE.sub("[REDACTED]", detail)
        if len(cleaned) > 80:
            cleaned = cleaned[:80]
        return f"{base}:{cleaned}"
    return base


def classify_provider_exception(exc: BaseException) -> ProviderErrorCategory:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    combined = f"{name} {msg}"
    if any(x in combined for x in ("auth", "permission", "401", "403", "api key")):
        return "AUTH_ERROR"
    if any(x in combined for x in ("429", "rate limit", "resource_exhausted", "quota")):
        return "RATE_LIMIT"
    if any(x in combined for x in ("timeout", "timed out", "deadline")):
        return "TIMEOUT"
    if any(
        x in combined
        for x in ("model not found", "not found", "unavailable", "404", "deprecated")
    ):
        return "MODEL_UNAVAILABLE"
    if any(x in combined for x in ("network", "connection", "dns", "unreachable")):
        return "NETWORK_ERROR"
    if any(x in combined for x in ("json", "parse", "invalid", "malformed", "decode")):
        return "INVALID_RESPONSE"
    return "UNKNOWN_PROVIDER_ERROR"


def redact_secrets(text: str, *, fake_secret: str | None = None) -> str:
    out = _SECRET_RE.sub("[REDACTED]", text or "")
    if fake_secret and fake_secret in out:
        out = out.replace(fake_secret, "[REDACTED]")
    return out


def assert_no_secret(payload: Any, secret: str) -> None:
    blob = str(payload)
    if secret and secret in blob:
        raise AssertionError("secret leaked into serialized payload")
