"""Phase 16.3.3 — AI Market Synthesis (read-only, hybrid deterministic + AI).

Does not generate or approve trades. Does not search the web.
"""

from __future__ import annotations

from exness_bot.market_analysis.synthesis.models import (
    RULE_VERSION,
    SCHEMA_VERSION,
    MarketSynthesis,
)
from exness_bot.market_analysis.synthesis.service import MarketSynthesisService

__all__ = [
    "RULE_VERSION",
    "SCHEMA_VERSION",
    "MarketSynthesis",
    "MarketSynthesisService",
]
