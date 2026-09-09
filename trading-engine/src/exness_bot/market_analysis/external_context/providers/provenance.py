"""Freshness helpers for free-source items."""

from __future__ import annotations

from datetime import UTC, datetime

from exness_bot.market_analysis.external_context.freshness import (
    classify_external_freshness,
)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def freshness_for(published_at: str | None, *, now: datetime) -> str:
    pub = parse_iso_datetime(published_at)
    return classify_external_freshness(pub, now=now).value
