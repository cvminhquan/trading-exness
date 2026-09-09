"""In-memory provider result cache with per-provider TTL."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from exness_bot.market_analysis.external_context.providers.base import (
    ExternalDataProviderResult,
)


@dataclass
class CachedProviderResult:
    result: ExternalDataProviderResult
    stored_at: datetime
    expires_at: datetime


class ProviderResultCache:
    """Cache raw provider fetches — independent of quote ticks / M15 fingerprint."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, CachedProviderResult] = {}

    def get(
        self, provider: str, *, now: datetime
    ) -> tuple[ExternalDataProviderResult | None, bool]:
        ref = now if now.tzinfo else now.replace(tzinfo=UTC)
        with self._lock:
            entry = self._entries.get(provider)
            if entry is None:
                return None, False
            if ref >= entry.expires_at:
                return None, False
            return entry.result, True

    def put(
        self,
        provider: str,
        result: ExternalDataProviderResult,
        *,
        now: datetime,
        ttl_seconds: int,
    ) -> None:
        ref = now if now.tzinfo else now.replace(tzinfo=UTC)
        ttl = max(1, int(ttl_seconds))
        with self._lock:
            self._entries[provider] = CachedProviderResult(
                result=result,
                stored_at=ref,
                expires_at=ref + timedelta(seconds=ttl),
            )

    def status(self, provider: str, *, now: datetime) -> dict[str, Any]:
        ref = now if now.tzinfo else now.replace(tzinfo=UTC)
        with self._lock:
            entry = self._entries.get(provider)
            if entry is None:
                return {"cached": False}
            valid = ref < entry.expires_at
            return {
                "cached": True,
                "valid": valid,
                "stored_at": entry.stored_at.isoformat(),
                "expires_at": entry.expires_at.isoformat(),
                "item_count": len(entry.result.items),
                "status": entry.result.status,
            }
