"""MarketSynthesisProvider abstraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from exness_bot.market_analysis.synthesis.models import MarketSynthesisNarrative


@dataclass
class MarketSynthesisPromptInput:
    symbol: str
    payload: dict[str, Any]
    utc_now_iso: str


@dataclass
class MarketSynthesisProviderResult:
    ok: bool
    narrative: MarketSynthesisNarrative | None = None
    raw: dict[str, Any] | None = None
    latency_ms: float | None = None
    error_type: str | None = None
    provider: str = "unknown"
    model: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class MarketSynthesisProvider(Protocol):
    name: str
    model: str

    def generate_explanation(
        self, request: MarketSynthesisPromptInput
    ) -> MarketSynthesisProviderResult: ...
