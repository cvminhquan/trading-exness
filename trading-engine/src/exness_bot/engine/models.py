"""Trading engine models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from exness_bot.domain.models import IndicatorSnapshot, OrderResult, Signal


class CycleStatus(StrEnum):
    """Outcome of a single engine tick."""

    SKIPPED = "skipped"
    COMPLETED = "completed"
    PAUSED = "paused"


class PauseReason(StrEnum):
    """Reasons the engine paused trading."""

    MT5_DISCONNECTED = "mt5_disconnected"
    DATABASE_UNAVAILABLE = "database_unavailable"
    MARKET_DATA_UNAVAILABLE = "market_data_unavailable"
    STRATEGY_ERROR = "strategy_error"
    RISK_ERROR = "risk_error"
    EXECUTION_ERROR = "execution_error"
    UNEXPECTED_ERROR = "unexpected_error"


class TradingCycleResult(BaseModel):
    """Structured result of one orchestration cycle."""

    status: CycleStatus
    candle_timestamp: datetime | None = None
    indicators: IndicatorSnapshot | None = None
    signal: Signal | None = None
    risk_outcome: str | None = None
    order_result: OrderResult | None = None
    reconciliation: list[tuple[int, bool, str]] = Field(default_factory=list)
    message: str = ""
    paused: bool = False
    pause_reason: PauseReason | None = None

    model_config = {"frozen": True}
