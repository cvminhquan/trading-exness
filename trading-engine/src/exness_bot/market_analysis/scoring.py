"""Deterministic per-timeframe scoring (-100..+100) and confidence (0..100).

Confidence = EVIDENCE_ALIGNMENT — NOT predicted win probability.

Documented component weights (sum = 1.0):
  trendScore      0.30
  structureScore  0.25
  momentumScore   0.20
  locationScore   0.15
  volumeScore     0.10
"""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.market_analysis.structure import StructureLabel
from exness_bot.market_analysis.trend import TrendLabel

WEIGHT_TREND = 0.30
WEIGHT_STRUCTURE = 0.25
WEIGHT_MOMENTUM = 0.20
WEIGHT_LOCATION = 0.15
WEIGHT_VOLUME = 0.10


@dataclass(frozen=True)
class ScoreBreakdown:
    trend_score: float
    structure_score: float
    momentum_score: float
    location_score: float
    volume_score: float
    total_score: float
    confidence: float
    direction: str  # LONG | SHORT | NEUTRAL


def _trend_component(trend: TrendLabel) -> float:
    if trend == TrendLabel.UPTREND:
        return 100.0
    if trend == TrendLabel.DOWNTREND:
        return -100.0
    if trend == TrendLabel.RANGE:
        return 0.0
    return 0.0


def _structure_component(structure: StructureLabel) -> float:
    if structure == StructureLabel.BULLISH:
        return 100.0
    if structure == StructureLabel.BEARISH:
        return -100.0
    if structure == StructureLabel.RANGE:
        return 0.0
    return 0.0


def _momentum_component(*, rsi: float | None, macd_momentum: str) -> float:
    score = 0.0
    parts = 0
    if rsi is not None:
        parts += 1
        if rsi >= 55:
            score += min(100.0, (rsi - 50) * 4)
        elif rsi <= 45:
            score += max(-100.0, (rsi - 50) * 4)
    if macd_momentum == "BULLISH":
        parts += 1
        score += 80.0
    elif macd_momentum == "BEARISH":
        parts += 1
        score += -80.0
    elif macd_momentum == "NEUTRAL":
        parts += 1
    if parts == 0:
        return 0.0
    return max(-100.0, min(100.0, score / parts))


def _location_component(
    *,
    close: float | None,
    support: float | None,
    resistance: float | None,
    atr: float | None,
) -> float:
    if close is None or atr is None or atr <= 0:
        return 0.0
    # Near support → bullish location; near resistance → bearish
    score = 0.0
    if support is not None:
        dist = (close - support) / atr
        if dist <= 0.5:
            score += 80.0
        elif dist <= 1.0:
            score += 40.0
    if resistance is not None:
        dist = (resistance - close) / atr
        if dist <= 0.5:
            score -= 80.0
        elif dist <= 1.0:
            score -= 40.0
    return max(-100.0, min(100.0, score))


def _volume_component(state: str, direction_hint: float) -> float:
    if state == "HIGH":
        return 60.0 if direction_hint >= 0 else -60.0
    if state == "LOW":
        return -20.0 if direction_hint >= 0 else 20.0
    if state == "NORMAL":
        return 10.0 if direction_hint > 0 else (-10.0 if direction_hint < 0 else 0.0)
    return 0.0


def compute_timeframe_score(
    *,
    trend: TrendLabel,
    structure: StructureLabel,
    rsi: float | None,
    macd_momentum: str,
    close: float | None,
    support: float | None,
    resistance: float | None,
    atr: float | None,
    volume_state: str,
) -> ScoreBreakdown:
    trend_s = _trend_component(trend)
    struct_s = _structure_component(structure)
    mom_s = _momentum_component(rsi=rsi, macd_momentum=macd_momentum)
    loc_s = _location_component(
        close=close, support=support, resistance=resistance, atr=atr
    )
    hint = trend_s + struct_s + mom_s
    vol_s = _volume_component(volume_state, hint)

    total = (
        WEIGHT_TREND * trend_s
        + WEIGHT_STRUCTURE * struct_s
        + WEIGHT_MOMENTUM * mom_s
        + WEIGHT_LOCATION * loc_s
        + WEIGHT_VOLUME * vol_s
    )
    total = max(-100.0, min(100.0, total))

    if total >= 25:
        direction = "LONG"
    elif total <= -25:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    # Confidence = how aligned components are with the chosen direction
    components = [trend_s, struct_s, mom_s, loc_s, vol_s]
    if direction == "NEUTRAL":
        confidence = max(0.0, 50.0 - abs(total))
    else:
        sign = 1.0 if direction == "LONG" else -1.0
        agreeing = sum(1 for c in components if c * sign > 0)
        magnitude = abs(total)
        confidence = min(100.0, agreeing / len(components) * 55.0 + magnitude * 0.45)

    return ScoreBreakdown(
        trend_score=round(trend_s, 2),
        structure_score=round(struct_s, 2),
        momentum_score=round(mom_s, 2),
        location_score=round(loc_s, 2),
        volume_score=round(vol_s, 2),
        total_score=round(total, 2),
        confidence=round(confidence, 2),
        direction=direction,
    )
