"""Tick-volume analysis (MT5 tick_volume — not exchange real volume)."""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.domain.models import Candle


@dataclass(frozen=True)
class VolumeSnapshot:
    source: str  # TICK_VOLUME
    current: float | None
    average: float | None
    ratio: float | None
    state: str  # HIGH | NORMAL | LOW | UNKNOWN


def analyze_tick_volume(
    candles: list[Candle],
    *,
    average_period: int = 20,
    high_ratio: float = 1.5,
    low_ratio: float = 0.7,
) -> VolumeSnapshot:
    """Compare latest closed candle tick_volume to prior average.

    Uses ``tick_volume`` when present; falls back to ``volume``.
    Source is always labeled TICK_VOLUME for MT5 semantics.
    """
    if len(candles) < 2:
        return VolumeSnapshot("TICK_VOLUME", None, None, None, "UNKNOWN")

    def _vol(c: Candle) -> float:
        tv = float(getattr(c, "tick_volume", 0.0) or 0.0)
        if tv > 0:
            return tv
        return float(c.volume or 0.0)

    current = _vol(candles[-1])
    history = candles[-(average_period + 1) : -1]
    if not history:
        return VolumeSnapshot("TICK_VOLUME", current, None, None, "UNKNOWN")
    avg = sum(_vol(c) for c in history) / len(history)
    if avg <= 0:
        return VolumeSnapshot("TICK_VOLUME", current, avg, None, "UNKNOWN")
    ratio = current / avg
    if ratio >= high_ratio:
        state = "HIGH"
    elif ratio < low_ratio:
        state = "LOW"
    else:
        state = "NORMAL"
    return VolumeSnapshot("TICK_VOLUME", current, avg, round(ratio, 6), state)
