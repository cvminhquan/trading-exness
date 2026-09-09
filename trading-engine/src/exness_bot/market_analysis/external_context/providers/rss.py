"""Allowlisted RSS/Atom provider — no user-supplied URLs."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from exness_bot.market_analysis.external_context.providers.base import (
    ExternalDataItem,
    ExternalDataProviderResult,
    ProviderFetchStatus,
    ProviderHealth,
)
from exness_bot.market_analysis.external_context.providers.feed_parse import (
    dedupe_feed_entries,
    parse_feed_xml,
)
from exness_bot.market_analysis.external_context.providers.http_util import (
    http_get,
    map_http_exception,
)
from exness_bot.market_analysis.external_context.providers.provenance import (
    freshness_for,
)
from exness_bot.market_analysis.external_context.sources import normalize_url

# Official / public feeds only — never add random financial blogs silently.
DEFAULT_RSS_ALLOWLIST: tuple[str, ...] = (
    # Official Federal Reserve monetary press feed (allowlist demonstration;
    # FederalReserveProvider also consumes Fed feeds — composite dedupes URLs).
    "https://www.federalreserve.gov/feeds/press_monetary.xml",
)

DEFAULT_TTL_SECONDS = 10 * 60
_BLOCKED_SCHEMES = frozenset({"javascript", "file", "data", "vbscript"})


def is_url_safe_for_rss(url: str, *, allowlist: set[str]) -> bool:
    """Reject non-allowlisted and unsafe schemes. HTTP/HTTPS only."""
    normalized = normalize_url(url)
    if normalized is None:
        return False
    parsed = urlparse(normalized)
    if parsed.scheme.lower() in _BLOCKED_SCHEMES:
        return False
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    # Allowlist match on normalized URL
    allowed_norm = {normalize_url(u) for u in allowlist}
    allowed_norm.discard(None)
    return normalized in allowed_norm


class RssProvider:
    name = "rss"

    def __init__(
        self,
        *,
        enabled: bool = True,
        allowlist: tuple[str, ...] | list[str] | None = None,
        timeout_seconds: float = 15.0,
        http_get_bytes: Any | None = None,
        max_items_per_feed: int = 20,
    ) -> None:
        self._enabled = enabled
        raw_list = tuple(allowlist) if allowlist is not None else DEFAULT_RSS_ALLOWLIST
        self._allowlist = tuple(
            u for u in (normalize_url(x) for x in raw_list) if u is not None
        )
        self._allowset = set(self._allowlist)
        self._timeout = timeout_seconds
        self._http_get_bytes = http_get_bytes or (
            lambda url: http_get(url, timeout=self._timeout)[1]
        )
        self._max_items = max_items_per_feed
        self._last_success_at: str | None = None
        self._last_status: str = "IDLE"
        self._last_item_count: int | None = None

    @property
    def configured(self) -> bool:
        return bool(self._allowlist)

    @property
    def ttl_seconds(self) -> int:
        return DEFAULT_TTL_SECONDS

    @property
    def feeds(self) -> tuple[str, ...]:
        return self._allowlist

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            enabled=self._enabled,
            configured=self.configured,
            status=(
                ProviderFetchStatus.DISABLED.value
                if not self._enabled
                else self._last_status
            ),
            last_success_at=self._last_success_at,
            item_count=self._last_item_count,
            detail=f"feeds={len(self._allowlist)}",
        )

    def fetch(self, *, now: datetime) -> ExternalDataProviderResult:
        retrieved_at = (now if now.tzinfo else now.replace(tzinfo=UTC)).isoformat()
        if not self._enabled:
            self._last_status = ProviderFetchStatus.DISABLED.value
            return ExternalDataProviderResult(
                provider=self.name,
                status=ProviderFetchStatus.DISABLED.value,
                retrieved_at=retrieved_at,
            )
        if not self._allowlist:
            self._last_status = ProviderFetchStatus.NOT_CONFIGURED.value
            return ExternalDataProviderResult(
                provider=self.name,
                status=ProviderFetchStatus.NOT_CONFIGURED.value,
                error_category=ProviderFetchStatus.NOT_CONFIGURED.value,
                error_detail="empty_allowlist",
                retrieved_at=retrieved_at,
            )

        t0 = time.perf_counter()
        all_entries = []
        errors: list[str] = []
        last_category: str | None = None

        for feed_url in self._allowlist:
            if not is_url_safe_for_rss(feed_url, allowlist=self._allowset):
                errors.append("rejected_unsafe_url")
                continue
            try:
                raw = self._http_get_bytes(feed_url)
                entries = parse_feed_xml(raw, max_entries=self._max_items)
                all_entries.extend(entries)
            except ValueError:
                last_category = ProviderFetchStatus.INVALID_RESPONSE.value
                errors.append("malformed_xml")
            except Exception as exc:
                last_category = map_http_exception(exc)
                errors.append(type(exc).__name__)

        entries = dedupe_feed_entries(all_entries)
        items = [
            ExternalDataItem(
                provider="rss",
                source_type="OFFICIAL",
                title=e.title,
                value=e.title,
                published_at=e.published_at,
                retrieved_at=retrieved_at,
                canonical_url=e.link,
                freshness=freshness_for(e.published_at, now=now),
                category=e.category or "rss",
            )
            for e in entries
        ]

        if items:
            self._last_status = ProviderFetchStatus.OK.value
            self._last_success_at = retrieved_at
            self._last_item_count = len(items)
            return ExternalDataProviderResult(
                provider=self.name,
                status=ProviderFetchStatus.OK.value,
                items=items,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                retrieved_at=retrieved_at,
                error_detail=";".join(errors) if errors else None,
            )

        category = last_category or ProviderFetchStatus.UPSTREAM_UNAVAILABLE.value
        self._last_status = category
        return ExternalDataProviderResult(
            provider=self.name,
            status=category,
            error_category=category,
            error_detail=";".join(errors) or "no_items",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            retrieved_at=retrieved_at,
        )
