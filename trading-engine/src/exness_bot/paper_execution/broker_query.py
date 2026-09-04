"""Read-only broker execution query — reconcile UNKNOWN intents. No mutations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.contract import IntentRecord


class IntentReconcileStatus(StrEnum):
    """Authoritative read-only reconciliation outcome for one intent."""

    CONFIRMED_FILLED = "CONFIRMED_FILLED"
    CONFIRMED_REJECTED = "CONFIRMED_REJECTED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class BrokerExecutionEvidence:
    """Single read-only broker deal/order/rejection clue."""

    symbol: str
    side: SignalDirection
    volume: float
    timestamp: datetime
    broker_order_id: str | None = None
    broker_deal_id: str | None = None
    broker_position_id: str | None = None
    correlation_id: str | None = None
    rejected: bool = False
    reject_reason: str | None = None
    fill_price: float | None = None


@dataclass(frozen=True)
class IntentReconcileResult:
    status: IntentReconcileStatus
    intent_id: str
    idempotency_key: str
    matched_evidence: tuple[BrokerExecutionEvidence, ...] = ()
    message: str = ""
    broker_order_id: str | None = None
    broker_deal_id: str | None = None
    fill_price: float | None = None


class BrokerExecutionQuery(Protocol):
    """
    Broker-agnostic read-only query for intent reconciliation.

    Implementations MUST NOT submit, modify, close, or cancel orders.
    """

    def find_execution(self, intent: IntentRecord) -> IntentReconcileResult:
        """Locate authoritative evidence for an unresolved intent."""
        ...


class UnavailableBrokerExecutionQuery:
    """Default when no broker query is wired — remain UNKNOWN."""

    def find_execution(self, intent: IntentRecord) -> IntentReconcileResult:
        return IntentReconcileResult(
            status=IntentReconcileStatus.UNAVAILABLE,
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            message="Broker execution query unavailable.",
        )


class StaticBrokerExecutionQuery:
    """Test double: returns a fixed pool of evidence through matching rules."""

    def __init__(
        self,
        evidence: Sequence[BrokerExecutionEvidence] = (),
        *,
        unavailable: bool = False,
    ) -> None:
        self._evidence = tuple(evidence)
        self._unavailable = unavailable
        self.calls: list[str] = []

    def find_execution(self, intent: IntentRecord) -> IntentReconcileResult:
        self.calls.append(intent.intent_id)
        if self._unavailable:
            return IntentReconcileResult(
                status=IntentReconcileStatus.UNAVAILABLE,
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                message="Static query forced unavailable.",
            )
        return match_intent_to_evidence(intent, self._evidence)


def match_intent_to_evidence(
    intent: IntentRecord,
    evidence: Sequence[BrokerExecutionEvidence],
    *,
    volume_tolerance: float = 0.001,
    time_window: timedelta = timedelta(hours=2),
) -> IntentReconcileResult:
    """
    Deterministic matching hierarchy (strong → weak):

    1. correlation_id == intent_id or idempotency_key
    2. broker_order_id already recorded on the intent
    3. symbol + side + volume + time window (unique only)

    symbol+side alone is never sufficient.
    """
    if not evidence:
        return IntentReconcileResult(
            status=IntentReconcileStatus.NOT_FOUND,
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            message="No broker evidence available.",
        )

    correlation_keys = {
        intent.intent_id,
        intent.idempotency_key,
        *(
            [intent.correlation_id]
            if getattr(intent, "correlation_id", None)
            else []
        ),
    }
    by_correlation = [
        item
        for item in evidence
        if item.correlation_id and item.correlation_id in correlation_keys
    ]
    if len(by_correlation) == 1:
        return _from_single(intent, by_correlation[0], "Matched by correlation_id.")
    if len(by_correlation) > 1:
        return IntentReconcileResult(
            status=IntentReconcileStatus.AMBIGUOUS,
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            matched_evidence=tuple(by_correlation),
            message="Multiple evidences share the same correlation_id.",
        )

    stored_order = getattr(intent, "broker_order_id", None)
    if stored_order:
        by_order = [item for item in evidence if item.broker_order_id == stored_order]
        if len(by_order) == 1:
            return _from_single(intent, by_order[0], "Matched by stored broker_order_id.")
        if len(by_order) > 1:
            return IntentReconcileResult(
                status=IntentReconcileStatus.AMBIGUOUS,
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                matched_evidence=tuple(by_order),
                message="Multiple evidences for stored broker_order_id.",
            )

    side = _parse_side(intent.side)
    if side is None:
        return IntentReconcileResult(
            status=IntentReconcileStatus.AMBIGUOUS,
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            message="Intent side is not parseable.",
        )

    anchor = intent.signal_timestamp or intent.created_at
    weak: list[BrokerExecutionEvidence] = []
    for item in evidence:
        if item.symbol != intent.symbol:
            continue
        if item.side != side:
            continue
        if abs(item.volume - intent.requested_quantity) > volume_tolerance:
            continue
        if abs((item.timestamp - anchor).total_seconds()) > time_window.total_seconds():
            continue
        weak.append(item)

    if len(weak) == 0:
        return IntentReconcileResult(
            status=IntentReconcileStatus.NOT_FOUND,
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            message="No unique symbol/side/volume/time match.",
        )
    if len(weak) > 1:
        return IntentReconcileResult(
            status=IntentReconcileStatus.AMBIGUOUS,
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            matched_evidence=tuple(weak),
            message="Multiple weak matches — refuse to confirm.",
        )
    return _from_single(intent, weak[0], "Matched by symbol/side/volume/time window.")


def _from_single(
    intent: IntentRecord,
    evidence: BrokerExecutionEvidence,
    message: str,
) -> IntentReconcileResult:
    if evidence.rejected:
        return IntentReconcileResult(
            status=IntentReconcileStatus.CONFIRMED_REJECTED,
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            matched_evidence=(evidence,),
            message=evidence.reject_reason or message,
            broker_order_id=evidence.broker_order_id,
            broker_deal_id=evidence.broker_deal_id,
        )
    return IntentReconcileResult(
        status=IntentReconcileStatus.CONFIRMED_FILLED,
        intent_id=intent.intent_id,
        idempotency_key=intent.idempotency_key,
        matched_evidence=(evidence,),
        message=message,
        broker_order_id=evidence.broker_order_id,
        broker_deal_id=evidence.broker_deal_id,
        fill_price=evidence.fill_price,
    )


def _parse_side(raw: str) -> SignalDirection | None:
    try:
        return SignalDirection(raw)
    except ValueError:
        return None
