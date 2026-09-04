"""Map closed candles and strategy output to SignalResult — no broker calls."""

from __future__ import annotations

import math
from typing import TypeGuard

from exness_bot.domain.enums import SignalAction
from exness_bot.domain.models import IndicatorSnapshot, Signal
from exness_bot.signal_engine.models import SignalCondition, SignalKind
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME


def is_finite_number(value: float | None) -> TypeGuard[float]:
    return value is not None and math.isfinite(value)


def indicators_are_valid(snapshot: IndicatorSnapshot) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    mapping = {
        "ema_20": snapshot.ema_20,
        "ema_50": snapshot.ema_50,
        "ema_200": snapshot.ema_200,
        "rsi_14": snapshot.rsi_14,
        "atr_14": snapshot.atr_14,
    }
    for name, value in mapping.items():
        if not is_finite_number(value):
            missing.append(name)
    return (not missing, tuple(missing))


def map_action(action: SignalAction) -> SignalKind:
    if action == SignalAction.BUY:
        return SignalKind.BUY
    if action == SignalAction.SELL:
        return SignalKind.SELL
    return SignalKind.NO_SIGNAL


def build_conditions(
    signal: Signal,
    *,
    rsi_long_min: float,
    rsi_long_max: float,
) -> tuple[SignalCondition, ...]:
    indicators = signal.indicators
    close = signal.entry_price
    ema_20 = indicators.ema_20
    ema_50 = indicators.ema_50
    ema_200 = indicators.ema_200
    rsi_14 = indicators.rsi_14
    atr_14 = indicators.atr_14
    bullish = False
    if is_finite_number(ema_20) and is_finite_number(ema_50) and is_finite_number(ema_200):
        bullish = ema_20 > ema_50 > ema_200
    close_ok = is_finite_number(ema_20) and close > ema_20
    rsi_ok = is_finite_number(rsi_14) and rsi_long_min < rsi_14 < rsi_long_max
    atr_ok = is_finite_number(atr_14)
    rsi_detail = (
        f"RSI trong ({rsi_long_min}, {rsi_long_max})"
        if rsi_ok
        else "RSI không trong vùng xác nhận."
    )
    return (
        SignalCondition(
            id="ema-stack",
            label="EMA 20/50/200",
            detail="EMA20 > EMA50 > EMA200" if bullish else "Chưa đủ điều kiện xếp chồng EMA.",
            satisfied=bool(bullish),
        ),
        SignalCondition(
            id="close-vs-ema20",
            label="Giá đóng vs EMA20",
            detail="Close > EMA20" if close_ok else "Close không trên EMA20.",
            satisfied=bool(close_ok),
        ),
        SignalCondition(
            id="rsi",
            label="RSI 14",
            detail=rsi_detail,
            satisfied=bool(rsi_ok),
        ),
        SignalCondition(
            id="atr",
            label="ATR 14",
            detail="ATR hợp lệ." if atr_ok else "ATR thiếu hoặc không hữu hạn.",
            satisfied=bool(atr_ok),
        ),
        SignalCondition(
            id="strategy",
            label=STRATEGY_NAME,
            detail=signal.reason,
            satisfied=signal.action in {SignalAction.BUY, SignalAction.SELL},
        ),
    )
