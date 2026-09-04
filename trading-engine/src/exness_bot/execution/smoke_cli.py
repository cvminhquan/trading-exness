"""CLI diagnostic for Phase 12.6 orchestration — Fake/Paper only."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import structlog

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalDirection
from exness_bot.execution.eligibility import ExecutionEventKind
from exness_bot.execution.guard import default_orchestration_guards
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.plan import ExecutionPlan
from exness_bot.execution.spy import SpyExecutionPort
from exness_bot.paper_execution.contract import AckStatus
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from exness_bot.paper_execution.models import PaperSnapshot

logger = structlog.get_logger(__name__)


def run_orchestration_smoke(*, side: SignalDirection = SignalDirection.LONG) -> int:
    """
    End-to-end Fake execution orchestration diagnostic.

    NEVER instantiates LiveMT5ExecutionTransport / MT5Executor.
    """
    settings = Settings()
    now = datetime.now(tz=UTC)
    config = BacktestConfig.from_settings(settings)
    symbol = config.to_symbol_info(close_price=2350.0).model_copy(
        update={
            "stops_level": config.paper_stops_level,
            "freeze_level": config.paper_freeze_level,
        }
    )

    paper = PaperExecutor(PaperSnapshot.initial(10_000.0), config=config)
    store = SnapshotIntentStore(paper, persist=lambda: None)
    port = SpyExecutionPort(responses=AckStatus.FILLED, fill_price=symbol.ask)
    orch = ExecutionOrchestrator(
        store=store,
        port=port,
        clock=lambda: now,
        guard=default_orchestration_guards(store),
    )
    signal_id = f"orch-smoke-{uuid4().hex[:8]}"
    volume = max(float(symbol.volume_min or 0.01), 0.01)
    if side is SignalDirection.LONG:
        stop_loss = symbol.bid * 0.99
        take_profit = symbol.ask * 1.01
    else:
        stop_loss = symbol.ask * 1.01
        take_profit = symbol.bid * 0.99
    plan = ExecutionPlan(
        plan_id=f"plan-{signal_id}",
        signal_id=signal_id,
        strategy_id="execution_orchestration_smoke_v1",
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        side=side,
        requested_volume=volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        signal_timestamp=now,
        decision_timestamp=now,
        reason="Phase 12.6 diagnostic — Fake port only",
        source="execution-orchestration-smoke",
        event_kind=ExecutionEventKind.LIVE,
    )
    result = orch.execute(plan, quote=symbol)

    lines = [
        "",
        "==================================================",
        "EXECUTION ORCHESTRATION SMOKE (Phase 12.6)",
        "==================================================",
        "BROKER EXECUTION: DISABLED",
        "TRANSPORT: FAKE/PAPER",
        f"signal_id: {plan.signal_id}",
        "risk_decision: synthetic_approved (diagnostic)",
        f"execution_plan: {plan.plan_id}",
        f"intent_id: {result.intent.intent_id if result.intent else None}",
        f"idempotency_key: {result.idempotency_key}",
        f"lifecycle: {result.lifecycle.value if result.lifecycle else None}",
        f"execution_port_calls: {result.port_calls}",
        f"result: {result.outcome} — {result.message}",
        "==================================================",
        "",
    ]
    print("\n".join(lines))
    logger.info(
        "execution_orchestration_smoke",
        outcome=result.outcome,
        port_calls=result.port_calls,
        lifecycle=result.lifecycle.value if result.lifecycle else None,
        broker_execution="DISABLED",
        transport="FAKE",
    )
    return 0 if result.outcome in {
        "FILLED",
        "REJECTED",
        "UNKNOWN",
        "DUPLICATE",
        "BLOCKED",
    } else 1
