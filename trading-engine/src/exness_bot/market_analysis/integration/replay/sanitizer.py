"""Sanitizer for OPTIONAL future real-response capture.

Never auto-capture. Strips secrets and oversized bodies.
"""

from __future__ import annotations

from typing import Any

from exness_bot.market_analysis.integration.errors import redact_secrets

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set-cookie",
        "password",
        "token",
        "access_token",
        "refresh_token",
    }
)


def sanitize_provider_payload(
    payload: dict[str, Any],
    *,
    max_text_chars: int = 4000,
) -> dict[str, Any]:
    """Return a fixture-safe copy of a provider-like dict."""

    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                key = str(k)
                if key.lower() in _SENSITIVE_KEYS:
                    out[key] = "[REDACTED]"
                    continue
                out[key] = _walk(v)
            return out
        if isinstance(obj, list):
            return [_walk(v) for v in obj]
        if isinstance(obj, str):
            text = redact_secrets(obj)
            if len(text) > max_text_chars:
                return text[:max_text_chars] + "…"
            return text
        return obj

    cleaned = _walk(payload)
    return cleaned if isinstance(cleaned, dict) else {}
