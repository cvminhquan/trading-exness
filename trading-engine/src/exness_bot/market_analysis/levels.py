"""Support/resistance from confirmed swings with ATR clustering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from exness_bot.market_analysis.swings import ConfirmedSwing, SwingKind


class LevelType(StrEnum):
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"


@dataclass(frozen=True)
class StructureLevel:
    price: float
    level_type: LevelType
    touch_count: int
    strength: float
    first_seen: datetime
    last_seen: datetime


def _cluster_prices(
    swings: list[ConfirmedSwing],
    *,
    level_type: LevelType,
    tolerance: float,
) -> list[StructureLevel]:
    if not swings:
        return []
    ordered = sorted(swings, key=lambda s: s.index)
    clusters: list[list[ConfirmedSwing]] = []
    for swing in ordered:
        placed = False
        for cluster in clusters:
            center = sum(s.price for s in cluster) / len(cluster)
            if abs(swing.price - center) <= tolerance:
                cluster.append(swing)
                placed = True
                break
        if not placed:
            clusters.append([swing])

    levels: list[StructureLevel] = []
    for cluster in clusters:
        price = sum(s.price for s in cluster) / len(cluster)
        touch = len(cluster)
        # Simple explainable strength: touches + mild boost for more recent last touch
        strength = float(touch)
        levels.append(
            StructureLevel(
                price=round(price, 8),
                level_type=level_type,
                touch_count=touch,
                strength=strength,
                first_seen=cluster[0].timestamp,
                last_seen=cluster[-1].timestamp,
            )
        )
    levels.sort(key=lambda level: level.price)
    return levels


def build_support_resistance(
    swings: list[ConfirmedSwing],
    *,
    atr14: float | None,
    cluster_atr_multiplier: float = 0.25,
    point: float = 0.01,
) -> tuple[list[StructureLevel], list[StructureLevel]]:
    """Build support (swing lows) and resistance (swing highs) with clustering."""
    if atr14 is not None and atr14 > 0:
        tolerance = atr14 * cluster_atr_multiplier
    else:
        tolerance = max(point * 50, point)

    lows = [s for s in swings if s.kind == SwingKind.LOW]
    highs = [s for s in swings if s.kind == SwingKind.HIGH]
    supports = _cluster_prices(lows, level_type=LevelType.SUPPORT, tolerance=tolerance)
    resistances = _cluster_prices(
        highs, level_type=LevelType.RESISTANCE, tolerance=tolerance
    )
    return supports, resistances


def nearest_support_below(
    supports: list[StructureLevel], entry: float
) -> StructureLevel | None:
    below = [level for level in supports if level.price < entry]
    if not below:
        return None
    return max(below, key=lambda level: level.price)


def nearest_resistance_above(
    resistances: list[StructureLevel], entry: float
) -> StructureLevel | None:
    above = [level for level in resistances if level.price > entry]
    if not above:
        return None
    return min(above, key=lambda level: level.price)
