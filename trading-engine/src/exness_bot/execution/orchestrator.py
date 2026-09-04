"""ExecutionOrchestrator — durable lifecycle before ExecutionPort side effect.

Depends only on abstractions. Never imports MetaTrader5 or live broker transports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import structlog

from exness_bot.domain.models import SymbolInfo
from exness_bot.execution.guard import (
    ExecutionGuard,
    GuardDecision,
    default_orchestration_guards,
)
from exness_bot.execution.idempotency import idempotency_key_for_plan
from exness_bot.execution.plan import ExecutionPlan
from exness_bot.execution.result import OrchestrationOutcome, OrchestrationResult
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionAck,
    ExecutionIntent,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.intent_store import (
    DurableIntentStore,
    ExecutionEvidence,
    UnknownReason,
)
from exness_bot.paper_execution.port import ExecutionPort

logger = structlog.get_logger(__name__)

ClockFn = Callable[[], datetime]
IntentIdFactory = Callable[[ExecutionPlan], str]


@dataclass
class ExecutionOrchestrator:
    """
    Accept validated ExecutionPlan → durable intent → exactly one port.submit.

    Does NOT: indicators, strategy, MT5 request building, automatic UNKNOWN retry.
    """

    store: DurableIntentStore
    port: ExecutionPort
    clock: ClockFn
    guard: ExecutionGuard | None = None
    intent_id_factory: IntentIdFactory | None = None

    def __post_init__(self) -> None:
        if self.guard is None:
            self.guard = default_orchestration_guards(self.store)
        if self.intent_id_factory is None:
            self.intent_id_factory = _default_intent_id

    def execute(self, plan: ExecutionPlan, *, quote: SymbolInfo) -> OrchestrationResult:
        key = idempotency_key_for_plan(plan)
        existing = self.store.get_by_key(key)
        if existing is not None:
            return OrchestrationResult(
                outcome=_duplicate_or_blocking_outcome(existing.lifecycle),
                message=(
                    f"Existing intent {existing.intent_id} "
                    f"lifecycle={existing.lifecycle.value} — no second submit."
                ),
                plan_id=plan.plan_id,
                intent_record=existing,
                lifecycle=existing.lifecycle,
                idempotency_key=key,
                port_calls=0,
            )

        decision = self._evaluate_guard(plan)
        if not decision.allowed:
            return OrchestrationResult(
                outcome=OrchestrationOutcome.BLOCKED,
                message=decision.reason or "Execution blocked by guard.",
                plan_id=plan.plan_id,
                idempotency_key=key,
                port_calls=0,
            )

        now = self.clock()
        assert self.intent_id_factory is not None
        intent = ExecutionIntent(
            intent_id=self.intent_id_factory(plan),
            idempotency_key=key,
            symbol=plan.symbol,
            timeframe=plan.timeframe,
            strategy=plan.strategy_id,
            side=plan.side,
            requested_quantity=plan.requested_volume,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            created_at=plan.signal_timestamp,
            source=plan.source,
        )

        try:
            created = self.store.create_intent(intent, now=now)
        except Exception as exc:
            logger.error("orchestrator_create_failed", error=str(exc))
            return OrchestrationResult(
                outcome=OrchestrationOutcome.ERROR,
                message=f"Store create failed before side effect: {exc}",
                plan_id=plan.plan_id,
                intent=intent,
                idempotency_key=key,
                port_calls=0,
            )

        if not created.created:
            return OrchestrationResult(
                outcome=OrchestrationOutcome.DUPLICATE,
                message="Idempotency collision on create — no submit.",
                plan_id=plan.plan_id,
                intent=intent,
                intent_record=created.record,
                lifecycle=created.record.lifecycle,
                idempotency_key=key,
                port_calls=0,
            )

        try:
            self.store.mark_in_flight(intent.intent_id, now=self.clock())
        except Exception as exc:
            logger.error("orchestrator_in_flight_failed", error=str(exc))
            return OrchestrationResult(
                outcome=OrchestrationOutcome.ERROR,
                message=f"IN_FLIGHT persist failed — no side effect: {exc}",
                plan_id=plan.plan_id,
                intent=intent,
                intent_record=self.store.get(intent.intent_id),
                lifecycle=IntentLifecycle.INTENT_CREATED,
                idempotency_key=key,
                port_calls=0,
            )

        # Side effect only after durable IN_FLIGHT.
        try:
            ack = self.port.submit(intent, quote=quote)
        except Exception as exc:
            logger.warning("orchestrator_port_exception", error=str(exc))
            return self._finalize_unknown(
                plan=plan,
                intent=intent,
                key=key,
                detail=f"port exception after IN_FLIGHT: {exc}",
                reason=UnknownReason.ACK_UNKNOWN,
                port_calls=1,
            )

        return self._finalize_ack(plan=plan, intent=intent, key=key, ack=ack, port_calls=1)

    def _evaluate_guard(self, plan: ExecutionPlan) -> GuardDecision:
        assert self.guard is not None
        return self.guard.evaluate(plan)

    def _finalize_ack(
        self,
        *,
        plan: ExecutionPlan,
        intent: ExecutionIntent,
        key: str,
        ack: ExecutionAck,
        port_calls: int,
    ) -> OrchestrationResult:
        lifecycle, outcome, unknown_reason = _map_ack(ack.status)
        evidence = ExecutionEvidence(
            fill_price=ack.fill_price,
            broker_order_id=ack.broker_order_id,
            broker_deal_id=ack.broker_position_id,
            reason=ack.reason,
            ack_status=ack.status.value,
        )
        now = self.clock()
        try:
            if lifecycle is IntentLifecycle.FILLED:
                record = self.store.mark_filled(intent.intent_id, evidence, now=now)
            elif lifecycle is IntentLifecycle.REJECTED:
                record = self.store.mark_rejected(intent.intent_id, evidence, now=now)
            else:
                record = self.store.mark_unknown(
                    intent.intent_id,
                    unknown_reason,
                    now=now,
                    detail=ack.reason,
                )
        except Exception as exc:
            # Side effect MAY have occurred — never resend; fail closed to UNKNOWN.
            logger.error(
                "orchestrator_finalize_failed",
                error=str(exc),
                intent_id=intent.intent_id,
                ack=ack.status.value,
            )
            return self._recover_after_finalize_failure(
                plan=plan,
                intent=intent,
                key=key,
                ack=ack,
                port_calls=port_calls,
                error=str(exc),
            )

        logger.info(
            "orchestrator_complete",
            plan_id=plan.plan_id,
            intent_id=intent.intent_id,
            outcome=outcome,
            lifecycle=record.lifecycle.value,
            port_calls=port_calls,
        )
        return OrchestrationResult(
            outcome=outcome,
            message=ack.reason or outcome,
            plan_id=plan.plan_id,
            intent=intent,
            intent_record=record,
            ack=ack,
            lifecycle=record.lifecycle,
            idempotency_key=key,
            port_calls=port_calls,
        )

    def _finalize_unknown(
        self,
        *,
        plan: ExecutionPlan,
        intent: ExecutionIntent,
        key: str,
        detail: str,
        reason: UnknownReason,
        port_calls: int,
    ) -> OrchestrationResult:
        record: IntentRecord | None
        try:
            record = self.store.mark_unknown(
                intent.intent_id,
                reason,
                now=self.clock(),
                detail=detail,
            )
            lifecycle = record.lifecycle
        except Exception as exc:
            logger.error("orchestrator_mark_unknown_failed", error=str(exc))
            record = self.store.get(intent.intent_id)
            lifecycle = record.lifecycle if record else IntentLifecycle.IN_FLIGHT
        return OrchestrationResult(
            outcome=OrchestrationOutcome.UNKNOWN,
            message=detail,
            plan_id=plan.plan_id,
            intent=intent,
            intent_record=record,
            lifecycle=lifecycle,
            idempotency_key=key,
            port_calls=port_calls,
        )

    def _recover_after_finalize_failure(
        self,
        *,
        plan: ExecutionPlan,
        intent: ExecutionIntent,
        key: str,
        ack: ExecutionAck,
        port_calls: int,
        error: str,
    ) -> OrchestrationResult:
        detail = (
            f"Finalize persistence failed after side effect (ack={ack.status.value}): {error}. "
            "Treating as reconciliation-required — NO RESEND."
        )
        record: IntentRecord | None
        try:
            record = self.store.mark_unknown(
                intent.intent_id,
                UnknownReason.ACK_UNKNOWN,
                now=self.clock(),
                detail=detail,
            )
            lifecycle = record.lifecycle
        except Exception:
            record = self.store.get(intent.intent_id)
            lifecycle = (
                record.lifecycle if record is not None else IntentLifecycle.IN_FLIGHT
            )
        return OrchestrationResult(
            outcome=OrchestrationOutcome.UNKNOWN,
            message=detail,
            plan_id=plan.plan_id,
            intent=intent,
            intent_record=record,
            ack=ack,
            lifecycle=lifecycle,
            idempotency_key=key,
            port_calls=port_calls,
        )


def _default_intent_id(plan: ExecutionPlan) -> str:
    return f"orch-{plan.plan_id}-{uuid4().hex[:8]}"


def _map_ack(
    status: AckStatus,
) -> tuple[IntentLifecycle, str, UnknownReason]:
    if status is AckStatus.FILLED:
        return IntentLifecycle.FILLED, OrchestrationOutcome.FILLED, UnknownReason.ACK_UNKNOWN
    if status is AckStatus.REJECTED:
        return (
            IntentLifecycle.REJECTED,
            OrchestrationOutcome.REJECTED,
            UnknownReason.ACK_UNKNOWN,
        )
    if status is AckStatus.TIMEOUT:
        return IntentLifecycle.UNKNOWN, OrchestrationOutcome.UNKNOWN, UnknownReason.ACK_TIMEOUT
    if status is AckStatus.ACCEPTED:
        return IntentLifecycle.UNKNOWN, OrchestrationOutcome.UNKNOWN, UnknownReason.ACK_ACCEPTED
    if status is AckStatus.IN_FLIGHT:
        return IntentLifecycle.UNKNOWN, OrchestrationOutcome.UNKNOWN, UnknownReason.ACK_IN_FLIGHT
    return IntentLifecycle.UNKNOWN, OrchestrationOutcome.UNKNOWN, UnknownReason.ACK_UNKNOWN


def _duplicate_or_blocking_outcome(lifecycle: IntentLifecycle) -> str:
    if lifecycle in {
        IntentLifecycle.INTENT_CREATED,
        IntentLifecycle.IN_FLIGHT,
        IntentLifecycle.UNKNOWN,
    }:
        return OrchestrationOutcome.UNKNOWN
    return OrchestrationOutcome.DUPLICATE
