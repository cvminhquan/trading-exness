"""Closed-candle events and poll results — no strategy payload."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from exness_bot.domain.models import Candle


class CandlePollStatus(StrEnum):
    """Normal polling outcomes — not exceptions."""

    CANDLE_PROCESSED = "CANDLE_PROCESSED"
    CANDLE_ALREADY_PROCESSED = "CANDLE_ALREADY_PROCESSED"
    NO_CLOSED_CANDLE = "NO_CLOSED_CANDLE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    INVALID_CANDLE = "INVALID_CANDLE"


@dataclass(frozen=True)
class ClosedCandleEvent:
    """Boundary for a future Signal Engine. Contains a CLOSED candle only."""

    candle: Candle
    detected_at: datetime
    source: str
    idempotency_key: str


@dataclass(frozen=True)
class CandlePollResult:
    """Outcome of one poll cycle."""

    status: CandlePollStatus
    events: tuple[ClosedCandleEvent, ...] = ()
    message: str = ""
    latest_closed_at: datetime | None = None


def candle_idempotency_key(symbol: str, timeframe: str, timestamp: datetime) -> str:
    return f"{symbol}|{timeframe}|{timestamp.isoformat()}"
