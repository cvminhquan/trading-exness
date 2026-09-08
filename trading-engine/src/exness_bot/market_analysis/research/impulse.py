"""ATR-normalized M15 impulse score — closed candles only, no look-ahead.

Formulas (bar t = last closed candle index):

    move_1 = (close[t] - close[t-1]) / ATR14[t]
    move_3 = (close[t] - close[t-3]) / ATR14[t]
    move_4 = (close[t] - close[t-4]) / ATR14[t]

Normalization (documented, not fit to a single session):

    n(x) = 100 * tanh(x / scale)   # scale default 1.5 ATR units

    impulse = w1*n(move_1) + w3*n(move_3) + w4*n(move_4)

Clamped to [-100, 100]. Uses only closes and ATR available at t.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from exness_bot.market_analysis.research.freeze import DEFAULT_V2_CONFIG, V2FrozenConfig


@dataclass(frozen=True)
class ImpulseBreakdown:
    move_1: float | None
    move_3: float | None
    move_4: float | None
    impulse_score: float
    atr: float | None


def _tanh_norm(x: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return 100.0 * math.tanh(x / scale)


def compute_impulse_score(
    closes: list[float],
    atr14: float | None,
    *,
    config: V2FrozenConfig = DEFAULT_V2_CONFIG,
) -> ImpulseBreakdown:
    """Compute impulse from closed closes ending at last element."""
    if atr14 is None or atr14 <= 0 or len(closes) < 5:
        return ImpulseBreakdown(
            move_1=None,
            move_3=None,
            move_4=None,
            impulse_score=0.0,
            atr=atr14,
        )

    c_t = closes[-1]
    move_1 = (c_t - closes[-2]) / atr14
    move_3 = (c_t - closes[-4]) / atr14
    move_4 = (c_t - closes[-5]) / atr14

    scale = config.impulse_tanh_scale
    raw = (
        config.impulse_w1 * _tanh_norm(move_1, scale)
        + config.impulse_w3 * _tanh_norm(move_3, scale)
        + config.impulse_w4 * _tanh_norm(move_4, scale)
    )
    score = max(-100.0, min(100.0, raw))
    return ImpulseBreakdown(
        move_1=round(move_1, 6),
        move_3=round(move_3, 6),
        move_4=round(move_4, 6),
        impulse_score=round(score, 2),
        atr=atr14,
    )
