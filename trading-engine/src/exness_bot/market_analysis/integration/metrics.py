"""Phase 16.3.6 — sanitized in-process observability counters.

Never stores secrets. Process-local only.
"""

from __future__ import annotations

from threading import Lock
from typing import Any


class IntegrationMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[str, int] = {
            "external_provider_calls": 0,
            "external_cache_hits": 0,
            "external_cache_misses": 0,
            "synthesis_provider_calls": 0,
            "synthesis_cache_hits": 0,
            "synthesis_cache_misses": 0,
            "analyst_chat_provider_calls": 0,
            "analyst_chat_fallbacks": 0,
        }

    def inc(self, key: str, n: int = 1) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + n

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def reset(self) -> None:
        with self._lock:
            for k in list(self._counts):
                self._counts[k] = 0


_METRICS = IntegrationMetrics()


def get_integration_metrics() -> IntegrationMetrics:
    return _METRICS


def metrics_snapshot() -> dict[str, Any]:
    return get_integration_metrics().snapshot()
