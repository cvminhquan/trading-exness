"""Classify live quote freshness for Dashboard (LIVE / STALE / UNAVAILABLE)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum


class QuoteFreshness(StrEnum):
    LIVE = "LIVE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


def classify_quote_freshness(
    *,
    available: bool,
    tick_time: datetime | None,
    now: datetime | None = None,
    stale_after_seconds: int = 10,
) -> QuoteFreshness:
    """Return freshness from tick time. Never treat missing ticks as LIVE."""
    if not available or tick_time is None:
        return QuoteFreshness.UNAVAILABLE
    current = now or datetime.now(tz=UTC)
    aware = tick_time if tick_time.tzinfo is not None else tick_time.replace(tzinfo=UTC)
    age = current.astimezone(UTC) - aware.astimezone(UTC)
    if age > timedelta(seconds=stale_after_seconds):
        return QuoteFreshness.STALE
    return QuoteFreshness.LIVE
