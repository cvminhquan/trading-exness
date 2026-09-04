"""Durable intent store — explicit lifecycle, idempotency, crash recovery. No broker calls."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionIntent,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.errors import (
    DuplicateIdempotencyKey,
    InvalidLifecycleTransition,
)
from exness_bot.paper_execution.executor import PaperExecutor

# Explicit allowed transitions for mark_* (not reconciliation).
_ALLOWED_TRANSITIONS: dict[IntentLifecycle, frozenset[IntentLifecycle]] = {
    IntentLifecycle.INTENT_CREATED: frozenset({IntentLifecycle.IN_FLIGHT}),
    IntentLifecycle.IN_FLIGHT: frozenset(
        {
            IntentLifecycle.FILLED,
            IntentLifecycle.REJECTED,
            IntentLifecycle.UNKNOWN,
        }
    ),
    IntentLifecycle.UNKNOWN: frozenset(),
    IntentLifecycle.FILLED: frozenset(),
    IntentLifecycle.REJECTED: frozenset(),
    IntentLifecycle.DUPLICATE: frozenset(),
}


class UnknownReason(StrEnum):
    """Why an intent was marked UNKNOWN (local durability only)."""

    RECOVERED_IN_FLIGHT = "RECOVERED_IN_FLIGHT"
    ACK_TIMEOUT = "ACK_TIMEOUT"
    ACK_UNKNOWN = "ACK_UNKNOWN"
    ACK_ACCEPTED = "ACK_ACCEPTED"
    ACK_IN_FLIGHT = "ACK_IN_FLIGHT"
    OPERATOR = "OPERATOR"


@dataclass(frozen=True)
class ExecutionEvidence:
    """Local evidence attached when finalizing an intent — not a broker proof by itself."""

    fill_price: float | None = None
    broker_order_id: str | None = None
    broker_deal_id: str | None = None
    reason: str | None = None
    ack_status: str | None = None


@dataclass(frozen=True)
class CreateIntentResult:
    """Result of create — never silently overwrites an existing key."""

    record: IntentRecord
    created: bool


class IntentStore(Protocol):
    """Backward-compatible low-level protocol used by recovery helpers."""

    def create(self, record: IntentRecord) -> None: ...

    def update(self, record: IntentRecord) -> None: ...

    def get(self, intent_id: str) -> IntentRecord | None: ...

    def get_by_key(self, idempotency_key: str) -> IntentRecord | None: ...

    def list_blocking(self) -> tuple[IntentRecord, ...]: ...

    def recover_in_flight_to_unknown(self, *, now: datetime) -> tuple[IntentRecord, ...]: ...


class DurableIntentStore(Protocol):
    """
    Broker-agnostic durable intent lifecycle (Phase 12.1).

    Local durability ≠ broker transactional coupling.
    Persistence does NOT prove broker execution.
    """

    def create_intent(self, intent: ExecutionIntent, *, now: datetime) -> CreateIntentResult: ...

    def mark_in_flight(self, intent_id: str, *, now: datetime) -> IntentRecord: ...

    def mark_filled(
        self,
        intent_id: str,
        evidence: ExecutionEvidence,
        *,
        now: datetime,
    ) -> IntentRecord: ...

    def mark_rejected(
        self,
        intent_id: str,
        evidence: ExecutionEvidence,
        *,
        now: datetime,
    ) -> IntentRecord: ...

    def mark_unknown(
        self,
        intent_id: str,
        reason: UnknownReason,
        *,
        now: datetime,
        detail: str | None = None,
    ) -> IntentRecord: ...

    def reconcile_filled(
        self,
        intent_id: str,
        evidence: ExecutionEvidence,
        *,
        now: datetime,
    ) -> IntentRecord: ...

    def reconcile_rejected(
        self,
        intent_id: str,
        evidence: ExecutionEvidence,
        *,
        now: datetime,
    ) -> IntentRecord: ...

    def get(self, intent_id: str) -> IntentRecord | None: ...

    def get_by_key(self, idempotency_key: str) -> IntentRecord | None: ...

    def list_in_flight(self) -> tuple[IntentRecord, ...]: ...

    def list_unknown(self) -> tuple[IntentRecord, ...]: ...

    def list_blocking(self) -> tuple[IntentRecord, ...]: ...

    def recover_in_flight_to_unknown(self, *, now: datetime) -> tuple[IntentRecord, ...]: ...


def assert_transition_allowed(
    current: IntentLifecycle,
    target: IntentLifecycle,
    *,
    via_reconcile: bool = False,
) -> None:
    if via_reconcile:
        if current != IntentLifecycle.UNKNOWN or target not in {
            IntentLifecycle.FILLED,
            IntentLifecycle.REJECTED,
        }:
            raise InvalidLifecycleTransition(
                f"Reconcile only allows UNKNOWN → FILLED|REJECTED; got {current} → {target}"
            )
        return
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidLifecycleTransition(f"Illegal transition {current} → {target}")


class SnapshotIntentStore:
    """
    Intent rows live inside PaperSnapshot JSON (schemaVersion 3).

    Durability invariant (Phase 12.1):
    - IN_FLIGHT is persisted before any ExecutionPort.submit side effect.
    - Final FILLED / REJECTED / UNKNOWN is persisted after the ack is known.
    - Crash after side effect but before final persist → UNKNOWN on restart.
    - One mutation → one coherent snapshot persist (intents + session together).
    - In-process lock protects concurrent mutate+persist races (single-process architecture).

    JSON file persistence is NOT database-grade ACID and is NOT coupled to MT5.
    """

    def __init__(
        self,
        executor: PaperExecutor,
        *,
        persist: Callable[[], None],
    ) -> None:
        self._executor = executor
        self._persist = persist
        self._lock = threading.RLock()

    def create(self, record: IntentRecord) -> None:
        """Low-level insert — enforces idempotency uniqueness."""
        with self._lock:
            existing = self.get_by_key(record.idempotency_key)
            if existing is not None:
                raise DuplicateIdempotencyKey(
                    idempotency_key=record.idempotency_key,
                    existing=existing,
                )
            if self.get(record.intent_id) is not None:
                raise InvalidLifecycleTransition(
                    f"intent_id already exists: {record.intent_id}"
                )
            self._executor.upsert_intent(record)
            self._persist()

    def update(self, record: IntentRecord) -> None:
        """
        Low-level replace by intent_id.

        Prefer mark_* / reconcile_* for lifecycle safety. Kept for Protocol compatibility.
        """
        with self._lock:
            current = self.get(record.intent_id)
            if current is None:
                raise InvalidLifecycleTransition(f"Unknown intent_id: {record.intent_id}")
            if current.lifecycle != record.lifecycle:
                via_reconcile = (
                    current.lifecycle == IntentLifecycle.UNKNOWN
                    and record.lifecycle
                    in {IntentLifecycle.FILLED, IntentLifecycle.REJECTED}
                )
                assert_transition_allowed(
                    current.lifecycle,
                    record.lifecycle,
                    via_reconcile=via_reconcile,
                )
            self._executor.upsert_intent(record)
            self._persist()

    def create_intent(self, intent: ExecutionIntent, *, now: datetime) -> CreateIntentResult:
        with self._lock:
            existing = self.get_by_key(intent.idempotency_key)
            if existing is not None:
                return CreateIntentResult(record=existing, created=False)
            record = IntentRecord(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                lifecycle=IntentLifecycle.INTENT_CREATED,
                created_at=now,
                updated_at=now,
                side=intent.side.value,
                symbol=intent.symbol,
                requested_quantity=intent.requested_quantity,
                stop_loss=intent.stop_loss,
                take_profit=intent.take_profit,
                strategy=intent.strategy,
                timeframe=intent.timeframe,
                signal_timestamp=intent.created_at,
                correlation_id=intent.intent_id,
            )
            self._executor.upsert_intent(record)
            self._persist()
            return CreateIntentResult(record=record, created=True)

    def mark_in_flight(self, intent_id: str, *, now: datetime) -> IntentRecord:
        return self._transition(
            intent_id,
            IntentLifecycle.IN_FLIGHT,
            now=now,
            ack_status=AckStatus.IN_FLIGHT.value,
        )

    def mark_filled(
        self,
        intent_id: str,
        evidence: ExecutionEvidence,
        *,
        now: datetime,
    ) -> IntentRecord:
        return self._transition(
            intent_id,
            IntentLifecycle.FILLED,
            now=now,
            evidence=evidence,
            ack_status=evidence.ack_status or AckStatus.FILLED.value,
        )

    def mark_rejected(
        self,
        intent_id: str,
        evidence: ExecutionEvidence,
        *,
        now: datetime,
    ) -> IntentRecord:
        return self._transition(
            intent_id,
            IntentLifecycle.REJECTED,
            now=now,
            evidence=evidence,
            ack_status=evidence.ack_status or AckStatus.REJECTED.value,
            clear_fill=True,
        )

    def mark_unknown(
        self,
        intent_id: str,
        reason: UnknownReason,
        *,
        now: datetime,
        detail: str | None = None,
    ) -> IntentRecord:
        return self._transition(
            intent_id,
            IntentLifecycle.UNKNOWN,
            now=now,
            ack_status=AckStatus.UNKNOWN.value,
            reason_text=detail or reason.value,
        )

    def reconcile_filled(
        self,
        intent_id: str,
        evidence: ExecutionEvidence,
        *,
        now: datetime,
    ) -> IntentRecord:
        return self._transition(
            intent_id,
            IntentLifecycle.FILLED,
            now=now,
            evidence=evidence,
            ack_status=evidence.ack_status or AckStatus.FILLED.value,
            via_reconcile=True,
        )

    def reconcile_rejected(
        self,
        intent_id: str,
        evidence: ExecutionEvidence,
        *,
        now: datetime,
    ) -> IntentRecord:
        return self._transition(
            intent_id,
            IntentLifecycle.REJECTED,
            now=now,
            evidence=evidence,
            ack_status=evidence.ack_status or AckStatus.REJECTED.value,
            clear_fill=True,
            via_reconcile=True,
        )

    def get(self, intent_id: str) -> IntentRecord | None:
        for item in self._executor.snapshot.intents:
            if item.intent_id == intent_id:
                return item
        return None

    def get_by_key(self, idempotency_key: str) -> IntentRecord | None:
        return self._executor.intent_by_key(idempotency_key)

    def list_in_flight(self) -> tuple[IntentRecord, ...]:
        return tuple(
            item
            for item in self._executor.snapshot.intents
            if item.lifecycle == IntentLifecycle.IN_FLIGHT
        )

    def list_unknown(self) -> tuple[IntentRecord, ...]:
        return tuple(
            item
            for item in self._executor.snapshot.intents
            if item.lifecycle == IntentLifecycle.UNKNOWN
        )

    def list_blocking(self) -> tuple[IntentRecord, ...]:
        return tuple(
            item
            for item in self._executor.snapshot.intents
            if item.lifecycle
            in {
                IntentLifecycle.INTENT_CREATED,
                IntentLifecycle.IN_FLIGHT,
                IntentLifecycle.UNKNOWN,
            }
        )

    def recover_in_flight_to_unknown(self, *, now: datetime) -> tuple[IntentRecord, ...]:
        """
        Crash recovery: unresolved IN_FLIGHT → UNKNOWN.

        Does NOT resubmit. Does NOT mark FILLED or REJECTED without reconciliation.
        Persists one snapshot after all recoveries.
        """
        with self._lock:
            recovered: list[IntentRecord] = []
            for item in list(self._executor.snapshot.intents):
                if item.lifecycle != IntentLifecycle.IN_FLIGHT:
                    continue
                updated = replace(
                    item,
                    lifecycle=IntentLifecycle.UNKNOWN,
                    updated_at=now,
                    ack_status=IntentLifecycle.UNKNOWN.value,
                    reason=(
                        f"{UnknownReason.RECOVERED_IN_FLIGHT.value}: "
                        "Recovered from IN_FLIGHT after restart — requires reconciliation."
                    ),
                )
                self._executor.upsert_intent(updated)
                recovered.append(updated)
            if recovered:
                self._persist()
            return tuple(recovered)

    def _transition(
        self,
        intent_id: str,
        target: IntentLifecycle,
        *,
        now: datetime,
        evidence: ExecutionEvidence | None = None,
        ack_status: str | None = None,
        reason_text: str | None = None,
        clear_fill: bool = False,
        via_reconcile: bool = False,
    ) -> IntentRecord:
        with self._lock:
            current = self.get(intent_id)
            if current is None:
                raise InvalidLifecycleTransition(f"Unknown intent_id: {intent_id}")
            assert_transition_allowed(
                current.lifecycle,
                target,
                via_reconcile=via_reconcile,
            )
            fill_price = current.fill_price
            broker_order_id = current.broker_order_id
            broker_deal_id = current.broker_deal_id
            reason = reason_text if reason_text is not None else current.reason
            if evidence is not None:
                if evidence.fill_price is not None:
                    fill_price = evidence.fill_price
                if evidence.broker_order_id is not None:
                    broker_order_id = evidence.broker_order_id
                if evidence.broker_deal_id is not None:
                    broker_deal_id = evidence.broker_deal_id
                if evidence.reason is not None:
                    reason = evidence.reason
            if clear_fill:
                fill_price = None
            updated = replace(
                current,
                lifecycle=target,
                updated_at=now,
                ack_status=ack_status,
                fill_price=fill_price,
                broker_order_id=broker_order_id,
                broker_deal_id=broker_deal_id,
                reason=reason,
                correlation_id=current.correlation_id or current.intent_id,
            )
            self._executor.upsert_intent(updated)
            self._persist()
            return updated
