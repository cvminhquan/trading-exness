"""Orchestration result — broker-neutral."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from exness_bot.paper_execution.contract import (
    ExecutionAck,
    ExecutionIntent,
    IntentLifecycle,
    IntentRecord,
)


class OrchestrationOutcome(StrEnum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    DUPLICATE = "DUPLICATE"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class OrchestrationResult:
    outcome: str
    message: str
    plan_id: str | None = None
    intent: ExecutionIntent | None = None
    intent_record: IntentRecord | None = None
    ack: ExecutionAck | None = None
    lifecycle: IntentLifecycle | None = None
    idempotency_key: str | None = None
    port_calls: int = 0
