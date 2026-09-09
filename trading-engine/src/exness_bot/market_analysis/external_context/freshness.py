"""External content freshness windows (not candle freshness)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from exness_bot.market_analysis.external_context.models import ExternalFreshness

BREAKING_MAX = timedelta(hours=2)
RECENT_MAX = timedelta(hours=24)
CURRENT_MAX = timedelta(hours=72)


def classify_external_freshness(
    published_at: datetime | None,
    *,
    now: datetime,
) -> ExternalFreshness:
    if published_at is None:
        return ExternalFreshness.UNDATED
    pub = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    ref = now if now.tzinfo else now.replace(tzinfo=UTC)
    age = ref - pub.astimezone(UTC)
    if age < timedelta(0):
        # Future-dated → treat as undated rather than inventing "fresh"
        return ExternalFreshness.UNDATED
    if age <= BREAKING_MAX:
        return ExternalFreshness.BREAKING
    if age <= RECENT_MAX:
        return ExternalFreshness.RECENT
    if age <= CURRENT_MAX:
        return ExternalFreshness.CURRENT
    return ExternalFreshness.STALE
