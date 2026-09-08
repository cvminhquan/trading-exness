"""Entry / ATR SL / TP proposal helpers (analysis only — no order_send)."""

from __future__ import annotations

from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.execution_validation import validate_sl_tp_distance
from exness_bot.domain.models import SymbolInfo
from exness_bot.market_analysis.models import AnalysisReason, AnalysisSignal, TradePlan
from exness_bot.market_analysis.prices import normalize_price
from exness_bot.market_analysis.signal import reason
from exness_bot.risk.stops import (
    calculate_stop_loss,
    calculate_take_profit,
)


def select_entry_price(signal: AnalysisSignal, symbol: SymbolInfo) -> float:
    """BUY uses ASK; SELL uses BID."""
    if signal == AnalysisSignal.BUY:
        return float(symbol.ask)
    if signal == AnalysisSignal.SELL:
        return float(symbol.bid)
    msg = f"No entry price for signal {signal}"
    raise ValueError(msg)


def build_trade_plan(
    *,
    signal: AnalysisSignal,
    symbol: SymbolInfo,
    atr14: float,
    atr_sl_multiplier: float,
    reward_risk_ratio: float,
) -> tuple[TradePlan | None, list[AnalysisReason]]:
    """Build entry/SL/TP from live quote + ATR. Returns blocking reasons if invalid."""
    blocking: list[AnalysisReason] = []
    if signal not in (AnalysisSignal.BUY, AnalysisSignal.SELL):
        return None, blocking

    if atr14 <= 0:
        blocking.append(reason("ATR_AVAILABLE", False, "ATR14 is missing or invalid"))
        return None, blocking

    entry_raw = select_entry_price(signal, symbol)
    entry = normalize_price(entry_raw, symbol)
    direction = (
        SignalDirection.LONG if signal == AnalysisSignal.BUY else SignalDirection.SHORT
    )

    stop_raw = calculate_stop_loss(entry, direction, atr14, atr_sl_multiplier)
    stop_loss = normalize_price(stop_raw, symbol)
    take_profit_raw = calculate_take_profit(
        entry, stop_loss, direction, reward_risk_ratio
    )
    take_profit = normalize_price(take_profit_raw, symbol)

    # Actual R:R from normalized prices
    sl_distance = abs(entry - stop_loss)
    if sl_distance <= 0:
        blocking.append(
            reason("INVALID_SL_DISTANCE", False, "Stop loss distance must be positive")
        )
        return None, blocking
    tp_distance = abs(take_profit - entry)
    actual_rr = tp_distance / sl_distance

    stops_check = validate_sl_tp_distance(
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        side=direction,
        symbol=symbol,
    )
    if not stops_check.ok:
        blocking.append(
            reason(stops_check.code.value, False, stops_check.message or stops_check.code.value)
        )
        # Still return plan for display, but caller marks BLOCKED
        plan = TradePlan(
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=round(actual_rr, 6),
        )
        return plan, blocking

    return (
        TradePlan(
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=round(actual_rr, 6),
        ),
        blocking,
    )
