"""Deterministic execution identity — not random UUID as sole duplicate protection."""

from __future__ import annotations

from datetime import datetime

from exness_bot.domain.enums import SignalDirection
from exness_bot.execution.plan import ExecutionPlan


def build_execution_idempotency_key(
    *,
    strategy_id: str,
    symbol: str,
    timeframe: str,
    closed_candle_timestamp: datetime,
    signal_id: str,
    side: SignalDirection,
) -> str:
    """
    Deterministic key for the same logical trade decision.

    Same inputs → same key → at most one ExecutionPort.submit.
    """
    ts = closed_candle_timestamp.isoformat()
    return (
        f"{strategy_id}|{symbol}|{timeframe}|{ts}|{signal_id}|{side.value}"
    )


def idempotency_key_for_plan(plan: ExecutionPlan) -> str:
    """Prefer explicit metadata override; otherwise derive from plan fields."""
    override = plan.metadata.get("idempotency_key")
    if isinstance(override, str) and override.strip():
        return override.strip()
    return build_execution_idempotency_key(
        strategy_id=plan.strategy_id,
        symbol=plan.symbol,
        timeframe=plan.timeframe,
        closed_candle_timestamp=plan.signal_timestamp,
        signal_id=plan.signal_id,
        side=plan.side,
    )
