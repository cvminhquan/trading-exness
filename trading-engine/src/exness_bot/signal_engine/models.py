"""Signal result models — research/signal only, no execution fields."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from exness_bot.domain.models import IndicatorSnapshot


class SignalKind(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    NO_SIGNAL = "NO_SIGNAL"
    INVALID = "INVALID"


class SignalEmission(StrEnum):
    SIGNAL_EMISSION = "SIGNAL_EMISSION"
    INDICATOR_CATCHUP = "INDICATOR_CATCHUP"
    WARMUP = "WARMUP"


class SignalCycleStatus(StrEnum):
    SIGNAL_EMITTED = "SIGNAL_EMITTED"
    NO_SIGNAL = "NO_SIGNAL"
    WARMUP_COMPLETE = "WARMUP_COMPLETE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    INVALID_CANDLE = "INVALID_CANDLE"
    INVALID_INDICATOR = "INVALID_INDICATOR"
    FORMING_REJECTED = "FORMING_REJECTED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


@dataclass(frozen=True)
class SignalCondition:
    id: str
    label: str
    detail: str
    satisfied: bool


@dataclass(frozen=True)
class SignalResult:
    symbol: str
    timeframe: str
    candle_timestamp: datetime
    signal: SignalKind
    generated_at: datetime
    source: str
    strategy: str
    indicators: IndicatorSnapshot
    reason: str
    conditions: tuple[SignalCondition, ...]
    idempotency_key: str
    emission: SignalEmission
    actionable: bool
    executable: bool = False
    """Only True for latest closed-candle SIGNAL_EMISSION that may reach execution."""


@dataclass(frozen=True)
class SignalCycleResult:
    status: SignalCycleStatus
    results: tuple[SignalResult, ...] = ()
    catchup_count: int = 0
    message: str = ""


def signal_idempotency_key(
    symbol: str,
    timeframe: str,
    timestamp: datetime,
    strategy: str,
) -> str:
    return f"{symbol}|{timeframe}|{timestamp.isoformat()}|{strategy}"
