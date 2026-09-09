"""FRED API provider — OPTIONAL; requires API key; never required for startup."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from exness_bot.market_analysis.external_context.macro_models import FRED_SERIES
from exness_bot.market_analysis.external_context.providers.base import (
    ExternalDataItem,
    ExternalDataProviderResult,
    ProviderFetchStatus,
    ProviderHealth,
)
from exness_bot.market_analysis.external_context.providers.http_util import (
    http_get_json,
    map_http_exception,
)
from exness_bot.market_analysis.external_context.providers.provenance import (
    freshness_for,
)

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES_PAGE = "https://fred.stlouisfed.org/series/"
DEFAULT_TTL_SECONDS = 3600  # observations: ~1 hour


def redact_secrets(text: str, api_key: str) -> str:
    """Remove API key material from any string (logs/errors)."""
    if not api_key:
        return text
    return text.replace(api_key, "[REDACTED]")


def parse_fred_observations(
    payload: dict[str, Any],
    *,
    series_id: str,
    retrieved_at: str,
    now: datetime,
) -> ExternalDataItem | None:
    meta = FRED_SERIES.get(series_id)
    if meta is None:
        return None
    observations = payload.get("observations") or []
    if not isinstance(observations, list):
        return None
    # Keep chronological valid observations (API usually returns ascending)
    usable: list[dict[str, Any]] = []
    for row in observations:
        if not isinstance(row, dict):
            continue
        val = row.get("value")
        if val is None or str(val).strip() in {"", "."}:
            continue
        usable.append(row)
    if not usable:
        return None
    latest = usable[-1]
    prev = usable[-2] if len(usable) >= 2 else None
    try:
        value = float(str(latest.get("value")))
    except (TypeError, ValueError):
        return None
    date_str = str(latest.get("date") or "").strip()
    published_at = f"{date_str}T00:00:00+00:00" if date_str else None
    prev_value: float | None = None
    if prev is not None:
        try:
            prev_value = float(str(prev.get("value")))
        except (TypeError, ValueError):
            prev_value = None
    return ExternalDataItem(
        provider="fred",
        source_type="MARKET_DATA",
        title=meta["name"],
        value=value,
        published_at=published_at,
        retrieved_at=retrieved_at,
        canonical_url=f"{FRED_SERIES_PAGE}{series_id}",
        freshness=freshness_for(published_at, now=now),
        category=meta["category"],
        series_id=series_id,
        unit=meta.get("unit"),
        metadata={"previous_value": prev_value},
    )


class FredProvider:
    name = "fred"

    def __init__(
        self,
        *,
        enabled: bool = False,
        api_key: str = "",
        timeout_seconds: float = 20.0,
        series_ids: list[str] | None = None,
        http_get: Any | None = None,
    ) -> None:
        self._enabled = enabled
        self._api_key = (api_key or "").strip()
        self._timeout = timeout_seconds
        self._series_ids = list(series_ids or FRED_SERIES.keys())
        self._http_get = http_get or (
            lambda url: http_get_json(url, timeout=self._timeout)
        )
        self._last_success_at: str | None = None
        self._last_status: str = "IDLE"
        self._last_item_count: int | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def ttl_seconds(self) -> int:
        return DEFAULT_TTL_SECONDS

    def health(self) -> ProviderHealth:
        if not self._enabled:
            status = ProviderFetchStatus.DISABLED.value
        elif not self._api_key:
            status = ProviderFetchStatus.NOT_CONFIGURED.value
        else:
            status = self._last_status
        return ProviderHealth(
            provider=self.name,
            enabled=self._enabled,
            configured=self.configured,
            status=status,
            last_success_at=self._last_success_at,
            item_count=self._last_item_count,
            detail=None if self.configured else "FRED_API_KEY missing",
        )

    def _build_url(self, series_id: str) -> str:
        # Key in query — never log this URL
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "asc",
            "limit": "24",
        }
        return f"{FRED_OBSERVATIONS_URL}?{urlencode(params)}"

    def fetch(self, *, now: datetime) -> ExternalDataProviderResult:
        retrieved_at = (now if now.tzinfo else now.replace(tzinfo=UTC)).isoformat()
        if not self._enabled:
            self._last_status = ProviderFetchStatus.DISABLED.value
            return ExternalDataProviderResult(
                provider=self.name,
                status=ProviderFetchStatus.DISABLED.value,
                retrieved_at=retrieved_at,
            )
        if not self._api_key:
            self._last_status = ProviderFetchStatus.NOT_CONFIGURED.value
            return ExternalDataProviderResult(
                provider=self.name,
                status=ProviderFetchStatus.NOT_CONFIGURED.value,
                error_category=ProviderFetchStatus.NOT_CONFIGURED.value,
                error_detail="FRED_API_KEY missing",
                retrieved_at=retrieved_at,
            )

        t0 = time.perf_counter()
        items: list[ExternalDataItem] = []
        last_error: str | None = None
        last_category: str | None = None
        for series_id in self._series_ids:
            if series_id not in FRED_SERIES:
                continue
            try:
                url = self._build_url(series_id)
                payload = self._http_get(url)
                item = parse_fred_observations(
                    payload,
                    series_id=series_id,
                    retrieved_at=retrieved_at,
                    now=now,
                )
                if item is not None:
                    items.append(item)
            except Exception as exc:
                last_category = map_http_exception(exc)
                # Never include key in error detail
                last_error = redact_secrets(type(exc).__name__, self._api_key)
                continue

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
            )

        category = last_category or ProviderFetchStatus.UPSTREAM_UNAVAILABLE.value
        self._last_status = category
        return ExternalDataProviderResult(
            provider=self.name,
            status=category,
            error_category=category,
            error_detail=last_error or "no_observations",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            retrieved_at=retrieved_at,
        )
