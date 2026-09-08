"""Domain models for analysis → execution contract (no side effects)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from exness_bot.market_analysis.models import AnalysisReason
from exness_bot.market_analysis.setup import TakeProfitLevel


class SetupLifecycleState(StrEnum):
    """Durable setup lifecycle (extends Phase 16.2 ephemeral states)."""

    NO_SETUP = "NO_SETUP"
    WAITING_FOR_ENTRY = "WAITING_FOR_ENTRY"
    ENTRY_ZONE = "ENTRY_ZONE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class CanonicalTradeSetup:
    """Single durable trade setup identity — analysis only."""

    setup_id: str
    strategy_id: str
    symbol: str
    broker_symbol: str
    primary_timeframe: str
    direction: str  # LONG | SHORT
    source_candle_timestamp: datetime
    created_at: datetime
    expires_at: datetime
    entry_type: str
    entry_zone_low: float
    entry_zone_high: float
    entry_price: float
    stop_loss: float
    take_profits: tuple[TakeProfitLevel, ...]
    confidence_score: float
    confidence_meaning: str
    analysis_fingerprint: str
    state: SetupLifecycleState
    risk_snapshot: dict[str, float | bool | None] = field(default_factory=dict)
    reasons: tuple[AnalysisReason, ...] = ()
    warnings: tuple[AnalysisReason, ...] = ()
    contract_version: str = "1"


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reasons: tuple[str, ...]
    blocking: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionCandidate:
    """Phase-17 input shape — never submitted to broker in Phase 16.3."""

    candidate_id: str
    setup_id: str
    analysis_fingerprint: str
    symbol: str
    broker_symbol: str
    side: str  # LONG | SHORT
    entry: float
    stop_loss: float
    take_profits: tuple[TakeProfitLevel, ...]
    proposed_volume: float | None
    estimated_risk_usd: float | None
    estimated_risk_pct: float | None
    broker_executable: bool
    risk_acceptable: bool
    eligibility: EligibilityResult
    created_at: datetime


@dataclass(frozen=True)
class ExecutionCandidateStatus:
    """API/dashboard projection — always read-only."""

    eligible: bool
    setup_state: str
    setup_id: str | None
    analysis_fingerprint: str | None
    candidate: ExecutionCandidate | None
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    strategy_id: str
    confidence_score: float | None
    confidence_meaning: str
    generated_at: datetime
