"""Deterministic ExternalContextQueryPlanner — bounded topics for XAUUSD."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from exness_bot.market_analysis.external_context.fingerprint import technical_context_summary
from exness_bot.market_analysis.external_context.models import (
    ExternalSearchPlan,
    SearchTopic,
    SearchTopicItem,
)

# Max topics per request — keep bounded.
MAX_TOPICS = 6


def plan_search(
    *,
    symbol: str,
    snapshot: dict[str, Any],
    now: datetime | None = None,
) -> ExternalSearchPlan:
    now_utc = now or datetime.now(tz=UTC)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    summary = technical_context_summary(snapshot)
    tfs = snapshot.get("timeframes") or {}
    m15 = tfs.get("M15") or {}
    topics: list[SearchTopicItem] = [
        SearchTopicItem(
            topic=SearchTopic.GOLD_MARKET.value,
            purpose="Current gold/XAUUSD market developments and safe-haven narratives",
            priority=1,
        ),
        SearchTopicItem(
            topic=SearchTopic.USD.value,
            purpose="US dollar / DXY strength or weakness relevant to gold",
            priority=2,
        ),
        SearchTopicItem(
            topic=SearchTopic.TREASURY_YIELDS.value,
            purpose="US Treasury yields / real-yield context affecting gold",
            priority=3,
        ),
        SearchTopicItem(
            topic=SearchTopic.FED.value,
            purpose="Fed policy, speakers, and rate expectations",
            priority=4,
        ),
        SearchTopicItem(
            topic=SearchTopic.US_MACRO.value,
            purpose="US inflation, employment, and other macro releases affecting gold",
            priority=5,
        ),
    ]
    # Geopolitics when primary is directional or sharp impulse
    impulse = m15.get("descriptive_impulse") or {}
    last1 = impulse.get("last_1_bar_move") or {}
    atr_move = last1.get("atr_normalized_change")
    sharp = isinstance(atr_move, (int, float)) and abs(float(atr_move)) >= 1.0
    if sharp or (m15.get("trend") in {"BULLISH", "BEARISH"}):
        topics.append(
            SearchTopicItem(
                topic=SearchTopic.GEOPOLITICS.value,
                purpose="Geopolitical / risk-off events that may drive safe-haven gold flows",
                priority=6,
            )
        )
    topics = topics[:MAX_TOPICS]
    return ExternalSearchPlan(
        symbol=symbol.strip().upper() or "XAUUSD",
        generated_at=now_utc.isoformat(),
        technical_context_summary=summary,
        search_topics=topics,
        time_sensitivity="CURRENT",
    )
