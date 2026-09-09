"""Phase 16.3.2 — External Intelligence (read-only, grounded).

No LLM trading signals. No execution. No strategy mutation.
"""

from __future__ import annotations

from exness_bot.market_analysis.external_context.models import (
    SCHEMA_VERSION,
    ExternalMarketContext,
)
from exness_bot.market_analysis.external_context.service import ExternalContextService

__all__ = [
    "SCHEMA_VERSION",
    "ExternalContextService",
    "ExternalMarketContext",
]
