"""Context assessment vs structure / S-R — does not alter strategySignal."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from exness_bot.market_analysis.levels import (
    StructureLevel,
    nearest_resistance_above,
    nearest_support_below,
)
from exness_bot.market_analysis.models import AnalysisReason, AnalysisSignal, TradePlan
from exness_bot.market_analysis.signal import reason
from exness_bot.market_analysis.structure import StructureLabel, StructureSnapshot
from exness_bot.market_analysis.swings import ConfirmedSwing


class ContextAssessment(StrEnum):
    PASS = "PASS"
    CAUTION = "CAUTION"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class MarketStructureContext:
    classification: StructureLabel
    latest_swing_high: float | None
    latest_swing_low: float | None
    sequence: list[str]
    nearest_support: float | None
    nearest_resistance: float | None
    distance_to_support: float | None
    distance_to_resistance: float | None
    distance_to_support_atr: float | None
    distance_to_resistance_atr: float | None
    supports: list[StructureLevel] = field(default_factory=list)
    resistances: list[StructureLevel] = field(default_factory=list)
    swings: list[ConfirmedSwing] = field(default_factory=list)
    context_assessment: ContextAssessment = ContextAssessment.NOT_APPLICABLE
    context_reasons: list[AnalysisReason] = field(default_factory=list)


def assess_structure_context(
    *,
    strategy_signal: AnalysisSignal,
    trade: TradePlan | None,
    atr14: float | None,
    structure: StructureSnapshot,
    supports: list[StructureLevel],
    resistances: list[StructureLevel],
    swings: list[ConfirmedSwing],
    near_atr_threshold: float,
    caution_atr_threshold: float,
) -> MarketStructureContext:
    """Evaluate S/R proximity and TP/SL vs structure without changing signal."""
    ctx_reasons: list[AnalysisReason] = []
    assessment = ContextAssessment.NOT_APPLICABLE

    nearest_sup: StructureLevel | None = None
    nearest_res: StructureLevel | None = None
    dist_sup: float | None = None
    dist_res: float | None = None
    dist_sup_atr: float | None = None
    dist_res_atr: float | None = None

    if structure.classification == StructureLabel.UNDETERMINED or not structure.sequence:
        ctx_reasons.append(
            reason(
                "INSUFFICIENT_STRUCTURE_DATA",
                False,
                "Insufficient confirmed swings to classify market structure",
            )
        )
    elif structure.classification == StructureLabel.BULLISH:
        ctx_reasons.append(
            reason("STRUCTURE_BULLISH", True, "Bullish HH/HL structure")
        )
    elif structure.classification == StructureLabel.BEARISH:
        ctx_reasons.append(
            reason("STRUCTURE_BEARISH", True, "Bearish LH/LL structure")
        )
    elif structure.classification == StructureLabel.RANGE:
        ctx_reasons.append(
            reason("STRUCTURE_RANGE", True, "Range / mixed swing structure")
        )

    if strategy_signal == AnalysisSignal.WAIT or trade is None:
        return MarketStructureContext(
            classification=structure.classification,
            latest_swing_high=structure.latest_swing_high,
            latest_swing_low=structure.latest_swing_low,
            sequence=list(structure.sequence),
            nearest_support=None,
            nearest_resistance=None,
            distance_to_support=None,
            distance_to_resistance=None,
            distance_to_support_atr=None,
            distance_to_resistance_atr=None,
            supports=supports,
            resistances=resistances,
            swings=swings,
            context_assessment=ContextAssessment.NOT_APPLICABLE,
            context_reasons=ctx_reasons,
        )

    entry = trade.entry
    nearest_sup = nearest_support_below(supports, entry)
    nearest_res = nearest_resistance_above(resistances, entry)

    atr = atr14 if atr14 is not None and atr14 > 0 else None

    if nearest_sup is not None:
        dist_sup = entry - nearest_sup.price
        dist_sup_atr = dist_sup / atr if atr else None
        ctx_reasons.append(
            reason(
                "NEAR_SUPPORT",
                True,
                f"Support below entry at {nearest_sup.price:.5g}",
            )
        )
    if nearest_res is not None:
        dist_res = nearest_res.price - entry
        dist_res_atr = dist_res / atr if atr else None
        ctx_reasons.append(
            reason(
                "NEAR_RESISTANCE",
                True,
                f"Resistance above entry at {nearest_res.price:.5g}",
            )
        )

    assessment = ContextAssessment.PASS
    blocked = False
    caution = False

    if strategy_signal == AnalysisSignal.BUY:
        if dist_res_atr is not None and dist_res_atr <= near_atr_threshold:
            blocked = True
            ctx_reasons.append(
                reason(
                    "RESISTANCE_TOO_CLOSE",
                    False,
                    f"Nearest resistance is {dist_res_atr:.2f} ATR above entry",
                )
            )
        elif dist_res_atr is not None and dist_res_atr <= caution_atr_threshold:
            caution = True
            ctx_reasons.append(
                reason(
                    "NEAR_RESISTANCE",
                    False,
                    f"Resistance within {dist_res_atr:.2f} ATR of entry",
                )
            )

        if nearest_res is not None and trade.take_profit > nearest_res.price:
            # Strong = touch_count >= 2
            if nearest_res.touch_count >= 2 or nearest_res.strength >= 2:
                blocked = True
            else:
                caution = True
            ctx_reasons.append(
                reason(
                    "TP_CROSSES_RESISTANCE",
                    False,
                    (
                        f"Proposed TP {trade.take_profit:.5g} crosses resistance "
                        f"{nearest_res.price:.5g}"
                    ),
                )
            )

        if nearest_sup is not None:
            if trade.stop_loss > nearest_sup.price:
                ctx_reasons.append(
                    reason(
                        "SL_ABOVE_SUPPORT",
                        True,
                        "ATR SL is above nearest support (structure not protecting SL)",
                    )
                )
            else:
                ctx_reasons.append(
                    reason(
                        "SL_BELOW_SUPPORT",
                        True,
                        "ATR SL is below nearest support",
                    )
                )

    if strategy_signal == AnalysisSignal.SELL:
        if dist_sup_atr is not None and dist_sup_atr <= near_atr_threshold:
            blocked = True
            ctx_reasons.append(
                reason(
                    "SUPPORT_TOO_CLOSE",
                    False,
                    f"Nearest support is {dist_sup_atr:.2f} ATR below entry",
                )
            )
        elif dist_sup_atr is not None and dist_sup_atr <= caution_atr_threshold:
            caution = True
            ctx_reasons.append(
                reason(
                    "NEAR_SUPPORT",
                    False,
                    f"Support within {dist_sup_atr:.2f} ATR of entry",
                )
            )

        if nearest_sup is not None and trade.take_profit < nearest_sup.price:
            if nearest_sup.touch_count >= 2 or nearest_sup.strength >= 2:
                blocked = True
            else:
                caution = True
            ctx_reasons.append(
                reason(
                    "TP_CROSSES_SUPPORT",
                    False,
                    (
                        f"Proposed TP {trade.take_profit:.5g} crosses support "
                        f"{nearest_sup.price:.5g}"
                    ),
                )
            )

        if nearest_res is not None:
            if trade.stop_loss < nearest_res.price:
                ctx_reasons.append(
                    reason(
                        "SL_BELOW_RESISTANCE",
                        True,
                        "ATR SL is below nearest resistance (structure not protecting SL)",
                    )
                )
            else:
                ctx_reasons.append(
                    reason(
                        "SL_ABOVE_RESISTANCE",
                        True,
                        "ATR SL is above nearest resistance",
                    )
                )

    if blocked:
        assessment = ContextAssessment.BLOCKED
    elif caution:
        assessment = ContextAssessment.CAUTION

    return MarketStructureContext(
        classification=structure.classification,
        latest_swing_high=structure.latest_swing_high,
        latest_swing_low=structure.latest_swing_low,
        sequence=list(structure.sequence),
        nearest_support=None if nearest_sup is None else nearest_sup.price,
        nearest_resistance=None if nearest_res is None else nearest_res.price,
        distance_to_support=None if dist_sup is None else round(dist_sup, 6),
        distance_to_resistance=None if dist_res is None else round(dist_res, 6),
        distance_to_support_atr=(
            None if dist_sup_atr is None else round(dist_sup_atr, 6)
        ),
        distance_to_resistance_atr=(
            None if dist_res_atr is None else round(dist_res_atr, 6)
        ),
        supports=supports,
        resistances=resistances,
        swings=swings,
        context_assessment=assessment,
        context_reasons=ctx_reasons,
    )
