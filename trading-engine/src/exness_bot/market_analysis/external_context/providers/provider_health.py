"""Provider health snapshot helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from exness_bot.market_analysis.external_context.providers.base import ProviderHealth
from exness_bot.market_analysis.external_context.providers.provider_cache import (
    ProviderResultCache,
)


def merge_health_with_cache(
    health: ProviderHealth,
    cache: ProviderResultCache,
    *,
    now: datetime,
) -> dict[str, Any]:
    out = health.to_dict()
    out["cache"] = cache.status(health.provider, now=now)
    return out
