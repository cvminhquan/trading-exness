"""Domain models for read-only market analysis / trade proposal (Phase 16)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exness_bot.market_analysis.context import MarketStructureContext


class MarketRegime(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class AnalysisSignal(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"


class ExecutionStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AnalysisDataStatus(StrEnum):
    LIVE = "LIVE"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AnalysisReason:
    code: str
    passed: bool
    message: str


@dataclass(frozen=True)
class MarketQuoteSnapshot:
    bid: float | None
    ask: float | None
    spread_points: float | None
    quote_timestamp: datetime | None
    quote_age_seconds: float | None


@dataclass(frozen=True)
class IndicatorValues:
    ema20: float | None
    ema50: float | None
    ema200: float | None
    rsi14: float | None
    atr14: float | None
    close: float | None


@dataclass(frozen=True)
class TradePlan:
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float


@dataclass(frozen=True)
class PositionSizingSnapshot:
    equity: float
    risk_percent: float
    risk_budget_usd: float
    raw_volume: float | None
    normalized_volume: float | None
    broker_min_volume: float | None
    broker_max_volume: float | None
    broker_volume_step: float | None
    estimated_risk_usd: float | None
    estimated_risk_pct: float | None
    broker_executable: bool
    risk_acceptable: bool


@dataclass
class TradeAnalysisResult:
    symbol: str
    broker_symbol: str
    timeframe: str
    market: MarketQuoteSnapshot
    indicators: IndicatorValues
    regime: MarketRegime
    signal: AnalysisSignal
    execution_status: ExecutionStatus
    trade: TradePlan | None
    sizing: PositionSizingSnapshot | None
    reasons: list[AnalysisReason] = field(default_factory=list)
    blocking_reasons: list[AnalysisReason] = field(default_factory=list)
    candle_timestamp: datetime | None = None
    generated_at: datetime | None = None
    status: AnalysisDataStatus = AnalysisDataStatus.UNAVAILABLE
    strategy: str = "ema_rsi_atr_v1"
    # Phase 16.1 additive fields (backward compatible)
    strategy_signal: AnalysisSignal | None = None
    context_assessment: str | None = None
    structure: MarketStructureContext | None = None
