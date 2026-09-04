"""Helpers to build ExecutionPlan from risk/signal — broker-neutral."""

from __future__ import annotations

from datetime import datetime

from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import ApprovedOrderPlan
from exness_bot.execution.eligibility import ExecutionEventKind
from exness_bot.execution.plan import ExecutionPlan
from exness_bot.signal_engine.models import SignalEmission, SignalKind, SignalResult


def event_kind_from_signal(result: SignalResult) -> ExecutionEventKind:
    if result.emission != SignalEmission.SIGNAL_EMISSION:
        return ExecutionEventKind.CATCH_UP
    if not result.executable or not result.actionable:
        return ExecutionEventKind.CATCH_UP
    if result.signal not in {SignalKind.BUY, SignalKind.SELL}:
        return ExecutionEventKind.CATCH_UP
    return ExecutionEventKind.LIVE


def plan_from_approved(
    *,
    result: SignalResult,
    decision: ApprovedOrderPlan,
    side: SignalDirection,
    now: datetime,
    event_kind: ExecutionEventKind | None = None,
    plan_id: str | None = None,
) -> ExecutionPlan:
    kind = event_kind if event_kind is not None else event_kind_from_signal(result)
    return ExecutionPlan(
        plan_id=plan_id or f"plan-{result.idempotency_key}",
        signal_id=result.idempotency_key,
        strategy_id=result.strategy,
        symbol=result.symbol,
        timeframe=result.timeframe,
        side=side,
        requested_volume=decision.volume,
        stop_loss=decision.stop_loss,
        take_profit=decision.take_profit,
        signal_timestamp=result.candle_timestamp,
        decision_timestamp=now,
        reason=result.reason,
        source=result.source,
        event_kind=kind,
        metadata={"idempotency_key": result.idempotency_key},
    )
