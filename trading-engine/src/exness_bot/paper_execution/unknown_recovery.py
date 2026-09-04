"""Apply read-only reconciliation to UNKNOWN intents — never submit."""

from __future__ import annotations

from datetime import datetime

import structlog

from exness_bot.paper_execution.broker_query import (
    BrokerExecutionQuery,
    IntentReconcileResult,
    IntentReconcileStatus,
)
from exness_bot.paper_execution.contract import IntentLifecycle, IntentRecord
from exness_bot.paper_execution.intent_store import (
    DurableIntentStore,
    ExecutionEvidence,
    IntentStore,
)

logger = structlog.get_logger(__name__)


def apply_reconcile_to_intent(
    store: IntentStore | DurableIntentStore,
    intent: IntentRecord,
    result: IntentReconcileResult,
    *,
    now: datetime,
) -> IntentRecord:
    """
    Update lifecycle only when evidence is authoritative.

    CONFIRMED_FILLED → FILLED (via reconcile_filled)
    CONFIRMED_REJECTED → REJECTED (via reconcile_rejected)
    NOT_FOUND / AMBIGUOUS / UNAVAILABLE → remain UNKNOWN (no submit)
    """
    if intent.lifecycle != IntentLifecycle.UNKNOWN:
        return intent

    evidence = ExecutionEvidence(
        fill_price=result.fill_price,
        broker_order_id=result.broker_order_id,
        broker_deal_id=result.broker_deal_id,
        reason=result.message or None,
    )

    if result.status == IntentReconcileStatus.CONFIRMED_FILLED:
        if hasattr(store, "reconcile_filled"):
            updated = store.reconcile_filled(intent.intent_id, evidence, now=now)
        else:
            from dataclasses import replace

            from exness_bot.paper_execution.contract import AckStatus

            updated = replace(
                intent,
                lifecycle=IntentLifecycle.FILLED,
                updated_at=now,
                ack_status=AckStatus.FILLED.value,
                fill_price=(
                    result.fill_price if result.fill_price is not None else intent.fill_price
                ),
                reason=result.message or "Reconciled CONFIRMED_FILLED.",
                broker_order_id=result.broker_order_id or intent.broker_order_id,
                broker_deal_id=result.broker_deal_id or intent.broker_deal_id,
                correlation_id=intent.correlation_id or intent.intent_id,
            )
            store.update(updated)
        logger.info(
            "intent_reconciled_filled",
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
        )
        return updated

    if result.status == IntentReconcileStatus.CONFIRMED_REJECTED:
        if hasattr(store, "reconcile_rejected"):
            updated = store.reconcile_rejected(intent.intent_id, evidence, now=now)
        else:
            from dataclasses import replace

            from exness_bot.paper_execution.contract import AckStatus

            updated = replace(
                intent,
                lifecycle=IntentLifecycle.REJECTED,
                updated_at=now,
                ack_status=AckStatus.REJECTED.value,
                fill_price=None,
                reason=result.message or "Reconciled CONFIRMED_REJECTED.",
                broker_order_id=result.broker_order_id or intent.broker_order_id,
                broker_deal_id=result.broker_deal_id or intent.broker_deal_id,
                correlation_id=intent.correlation_id or intent.intent_id,
            )
            store.update(updated)
        logger.info(
            "intent_reconciled_rejected",
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
        )
        return updated

    logger.info(
        "intent_reconcile_unresolved",
        intent_id=intent.intent_id,
        status=result.status.value,
        message=result.message,
    )
    return intent


def reconcile_unknown_intents(
    store: IntentStore | DurableIntentStore,
    query: BrokerExecutionQuery,
    *,
    now: datetime,
) -> tuple[IntentRecord, ...]:
    """
    For each UNKNOWN intent, query broker read-only and optionally resolve.

    NEVER places a new execution request.
    """
    resolved: list[IntentRecord] = []
    for intent in store.list_blocking():
        if intent.lifecycle != IntentLifecycle.UNKNOWN:
            continue
        result = query.find_execution(intent)
        updated = apply_reconcile_to_intent(store, intent, result, now=now)
        if updated.lifecycle != IntentLifecycle.UNKNOWN:
            resolved.append(updated)
    return tuple(resolved)
