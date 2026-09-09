"""Phase 16.3.1 — Technical Market Snapshot (production read-only).

Deterministic technical truth for API/dashboard/future AI.
No LLM. No Google. No execution. No strategy modification.
"""

from __future__ import annotations

from exness_bot.market_analysis.technical_snapshot.builder import (
    TechnicalSnapshotBuilder,
)
from exness_bot.market_analysis.technical_snapshot.models import (
    SCHEMA_VERSION,
    TechnicalMarketSnapshot,
)

__all__ = [
    "SCHEMA_VERSION",
    "TechnicalMarketSnapshot",
    "TechnicalSnapshotBuilder",
]
