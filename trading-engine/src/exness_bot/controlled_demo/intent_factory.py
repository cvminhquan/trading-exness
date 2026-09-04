"""Build exactly one controlled DEMO ExecutionIntent — not from Strategy."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from exness_bot.domain.enums import SignalAction, SignalDirection, Timeframe
from exness_bot.domain.execution_validation import (
    validate_sl_tp_distance,
    validate_stops_metadata,
    validate_volume,
)
from exness_bot.domain.models import (
    AccountInfo,
    ApprovedOrderPlan,
    IndicatorSnapshot,
    Signal,
    SymbolInfo,
)
from exness_bot.paper_execution.contract import ExecutionIntent
from exness_bot.risk.manager import RiskManager
from exness_bot.risk.models import RiskState

CONTROLLED_STRATEGY_ID = "controlled_demo_smoke_v1"


def build_controlled_demo_intent(
    *,
    symbol: SymbolInfo,
    canonical_symbol: str,
    timeframe: str,
    now: datetime,
    account: AccountInfo,
    risk: RiskManager,
    side: SignalDirection = SignalDirection.LONG,
) -> ExecutionIntent:
    """
    Explicit smoke intent: smallest valid volume, geometry from stops_level.

    Still passes RiskManager.assess. Does NOT use the signal-engine / EMA / RSI path.
    """
    stops = validate_stops_metadata(symbol)
    if not stops.ok:
        msg = stops.message or stops.code.value
        raise ValueError(msg)

    assert symbol.stops_level is not None
    min_dist = max(symbol.stops_level, symbol.freeze_level or 0) * symbol.point
    if min_dist <= 0:
        min_dist = symbol.point * 10

    entry = symbol.ask if side == SignalDirection.LONG else symbol.bid
    # Wide enough for stops + room for risk ATR path
    atr = max(min_dist * 3.0, symbol.point * 50)
    if side == SignalDirection.LONG:
        sl = entry - atr * 1.5
        tp = entry + atr * 1.5 * 2.0
        action = SignalAction.BUY
    else:
        sl = entry + atr * 1.5
        tp = entry - atr * 1.5 * 2.0
        action = SignalAction.SELL

    indicators = IndicatorSnapshot(
        timestamp=now,
        ema_20=entry,
        ema_50=entry,
        ema_200=entry,
        rsi_14=55.0,
        atr_14=atr,
    )
    try:
        tf = Timeframe(timeframe)
    except ValueError:
        tf = Timeframe.M15
    signal = Signal.create(
        action=action,
        strategy_name=CONTROLLED_STRATEGY_ID,
        symbol=canonical_symbol,
        timeframe=tf,
        entry_price=entry,
        timestamp=now,
        indicators=indicators,
        reason="Phase 12.4 controlled DEMO smoke — not a strategy signal.",
    )
    decision = risk.assess(
        signal,
        account,
        symbol,
        [],
        RiskState(
            day_start_equity=max(account.equity, 0.01),
            peak_equity=max(account.equity, 0.01),
        ),
    )
    if not isinstance(decision, ApprovedOrderPlan):
        msg = f"RiskManager rejected controlled demo: {decision.reason}"
        raise ValueError(msg)

    volume = symbol.volume_min
    if volume > decision.volume + 1e-12:
        msg = (
            f"Risk-approved volume {decision.volume} below broker volume_min {volume}"
        )
        raise ValueError(msg)

    vol_check = validate_volume(volume, symbol)
    if not vol_check.ok:
        raise ValueError(vol_check.message or vol_check.code.value)

    # Prefer risk SL/TP when they pass distance; else geometric
    stop_loss = decision.stop_loss
    take_profit = decision.take_profit
    distance = validate_sl_tp_distance(
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        side=side,
        symbol=symbol,
    )
    if not distance.ok:
        stop_loss = sl
        take_profit = tp
        distance = validate_sl_tp_distance(
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            side=side,
            symbol=symbol,
        )
        if not distance.ok:
            raise ValueError(distance.message or distance.code.value)

    seq = uuid4().hex[:12]
    return ExecutionIntent(
        intent_id=f"demo-smoke-{seq}",
        idempotency_key=f"controlled-demo-{seq}",
        symbol=canonical_symbol,
        timeframe=timeframe,
        strategy=CONTROLLED_STRATEGY_ID,
        side=side,
        requested_quantity=volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        created_at=now,
        source="phase_12_4_controlled_demo",
    )
