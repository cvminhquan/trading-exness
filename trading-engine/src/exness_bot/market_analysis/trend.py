"""Deterministic multi-evidence trend classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from exness_bot.market_analysis.structure import StructureLabel


class TrendLabel(StrEnum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TrendEvidence:
    price_above_ema200: bool | None
    ema20_above_ema50: bool | None
    ema50_above_ema200: bool | None
    ema20_slope_positive: bool | None
    structure: StructureLabel | None
    bullish_count: int
    bearish_count: int
    total_checks: int


def _slope_positive(ema_series_tail: list[float]) -> bool | None:
    if len(ema_series_tail) < 2:
        return None
    return ema_series_tail[-1] > ema_series_tail[0]


def classify_trend(
    *,
    close: float | None,
    ema20: float | None,
    ema50: float | None,
    ema200: float | None,
    ema20_tail: list[float] | None,
    structure: StructureLabel | None,
) -> tuple[TrendLabel, TrendEvidence]:
    """Score multi-factor trend; mixed → RANGE; insufficient → UNKNOWN."""
    checks: list[tuple[str, bool | None]] = []
    price_above = None if close is None or ema200 is None else close > ema200
    e20_e50 = None if ema20 is None or ema50 is None else ema20 > ema50
    e50_e200 = None if ema50 is None or ema200 is None else ema50 > ema200
    slope = _slope_positive(ema20_tail or [])

    checks.append(("price_above_ema200", price_above))
    checks.append(("ema20_above_ema50", e20_e50))
    checks.append(("ema50_above_ema200", e50_e200))
    checks.append(("ema20_slope_positive", slope))

    bullish = 0
    bearish = 0
    known = 0
    for _, value in checks:
        if value is None:
            continue
        known += 1
        if value:
            bullish += 1
        else:
            bearish += 1

    if structure == StructureLabel.BULLISH:
        bullish += 1
        known += 1
    elif structure == StructureLabel.BEARISH:
        bearish += 1
        known += 1
    elif structure == StructureLabel.RANGE:
        known += 1  # mixed contribution — neither side

    evidence = TrendEvidence(
        price_above_ema200=price_above,
        ema20_above_ema50=e20_e50,
        ema50_above_ema200=e50_e200,
        ema20_slope_positive=slope,
        structure=structure,
        bullish_count=bullish,
        bearish_count=bearish,
        total_checks=known,
    )

    if known < 3:
        return TrendLabel.UNKNOWN, evidence
    if bullish >= known - 1 and bullish >= 3 and bullish > bearish:
        return TrendLabel.UPTREND, evidence
    if bearish >= known - 1 and bearish >= 3 and bearish > bullish:
        return TrendLabel.DOWNTREND, evidence
    return TrendLabel.RANGE, evidence
