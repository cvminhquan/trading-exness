"""Build exactly one controlled DEMO ExecutionIntent / ExecutionPlan — not from Strategy.

Position sizing is an explicit smoke-test constant (0.01 lots). This path must NEVER
use strategy equity-based sizing — that produced oversized DEMO intents
(e.g. 38.99 lots) when account equity was large and synthetic ATR stops were tight.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.execution_validation import (
    validate_sl_tp_distance,
    validate_stops_metadata,
    validate_volume,
)
from exness_bot.domain.models import SymbolInfo
from exness_bot.execution.eligibility import ExecutionEventKind
from exness_bot.execution.plan import ExecutionPlan
from exness_bot.paper_execution.contract import ExecutionIntent

CONTROLLED_STRATEGY_ID = "controlled_demo_smoke_v1"
CONTROLLED_DEMO_TEST_VOLUME = 0.01
CONTROLLED_DEMO_SOURCE = "phase_12_9_controlled_demo"


def resolve_controlled_demo_volume(
    *,
    symbol: SymbolInfo,
    max_position_lots: float,
    requested: float = CONTROLLED_DEMO_TEST_VOLUME,
) -> float:
    """
    Validate the explicit controlled-DEMO test volume.

    Does not clamp strategy sizes. Rejects anything other than the auditable
    smoke constant once broker / max-lots ceiling checks are applied.
    """
    if abs(requested - CONTROLLED_DEMO_TEST_VOLUME) > 1e-12:
        msg = (
            f"Controlled DEMO smoke volume must be exactly "
            f"{CONTROLLED_DEMO_TEST_VOLUME}, got {requested}"
        )
        raise ValueError(msg)

    if max_position_lots <= 0:
        msg = f"MAX_POSITION_LOTS invalid: {max_position_lots}"
        raise ValueError(msg)

    if requested > max_position_lots + 1e-12:
        msg = (
            f"Controlled DEMO test volume {requested} exceeds "
            f"MAX_POSITION_LOTS={max_position_lots}"
        )
        raise ValueError(msg)

    vol_check = validate_volume(requested, symbol)
    if not vol_check.ok:
        raise ValueError(vol_check.message or vol_check.code.value)

    return requested


def _geometry_sl_tp(
    *,
    symbol: SymbolInfo,
    side: SignalDirection,
) -> tuple[float, float, float]:
    """Entry + geometric SL/TP from stops metadata — not strategy ATR risk sizing."""
    stops = validate_stops_metadata(symbol)
    if not stops.ok:
        msg = stops.message or stops.code.value
        raise ValueError(msg)

    assert symbol.stops_level is not None
    min_dist = max(symbol.stops_level, symbol.freeze_level or 0) * symbol.point
    if min_dist <= 0:
        min_dist = symbol.point * 10

    # Wide enough for broker stops_level; independent of strategy ATR risk budget.
    atr = max(min_dist * 3.0, symbol.point * 50)
    entry = symbol.ask if side == SignalDirection.LONG else symbol.bid
    if side == SignalDirection.LONG:
        sl = entry - atr * 1.5
        tp = entry + atr * 1.5 * 2.0
    else:
        sl = entry + atr * 1.5
        tp = entry - atr * 1.5 * 2.0

    distance = validate_sl_tp_distance(
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        side=side,
        symbol=symbol,
    )
    if not distance.ok:
        raise ValueError(distance.message or distance.code.value)

    return entry, sl, tp


def build_controlled_demo_plan(
    *,
    symbol: SymbolInfo,
    canonical_symbol: str,
    timeframe: str,
    now: datetime,
    max_position_lots: float,
    side: SignalDirection = SignalDirection.LONG,
) -> ExecutionPlan:
    """
    Deterministic smoke ExecutionPlan: SIDE + VOLUME=0.01 after validation.

    Does NOT call strategy risk sizing. Does NOT use strategy signals.
    """
    volume = resolve_controlled_demo_volume(
        symbol=symbol,
        max_position_lots=max_position_lots,
    )
    _entry, stop_loss, take_profit = _geometry_sl_tp(symbol=symbol, side=side)
    seq = uuid4().hex[:12]
    signal_id = f"demo-smoke-sig-{seq}"
    return ExecutionPlan(
        plan_id=f"demo-smoke-plan-{seq}",
        signal_id=signal_id,
        strategy_id=CONTROLLED_STRATEGY_ID,
        symbol=canonical_symbol,
        timeframe=timeframe,
        side=side,
        requested_volume=volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        signal_timestamp=now,
        decision_timestamp=now,
        reason="Phase 12.9 controlled DEMO smoke — explicit 0.01 lot test, not strategy.",
        source=CONTROLLED_DEMO_SOURCE,
        event_kind=ExecutionEventKind.LIVE,
        metadata={"idempotency_key": f"controlled-demo-{seq}"},
    )


def build_controlled_demo_intent(
    *,
    symbol: SymbolInfo,
    canonical_symbol: str,
    timeframe: str,
    now: datetime,
    max_position_lots: float,
    side: SignalDirection = SignalDirection.LONG,
) -> ExecutionIntent:
    """
    Explicit smoke intent: VOLUME = CONTROLLED_DEMO_TEST_VOLUME (0.01).

    Isolated from normal strategy position sizing.
    """
    plan = build_controlled_demo_plan(
        symbol=symbol,
        canonical_symbol=canonical_symbol,
        timeframe=timeframe,
        now=now,
        max_position_lots=max_position_lots,
        side=side,
    )
    return ExecutionIntent(
        intent_id=f"demo-smoke-{plan.plan_id.removeprefix('demo-smoke-plan-')}",
        idempotency_key=str(plan.metadata["idempotency_key"]),
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
