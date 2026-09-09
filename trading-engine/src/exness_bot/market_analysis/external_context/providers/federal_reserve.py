"""Federal Reserve official public feeds (RSS/XML) — no scraping / automation."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from exness_bot.market_analysis.external_context.providers.base import (
    ExternalDataItem,
    ExternalDataProviderResult,
    ProviderFetchStatus,
    ProviderHealth,
)
from exness_bot.market_analysis.external_context.providers.feed_parse import (
    classify_fed_tone,
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

# Official Federal Reserve feeds (documented public endpoints).
FED_FEEDS: tuple[tuple[str, str, str], ...] = (
    (
        "press_monetary",
        "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "monetary_policy",
    ),
    (
        "speeches",
        "https://www.federalreserve.gov/feeds/speeches.xml",
        "speech",
    ),
    (
        "press_all",
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "press_release",
    ),
)

DEFAULT_TTL_SECONDS = 10 * 60  # 5-15 minutes


class FederalReserveProvider:
    name = "federal_reserve"

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 20.0,
        feeds: tuple[tuple[str, str, str], ...] | None = None,
        http_get_bytes: Any | None = None,
        max_items_per_feed: int = 15,
    ) -> None:
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._feeds = feeds or FED_FEEDS
        self._http_get_bytes = http_get_bytes or (
            lambda url: http_get(url, timeout=self._timeout)[1]
        )
        self._max_items = max_items_per_feed
        self._last_success_at: str | None = None
        self._last_status: str = "IDLE"
        self._last_item_count: int | None = None

    @property
    def configured(self) -> bool:
        return True

    @property
    def ttl_seconds(self) -> int:
        return DEFAULT_TTL_SECONDS

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

        t0 = time.perf_counter()
        collected: list[tuple[str, Any]] = []
        errors: list[str] = []
        last_category: str | None = None

        for feed_id, url, category in self._feeds:
            safe_url = normalize_url(url)
            if safe_url is None:
                continue
            try:
                raw = self._http_get_bytes(safe_url)
                entries = parse_feed_xml(
                    raw, default_category=category, max_entries=self._max_items
                )
                for e in entries:
                    collected.append((feed_id, e))
            except ValueError:
                last_category = ProviderFetchStatus.INVALID_RESPONSE.value
                errors.append(f"{feed_id}:malformed")
            except Exception as exc:
                last_category = map_http_exception(exc)
                errors.append(f"{feed_id}:{type(exc).__name__}")

        entries_only = dedupe_feed_entries([e for _, e in collected])
        cat_by_link: dict[str, str | None] = {}
        for _feed_id, e in collected:
            if e.link not in cat_by_link:
                cat_by_link[e.link] = e.category

        items: list[ExternalDataItem] = []
        for e in entries_only:
            items.append(
                ExternalDataItem(
                    provider="federal_reserve",
                    source_type="OFFICIAL",
                    title=e.title,
                    value=e.title,
                    published_at=e.published_at,
                    retrieved_at=retrieved_at,
                    canonical_url=e.link,
                    freshness=freshness_for(e.published_at, now=now),
                    category=cat_by_link.get(e.link) or e.category,
                    metadata={"tone": classify_fed_tone(e.title)},
                )
            )

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
            error_detail=";".join(errors) or "no_feed_items",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            retrieved_at=retrieved_at,
        )
