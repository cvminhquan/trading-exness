"""Shared free-source provider contract (read-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class ProviderFetchStatus(StrEnum):
    OK = "OK"
    DISABLED = "DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


@dataclass
class ExternalDataItem:
    provider: str
    source_type: str
    title: str
    value: str | float | None
    published_at: str | None
    retrieved_at: str
    canonical_url: str | None
    freshness: str
    category: str | None = None
    series_id: str | None = None
    unit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExternalDataProviderResult:
    provider: str
    status: str
    items: list[ExternalDataItem] = field(default_factory=list)
    error_category: str | None = None
    error_detail: str | None = None
    latency_ms: float | None = None
    retrieved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "item_count": len(self.items),
            "error_category": self.error_category,
            "error_detail": self.error_detail,
            "latency_ms": self.latency_ms,
            "retrieved_at": self.retrieved_at,
        }


@dataclass
class ProviderHealth:
    provider: str
    enabled: bool
    configured: bool
    status: str
    last_success_at: str | None = None
    cache_hit: bool | None = None
    item_count: int | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "configured": self.configured,
            "status": self.status,
            "last_success_at": self.last_success_at,
            "cache_hit": self.cache_hit,
            "item_count": self.item_count,
            "detail": self.detail,
        }


class ExternalDataProvider(Protocol):
    name: str

    def fetch(self, *, now: datetime) -> ExternalDataProviderResult: ...

    def health(self) -> ProviderHealth: ...
