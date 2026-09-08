"""Per-timeframe research scoring v2 (does not modify production scoring.py)."""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.market_analysis.research.freeze import DEFAULT_V2_CONFIG, V2FrozenConfig
from exness_bot.market_analysis.research.impulse import ImpulseBreakdown, compute_impulse_score
from exness_bot.market_analysis.research.structure_transition import (
    StructureTransition,
    classify_structure_transition,
    transition_score,
)
from exness_bot.market_analysis.scoring import (
    _location_component,
    _momentum_component,
    _trend_component,
    _volume_component,
)
from exness_bot.market_analysis.structure import StructureSnapshot
from exness_bot.market_analysis.trend import TrendLabel


@dataclass(frozen=True)
class ScoreBreakdownV2:
    trend_score: float
    structure_score: float
    structure_raw_binary: float
    structure_transition: StructureTransition
    momentum_score: float
    location_score: float
    volume_score: float
    impulse_score: float
    impulse: ImpulseBreakdown
    total_score: float
    confidence: float
    direction: str
    conflict_dampened: bool


def _binary_structure_score(snapshot: StructureSnapshot) -> float:
    from exness_bot.market_analysis.structure import StructureLabel

    if snapshot.classification == StructureLabel.BULLISH:
        return 100.0
    if snapshot.classification == StructureLabel.BEARISH:
        return -100.0
    return 0.0


def compute_timeframe_score_v2(
    *,
    trend: TrendLabel,
    structure_snapshot: StructureSnapshot,
    rsi: float | None,
    macd_momentum: str,
    close: float | None,
    support: float | None,
    resistance: float | None,
    atr: float | None,
    volume_state: str,
    closes: list[float],
    apply_impulse: bool = True,
    config: V2FrozenConfig = DEFAULT_V2_CONFIG,
) -> ScoreBreakdownV2:
    """Research scorer: soft structure + optional impulse + conflict dampening."""
    trend_s = _trend_component(trend)
    binary_struct = _binary_structure_score(structure_snapshot)
    transition = classify_structure_transition(structure_snapshot, close=close)
    struct_s = transition_score(transition)

    conflict_dampened = False
    # Stale confirmed structure opposing strong trend → dampen structure pull
    if trend_s * struct_s < 0 and abs(trend_s) >= 99.0 and abs(struct_s) >= 99.0:
        struct_s = struct_s * config.structure_conflict_dampen
        conflict_dampened = True
    elif trend_s * binary_struct < 0 and abs(trend_s) >= 99.0 and abs(binary_struct) >= 99.0:
        # Even if transition softened, record dampening intent for audit cases
        if abs(struct_s) > abs(binary_struct) * config.structure_conflict_dampen:
            struct_s = binary_struct * config.structure_conflict_dampen
            conflict_dampened = True

    mom_s = _momentum_component(rsi=rsi, macd_momentum=macd_momentum)
    loc_s = _location_component(
        close=close, support=support, resistance=resistance, atr=atr
    )
    impulse = (
        compute_impulse_score(closes, atr, config=config)
        if apply_impulse
        else ImpulseBreakdown(None, None, None, 0.0, atr)
    )
    impulse_s = impulse.impulse_score if apply_impulse else 0.0

    hint = trend_s + struct_s + mom_s + impulse_s
    vol_s = _volume_component(volume_state, hint)

    if apply_impulse:
        total = (
            config.weight_trend * trend_s
            + config.weight_structure * struct_s
            + config.weight_momentum * mom_s
            + config.weight_location * loc_s
            + config.weight_volume * vol_s
            + config.weight_impulse * impulse_s
        )
    else:
        # Higher TF: no impulse component — renormalize without impulse weight
        w_sum = (
            config.weight_trend
            + config.weight_structure
            + config.weight_momentum
            + config.weight_location
            + config.weight_volume
        )
        total = (
            config.weight_trend * trend_s
            + config.weight_structure * struct_s
            + config.weight_momentum * mom_s
            + config.weight_location * loc_s
            + config.weight_volume * vol_s
        ) / w_sum

    total = max(-100.0, min(100.0, total))

    if total >= config.tf_long_threshold:
        direction = "LONG"
    elif total <= config.tf_short_threshold:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    components = [trend_s, struct_s, mom_s, loc_s, vol_s]
    if apply_impulse:
        components.append(impulse_s)
    if direction == "NEUTRAL":
        confidence = max(0.0, 50.0 - abs(total))
    else:
        sign = 1.0 if direction == "LONG" else -1.0
        agreeing = sum(1 for c in components if c * sign > 0)
        confidence = min(100.0, agreeing / len(components) * 55.0 + abs(total) * 0.45)

    return ScoreBreakdownV2(
        trend_score=round(trend_s, 2),
        structure_score=round(struct_s, 2),
        structure_raw_binary=round(binary_struct, 2),
        structure_transition=transition,
        momentum_score=round(mom_s, 2),
        location_score=round(loc_s, 2),
        volume_score=round(vol_s, 2),
        impulse_score=round(impulse_s, 2),
        impulse=impulse,
        total_score=round(total, 2),
        confidence=round(confidence, 2),
        direction=direction,
        conflict_dampened=conflict_dampened,
    )


def audit_trend_structure_conflict_case() -> dict[str, float | bool]:
    """Document TREND=-100 vs STRUCTURE=+100 under v1 vs v2 dampening."""
    # v1: 0.30*(-100) + 0.25*(+100) = -30 + 25 = -5 (+ other components)
    v1_partial = 0.30 * (-100.0) + 0.25 * (100.0)
    # v2: structure dampened to +35; weights trend 0.25 structure 0.15
    v2_struct = 100.0 * DEFAULT_V2_CONFIG.structure_conflict_dampen
    v2_partial = (
        DEFAULT_V2_CONFIG.weight_trend * (-100.0)
        + DEFAULT_V2_CONFIG.weight_structure * v2_struct
    )
    return {
        "v1_trend_structure_contribution": v1_partial,
        "v2_trend_structure_contribution": v2_partial,
        "v2_structure_after_dampen": v2_struct,
        "structure_less_able_to_cancel_trend": abs(v2_partial) > abs(v1_partial)
        or (v1_partial > -10 and v2_partial < v1_partial),
    }
