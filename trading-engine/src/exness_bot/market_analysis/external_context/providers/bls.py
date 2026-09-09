"""BLS Public Data API provider (zero-key mode supported)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from exness_bot.market_analysis.external_context.macro_models import BLS_SERIES
from exness_bot.market_analysis.external_context.providers.base import (
    ExternalDataItem,
    ExternalDataProviderResult,
    ProviderFetchStatus,
    ProviderHealth,
)
from exness_bot.market_analysis.external_context.providers.http_util import (
    map_http_exception,
)
from exness_bot.market_analysis.external_context.providers.provenance import (
    freshness_for,
)

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_SERIES_PAGE = "https://www.bls.gov/data/"
DEFAULT_TTL_SECONDS = 6 * 3600  # macro: hours


def _period_to_iso(year: str, period: str) -> str | None:
    """Map BLS year+period (M01..M12 or M13 annual) to month-end-ish ISO date.

    published_at is the observation period date — never invented from retrieve time.
    """
    y = year.strip()
    p = period.strip().upper()
    if not y.isdigit() or len(y) != 4:
        return None
    if p.startswith("M") and len(p) == 3 and p[1:].isdigit():
        month = int(p[1:])
        if month == 13:
            # Annual average — use Dec 31 of that year
            return f"{y}-12-31T00:00:00+00:00"
        if 1 <= month <= 12:
            return f"{y}-{month:02d}-01T00:00:00+00:00"
    if p.startswith("Q") and len(p) == 2 and p[1:].isdigit():
        q = int(p[1:])
        if 1 <= q <= 4:
            month = (q - 1) * 3 + 1
            return f"{y}-{month:02d}-01T00:00:00+00:00"
    return None


def parse_bls_payload(
    payload: dict[str, Any],
    *,
    retrieved_at: str,
    now: datetime,
) -> list[ExternalDataItem]:
    """Parse BLS v2 JSON into ExternalDataItem list (testable pure function)."""
    items: list[ExternalDataItem] = []
    results = payload.get("Results") or {}
    series_list = results.get("series") or []
    if not isinstance(series_list, list):
        return items

    for series in series_list:
        if not isinstance(series, dict):
            continue
        series_id = str(series.get("seriesID") or "").strip()
        meta = BLS_SERIES.get(series_id)
        if meta is None:
            # Ignore undocumented / unexpected series — never invent meaning
            continue
        data_points = series.get("data") or []
        if not isinstance(data_points, list) or not data_points:
            continue
        # BLS returns newest first
        latest = data_points[0] if isinstance(data_points[0], dict) else None
        prev = (
            data_points[1]
            if len(data_points) > 1 and isinstance(data_points[1], dict)
            else None
        )
        if latest is None:
            continue
        try:
            value = float(str(latest.get("value")))
        except (TypeError, ValueError):
            continue
        year = str(latest.get("year") or "")
        period = str(latest.get("period") or "")
        published_at = _period_to_iso(year, period)
        prev_value: float | None = None
        if prev is not None:
            try:
                prev_value = float(str(prev.get("value")))
            except (TypeError, ValueError):
                prev_value = None
        items.append(
            ExternalDataItem(
                provider="bls",
                source_type="MARKET_DATA",
                title=meta["name"],
                value=value,
                published_at=published_at,
                retrieved_at=retrieved_at,
                canonical_url=f"{BLS_SERIES_PAGE}?series={series_id}",
                freshness=freshness_for(published_at, now=now),
                category=meta["category"],
                series_id=series_id,
                unit=meta.get("unit"),
                metadata={
                    "year": year,
                    "period": period,
                    "periodName": latest.get("periodName"),
                    "previous_value": prev_value,
                },
            )
        )
    return items


class BlsProvider:
    """Official BLS Public Data API — works without registration key (lower limits)."""

    name = "bls"

    def __init__(
        self,
        *,
        enabled: bool = True,
        api_key: str = "",
        timeout_seconds: float = 20.0,
        series_ids: list[str] | None = None,
        http_post: Any | None = None,
    ) -> None:
        self._enabled = enabled
        self._api_key = (api_key or "").strip()
        self._timeout = timeout_seconds
        self._series_ids = list(series_ids or BLS_SERIES.keys())
        self._http_post = http_post or self._default_post
        self._last_success_at: str | None = None
        self._last_status: str = "IDLE"
        self._last_item_count: int | None = None

    @property
    def configured(self) -> bool:
        # Zero-key mode is supported — always "configured" when enabled
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
            detail="zero_key_mode" if not self._api_key else "registered_key_mode",
        )

    def _default_post(self, body: dict[str, Any]) -> dict[str, Any]:
        raw_body = json.dumps(body).encode("utf-8")
        req = Request(
            BLS_API_URL,
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "exness-bot-external-context/16.3.7 (read-only)",
            },
            method="POST",
        )
        with urlopen(req, timeout=self._timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            raw = resp.read(2_000_000)
            if status >= 400:
                raise HTTPError(BLS_API_URL, status, f"http_{status}", hdrs=None, fp=None)  # type: ignore[arg-type]
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("bls_json_not_object")
            return data

    def fetch(self, *, now: datetime) -> ExternalDataProviderResult:
        retrieved_at = (now if now.tzinfo else now.replace(tzinfo=UTC)).isoformat()
        if not self._enabled:
            self._last_status = ProviderFetchStatus.DISABLED.value
            return ExternalDataProviderResult(
                provider=self.name,
                status=ProviderFetchStatus.DISABLED.value,
                retrieved_at=retrieved_at,
            )

        body: dict[str, Any] = {
            "seriesid": self._series_ids,
            "startyear": str(now.year - 2),
            "endyear": str(now.year),
        }
        # Optional registered key — never log this field
        if self._api_key:
            body["registrationkey"] = self._api_key

        t0 = time.perf_counter()
        try:
            payload = self._http_post(body)
            status_text = str(payload.get("status") or "")
            no_series = not (payload.get("Results") or {}).get("series")
            if status_text and "REQUEST_SUCCEEDED" not in status_text.upper() and no_series:
                self._last_status = ProviderFetchStatus.INVALID_RESPONSE.value
                return ExternalDataProviderResult(
                    provider=self.name,
                    status=ProviderFetchStatus.INVALID_RESPONSE.value,
                    error_category=ProviderFetchStatus.INVALID_RESPONSE.value,
                    error_detail=status_text[:200] or "bls_request_not_succeeded",
                    latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                    retrieved_at=retrieved_at,
                )
            items = parse_bls_payload(payload, retrieved_at=retrieved_at, now=now)
            if not items:
                self._last_status = ProviderFetchStatus.INVALID_RESPONSE.value
                return ExternalDataProviderResult(
                    provider=self.name,
                    status=ProviderFetchStatus.INVALID_RESPONSE.value,
                    error_category=ProviderFetchStatus.INVALID_RESPONSE.value,
                    error_detail="no_documented_series_observations",
                    latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                    retrieved_at=retrieved_at,
                )
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
        except Exception as exc:
            category = map_http_exception(exc)
            self._last_status = category
            return ExternalDataProviderResult(
                provider=self.name,
                status=category,
                error_category=category,
                error_detail=type(exc).__name__,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                retrieved_at=retrieved_at,
            )
