"""Broker-neutral ExecutionPlan — decision, not commitment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from exness_bot.domain.enums import SignalDirection
from exness_bot.execution.eligibility import ExecutionEventKind


@dataclass(frozen=True)
class ExecutionPlan:
    """
    What we WOULD like to execute.

    Broker-neutral: no MT5 constants, tickets, or mutable lifecycle status.
    Commitment to the execution boundary happens via ExecutionIntent.
    """

    plan_id: str
    signal_id: str
    strategy_id: str
    symbol: str
    timeframe: str
    side: SignalDirection
    requested_volume: float
    stop_loss: float
    take_profit: float
    signal_timestamp: datetime
    decision_timestamp: datetime
    reason: str = ""
    source: str = "execution_plan"
    event_kind: ExecutionEventKind = ExecutionEventKind.LIVE
    metadata: dict[str, Any] = field(default_factory=dict)
