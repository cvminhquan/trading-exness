"""Deterministic candle wick morphology — SNAPSHOT DESCRIPTIVE only.

Does NOT affect MTF score, ExecutionCandidate, or strategy eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.domain.models import Candle
from exness_bot.market_analysis.technical_snapshot.models import (
    LevelContext,
    WickMorphology,
    WickPattern,
)

# Frozen snapshot descriptive constants (not strategy thresholds).
WICK_BODY_MULTIPLIER = 2.0
WICK_RANGE_SHARE_MIN = 0.40
UPPER_CLOSE_POSITION_MAX = 0.60
LOWER_CLOSE_POSITION_MIN = 0.40
NEAR_LEVEL_ATR = 0.35  # align with patterns.py proximity band
EPSILON = 1e-12


@dataclass(frozen=True)
class WickRaw:
    body: float
    range_size: float
    upper_wick: float
    lower_wick: float
    close_position: float | None


def compute_wick_raw(candle: Candle) -> WickRaw:
    o = float(candle.open)
    h = float(candle.high)
    low = float(candle.low)
    c = float(candle.close)
    body = abs(c - o)
    range_size = h - low
    upper = h - max(o, c)
    lower = min(o, c) - low
    close_pos = None if range_size <= EPSILON else (c - low) / range_size
    return WickRaw(
        body=body,
        range_size=max(0.0, range_size),
        upper_wick=max(0.0, upper),
        lower_wick=max(0.0, lower),
        close_position=close_pos,
    )


def classify_wick_pattern(raw: WickRaw) -> WickPattern:
    if raw.range_size <= EPSILON:
        return WickPattern.NO_CLEAR_REJECTION
    body_floor = max(raw.body, EPSILON)
    upper_ok = (
        raw.upper_wick >= WICK_BODY_MULTIPLIER * body_floor
        and (raw.upper_wick / raw.range_size) >= WICK_RANGE_SHARE_MIN
        and raw.close_position is not None
        and raw.close_position <= UPPER_CLOSE_POSITION_MAX
    )
    lower_ok = (
        raw.lower_wick >= WICK_BODY_MULTIPLIER * body_floor
        and (raw.lower_wick / raw.range_size) >= WICK_RANGE_SHARE_MIN
        and raw.close_position is not None
        and raw.close_position >= LOWER_CLOSE_POSITION_MIN
    )
    if upper_ok and not lower_ok:
        return WickPattern.UPPER_WICK_REJECTION
    if lower_ok and not upper_ok:
        return WickPattern.LOWER_WICK_REJECTION
    return WickPattern.NO_CLEAR_REJECTION


def _ratio(num: float, den: float) -> float | None:
    if den < EPSILON:
        return None
    return round(num / den, 6)


def build_wick_morphology(
    candle: Candle,
    *,
    atr14: float | None,
    nearest_support: float | None,
    nearest_resistance: float | None,
    close: float | None = None,
) -> WickMorphology:
    raw = compute_wick_raw(candle)
    pattern = classify_wick_pattern(raw)
    px = float(close if close is not None else candle.close)
    near_sup = False
    near_res = False
    dist_sup_atr: float | None = None
    dist_res_atr: float | None = None
    if atr14 is not None and atr14 > EPSILON:
        if nearest_support is not None:
            dist_sup_atr = abs(px - nearest_support) / atr14
            near_sup = dist_sup_atr <= NEAR_LEVEL_ATR
        if nearest_resistance is not None:
            dist_res_atr = abs(px - nearest_resistance) / atr14
            near_res = dist_res_atr <= NEAR_LEVEL_ATR

    if near_res and not near_sup:
        level_ctx = LevelContext.AT_RESISTANCE
    elif near_sup and not near_res:
        level_ctx = LevelContext.AT_SUPPORT
    else:
        level_ctx = LevelContext.NO_LEVEL_CONTEXT

    range_atr = None
    if atr14 is not None and atr14 > EPSILON:
        range_atr = round(raw.range_size / atr14, 6)

    return WickMorphology(
        body_size=round(raw.body, 8),
        range_size=round(raw.range_size, 8),
        upper_wick_size=round(raw.upper_wick, 8),
        lower_wick_size=round(raw.lower_wick, 8),
        body_to_range_ratio=_ratio(raw.body, raw.range_size),
        upper_wick_to_body_ratio=_ratio(raw.upper_wick, max(raw.body, EPSILON)),
        lower_wick_to_body_ratio=_ratio(raw.lower_wick, max(raw.body, EPSILON)),
        close_position_in_range=(
            None if raw.close_position is None else round(raw.close_position, 6)
        ),
        range_atr=range_atr,
        pattern=pattern.value,
        level_context=level_ctx.value,
        near_support=near_sup,
        near_resistance=near_res,
        nearest_support_distance_atr=(
            None if dist_sup_atr is None else round(dist_sup_atr, 6)
        ),
        nearest_resistance_distance_atr=(
            None if dist_res_atr is None else round(dist_res_atr, 6)
        ),
    )
