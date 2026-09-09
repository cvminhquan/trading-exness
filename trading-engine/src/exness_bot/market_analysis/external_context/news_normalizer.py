"""News/feed headline normalization — titles only, no article bodies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from exness_bot.market_analysis.external_context.providers.base import ExternalDataItem

_GEO = re.compile(
    r"\b(war|conflict|sanction|geopolit|missile|invasion|terror)\b", re.I
)
_EVENT = re.compile(
    r"\b(fomc|cpi|payroll|nfp|jobs\s+report|gdp|pce|jackson\s+hole)\b", re.I
)


@dataclass
class NewsGoldContext:
    geopolitical_hits: int = 0
    macro_event_hits: int = 0
    headlines: list[str] = field(default_factory=list)
    event_risk: str = "UNKNOWN"


def normalize_news_items(items: list[ExternalDataItem]) -> NewsGoldContext:
    ctx = NewsGoldContext()
    for item in items:
        if item.provider not in {"federal_reserve", "rss"}:
            continue
        title = item.title or ""
        if not title:
            continue
        ctx.headlines.append(title[:200])
        if _GEO.search(title):
            ctx.geopolitical_hits += 1
        if _EVENT.search(title) or (item.category or "") in {
            "monetary_policy",
            "speech",
        }:
            ctx.macro_event_hits += 1

    if ctx.geopolitical_hits >= 2 or ctx.macro_event_hits >= 4:
        ctx.event_risk = "HIGH"
    elif ctx.geopolitical_hits >= 1 or ctx.macro_event_hits >= 2:
        ctx.event_risk = "MEDIUM"
    elif ctx.headlines:
        ctx.event_risk = "LOW"
    else:
        ctx.event_risk = "UNKNOWN"
    return ctx
