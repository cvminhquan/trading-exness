"""Orchestration-level guards — abstractions only (no MT5 config)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from exness_bot.execution.eligibility import is_broker_eligible
from exness_bot.execution.plan import ExecutionPlan


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str = ""


class ExecutionGuard(Protocol):
    """Policy checked before committing an intent / side effect."""

    def evaluate(self, plan: ExecutionPlan) -> GuardDecision: ...


class IntentBlockingView(Protocol):
    """Minimal store surface for unresolved-intent checks."""

    def get_by_key(self, idempotency_key: str) -> Any: ...

    def list_blocking(self) -> tuple[Any, ...]: ...


@dataclass(frozen=True)
class StaticExecutionGuard:
    """Fixed allow/block — used for kill-switch / session tests."""

    allowed: bool
    reason: str = "static_guard"

    def evaluate(self, plan: ExecutionPlan) -> GuardDecision:
        del plan
        if self.allowed:
            return GuardDecision(allowed=True, reason="ok")
        return GuardDecision(allowed=False, reason=self.reason)


@dataclass(frozen=True)
class EventEligibilityGuard:
    """Reject CATCH_UP / REPLAY for broker-capable orchestration."""

    def evaluate(self, plan: ExecutionPlan) -> GuardDecision:
        if is_broker_eligible(plan.event_kind):
            return GuardDecision(allowed=True, reason="LIVE_EVENT")
        return GuardDecision(
            allowed=False,
            reason=f"event_kind={plan.event_kind.value} not broker-eligible",
        )


@dataclass
class UnresolvedIntentGuard:
    """
    Global safety: any CREATED / IN_FLIGHT / UNKNOWN blocks a *new* plan.

    Same idempotency key is handled by the orchestrator as duplicate (no submit).
    Scope: single-process DurableIntentStore (not distributed exactly-once).
    """

    store: IntentBlockingView

    def evaluate(self, plan: ExecutionPlan) -> GuardDecision:
        from exness_bot.execution.idempotency import idempotency_key_for_plan

        key = idempotency_key_for_plan(plan)
        existing = self.store.get_by_key(key)
        if existing is not None:
            return GuardDecision(allowed=True, reason="existing_key")
        blocking = self.store.list_blocking()
        if not blocking:
            return GuardDecision(allowed=True, reason="no_blocking_intents")
        sample = blocking[0]
        lifecycle = getattr(sample, "lifecycle", None)
        intent_id = getattr(sample, "intent_id", "?")
        life_label = getattr(lifecycle, "value", str(lifecycle))
        return GuardDecision(
            allowed=False,
            reason=(
                f"unresolved {life_label} intent {intent_id} blocks new execution"
            ),
        )


@dataclass(frozen=True)
class CompositeExecutionGuard:
    guards: tuple[ExecutionGuard, ...]

    def evaluate(self, plan: ExecutionPlan) -> GuardDecision:
        for guard in self.guards:
            decision = guard.evaluate(plan)
            if not decision.allowed:
                return decision
        return GuardDecision(allowed=True, reason="all_guards_passed")


def default_orchestration_guards(store: IntentBlockingView) -> CompositeExecutionGuard:
    """Standard Phase 12.6 guards for Fake/Paper orchestration."""
    return CompositeExecutionGuard(
        guards=(
            EventEligibilityGuard(),
            UnresolvedIntentGuard(store=store),
        )
    )
