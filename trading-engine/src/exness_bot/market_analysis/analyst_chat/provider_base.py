"""Provider abstraction for Market Analyst Chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from exness_bot.market_analysis.analyst_chat.models import (
    ChatMessage,
    MarketAnalystContext,
)


@dataclass
class MarketAnalystProviderResponse:
    answer: str
    answer_type: str
    source_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider: str = "unknown"
    model: str | None = None
    latency_ms: float | None = None
    raw_error: str | None = None


class MarketAnalystProvider(Protocol):
    def answer(
        self,
        *,
        context: MarketAnalystContext,
        conversation: list[ChatMessage],
        message: str,
    ) -> MarketAnalystProviderResponse: ...
