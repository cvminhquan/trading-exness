"""Broker-agnostic execution contract — intent ≠ fill. No MT5 types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from exness_bot.domain.enums import SignalDirection


class IntentLifecycle(StrEnum):
    """Persisted lifecycle before/after external side effects."""

    INTENT_CREATED = "INTENT_CREATED"
    IN_FLIGHT = "IN_FLIGHT"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    DUPLICATE = "DUPLICATE"


class AckStatus(StrEnum):
    """
    Acknowledgement from an ExecutionPort implementation.

    Semantics (Phase 11.9):
    - ACCEPTED: request received / broker accepted — final fill NOT known.
      MUST NOT be treated as FILLED. Lifecycle maps to UNKNOWN until reconcile.
    - FILLED: final execution confirmed by the executor (paper: virtual fill).
    - REJECTED: definitive rejection (no broker fill).
    - TIMEOUT / UNKNOWN / IN_FLIGHT: unresolved — remain UNKNOWN; no auto-retry.
    """

    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    IN_FLIGHT = "IN_FLIGHT"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class ExecutionIntent:
    """What SHOULD be executed — never includes a guaranteed fill."""

    intent_id: str
    idempotency_key: str
    symbol: str
    timeframe: str
    strategy: str
    side: SignalDirection
    requested_quantity: float
    stop_loss: float
    take_profit: float
    created_at: datetime
    source: str


@dataclass(frozen=True)
class ExecutionAck:
    """Broker/execution-independent acknowledgement."""

    intent_id: str
    idempotency_key: str
    status: AckStatus
    timestamp: datetime
    broker_order_id: str | None = None
    broker_position_id: str | None = None
    requested_price: float | None = None
    fill_price: float | None = None
    filled_quantity: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class IntentRecord:
    """Persisted intent lifecycle row (paper JSON / future live store)."""

    intent_id: str
    idempotency_key: str
    lifecycle: IntentLifecycle
    created_at: datetime
    updated_at: datetime
    side: str
    symbol: str
    requested_quantity: float
    stop_loss: float
    take_profit: float
    strategy: str = ""
    timeframe: str = ""
    signal_timestamp: datetime | None = None
    ack_status: str | None = None
    fill_price: float | None = None
    reason: str | None = None
    broker_order_id: str | None = None
    broker_deal_id: str | None = None
    correlation_id: str | None = None
