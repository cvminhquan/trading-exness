"""Swing / level / move / pullback helpers for snapshot builder."""

from __future__ import annotations

from exness_bot.domain.models import Candle
from exness_bot.market_analysis.levels import StructureLevel
from exness_bot.market_analysis.structure import LabeledSwing
from exness_bot.market_analysis.swings import SwingKind
from exness_bot.market_analysis.technical_snapshot.models import (
    LevelDistance,
    PriceMove,
    PullbackSnapshot,
    PullbackState,
    SwingPoint,
    TrendSegment,
)
from exness_bot.market_analysis.technical_snapshot.wick_detector import NEAR_LEVEL_ATR


def labeled_swings_to_points(
    labeled: list[LabeledSwing],
    *,
    limit: int = 8,
) -> list[SwingPoint]:
    recent = labeled[-limit:] if len(labeled) > limit else labeled
    out: list[SwingPoint] = []
    for item in recent:
        kind = (
            "SWING_HIGH"
            if item.swing.kind == SwingKind.HIGH
            else "SWING_LOW"
        )
        out.append(
            SwingPoint(
                type=kind,
                timestamp=item.swing.timestamp.isoformat(),
                price=round(float(item.swing.price), 8),
                confirmed=True,
                label=None if item.label is None else item.label.value,
            )
        )
    return out


def level_distance(
    level: StructureLevel | None,
    *,
    close: float,
    atr14: float | None,
    timeframe: str,
) -> LevelDistance | None:
    if level is None:
        return None
    dist = close - level.price
    abs_dist = abs(dist)
    pct = None
    if abs(close) > 1e-12:
        pct = round(100.0 * abs_dist / abs(close), 6)
    dist_atr = None
    near = False
    if atr14 is not None and atr14 > 1e-12:
        dist_atr = round(abs_dist / atr14, 6)
        near = dist_atr <= NEAR_LEVEL_ATR
    return LevelDistance(
        price=round(level.price, 8),
        distance_price=round(abs_dist, 8),
        distance_percent=pct,
        distance_atr=dist_atr,
        touch_count=level.touch_count,
        strength=level.strength,
        source_timeframe=timeframe,
        last_test_timestamp=level.last_seen.isoformat(),
        currently_near=near,
    )


def price_levels_from_floats(
    prices: list[float],
    *,
    close: float,
    atr14: float | None,
    timeframe: str,
) -> list[LevelDistance]:
    out: list[LevelDistance] = []
    for p in prices[:8]:
        abs_dist = abs(close - p)
        pct = round(100.0 * abs_dist / abs(close), 6) if abs(close) > 1e-12 else None
        dist_atr = None
        near = False
        if atr14 is not None and atr14 > 1e-12:
            dist_atr = round(abs_dist / atr14, 6)
            near = dist_atr <= NEAR_LEVEL_ATR
        out.append(
            LevelDistance(
                price=round(p, 8),
                distance_price=round(abs_dist, 8),
                distance_percent=pct,
                distance_atr=dist_atr,
                source_timeframe=timeframe,
                currently_near=near,
            )
        )
    return out


def descriptive_moves(candles: list[Candle], atr14: float | None) -> dict[str, PriceMove]:
    """DESCRIPTIVE_IMPULSE — not V2 research impulse."""
    out: dict[str, PriceMove] = {}
    if not candles:
        return out
    last = float(candles[-1].close)
    for n in (1, 3, 4):
        key = f"last_{n}_bar_move"
        if len(candles) <= n:
            out[key] = PriceMove(
                bars=n,
                price_change=None,
                percentage_change=None,
                atr_normalized_change=None,
            )
            continue
        prev = float(candles[-(n + 1)].close)
        change = last - prev
        pct = round(100.0 * change / prev, 6) if abs(prev) > 1e-12 else None
        atr_n = round(change / atr14, 6) if atr14 is not None and atr14 > 1e-12 else None
        out[key] = PriceMove(
            bars=n,
            price_change=round(change, 8),
            percentage_change=pct,
            atr_normalized_change=atr_n,
        )
    return out


def derive_pullback(
    *,
    segment: TrendSegment | None,
    candles: list[Candle],
    atr14: float | None,
) -> PullbackSnapshot | None:
    """Pullback only when a confirmed trend leg exists."""
    if segment is None or len(candles) < 3:
        return None
    closes = [float(c.close) for c in candles]
    current = closes[-1]
    start = segment.start_price
    if segment.direction == "BULLISH":
        # extreme = max close since anchor bar count from end
        window = closes[-(segment.bars + 1) :] if segment.bars > 0 else closes[-5:]
        extreme = max(window)
        if extreme <= start:
            return PullbackSnapshot(
                state=PullbackState.NONE.value,
                trend_leg_start=start,
                trend_leg_extreme=extreme,
                pullback_start=None,
                current_price=current,
                retracement_percent=None,
            )
        if current >= extreme - (0.05 * (atr14 or 0.0)):
            return PullbackSnapshot(
                state=PullbackState.NONE.value,
                trend_leg_start=start,
                trend_leg_extreme=extreme,
                pullback_start=None,
                current_price=current,
                retracement_percent=None,
            )
        leg = extreme - start
        retr = None if leg <= 1e-12 else round(100.0 * (extreme - current) / leg, 4)
        return PullbackSnapshot(
            state=PullbackState.PULLBACK_AGAINST_BULLISH_TREND.value,
            trend_leg_start=start,
            trend_leg_extreme=extreme,
            pullback_start=extreme,
            current_price=current,
            retracement_percent=retr,
        )
    # BEARISH
    window = closes[-(segment.bars + 1) :] if segment.bars > 0 else closes[-5:]
    extreme = min(window)
    if extreme >= start:
        return PullbackSnapshot(
            state=PullbackState.NONE.value,
            trend_leg_start=start,
            trend_leg_extreme=extreme,
            pullback_start=None,
            current_price=current,
            retracement_percent=None,
        )
    if current <= extreme + (0.05 * (atr14 or 0.0)):
        return PullbackSnapshot(
            state=PullbackState.NONE.value,
            trend_leg_start=start,
            trend_leg_extreme=extreme,
            pullback_start=None,
            current_price=current,
            retracement_percent=None,
        )
    leg = start - extreme
    retr = None if leg <= 1e-12 else round(100.0 * (current - extreme) / leg, 4)
    return PullbackSnapshot(
        state=PullbackState.PULLBACK_AGAINST_BEARISH_TREND.value,
        trend_leg_start=start,
        trend_leg_extreme=extreme,
        pullback_start=extreme,
        current_price=current,
        retracement_percent=retr,
    )
