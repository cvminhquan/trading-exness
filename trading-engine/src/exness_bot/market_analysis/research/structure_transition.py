"""Structure transition states for research scoring (no look-ahead).

States (soft scores):
  CONFIRMED_BULLISH   +100
  WEAKENING_BULLISH    +40
  TRANSITION             0
  WEAKENING_BEARISH    -40
  CONFIRMED_BEARISH   -100

Heuristic on closed bars + already-confirmed swing labels only:
- Confirmed: recent sequence dominated by HH/HL or LH/LL
- Weakening: confirmed bias but last label opposes (e.g. bullish book + LH/LL)
- Transition: mixed book or break of last swing in opposing direction
"""

from __future__ import annotations

from enum import StrEnum

from exness_bot.market_analysis.structure import StructureLabel, StructureSnapshot


class StructureTransition(StrEnum):
    CONFIRMED_BULLISH = "CONFIRMED_BULLISH"
    WEAKENING_BULLISH = "WEAKENING_BULLISH"
    TRANSITION = "TRANSITION"
    WEAKENING_BEARISH = "WEAKENING_BEARISH"
    CONFIRMED_BEARISH = "CONFIRMED_BEARISH"


_TRANSITION_SCORE: dict[StructureTransition, float] = {
    StructureTransition.CONFIRMED_BULLISH: 100.0,
    StructureTransition.WEAKENING_BULLISH: 40.0,
    StructureTransition.TRANSITION: 0.0,
    StructureTransition.WEAKENING_BEARISH: -40.0,
    StructureTransition.CONFIRMED_BEARISH: -100.0,
}


def transition_score(state: StructureTransition) -> float:
    return _TRANSITION_SCORE[state]


def classify_structure_transition(
    snapshot: StructureSnapshot,
    *,
    close: float | None,
) -> StructureTransition:
    """Map binary structure + recent sequence + optional swing break → transition."""
    seq = snapshot.sequence
    recent = seq[-4:] if len(seq) >= 4 else seq
    bull_marks = sum(1 for x in recent if x in {"HH", "HL"})
    bear_marks = sum(1 for x in recent if x in {"LH", "LL"})
    last = recent[-1] if recent else None

    base = snapshot.classification
    if base == StructureLabel.BULLISH:
        if last in {"LH", "LL"} or (
            close is not None
            and snapshot.latest_swing_low is not None
            and close < snapshot.latest_swing_low
        ):
            return StructureTransition.WEAKENING_BULLISH
        if bear_marks > 0 and bear_marks >= bull_marks:
            return StructureTransition.WEAKENING_BULLISH
        return StructureTransition.CONFIRMED_BULLISH

    if base == StructureLabel.BEARISH:
        if last in {"HH", "HL"} or (
            close is not None
            and snapshot.latest_swing_high is not None
            and close > snapshot.latest_swing_high
        ):
            return StructureTransition.WEAKENING_BEARISH
        if bull_marks > 0 and bull_marks >= bear_marks:
            return StructureTransition.WEAKENING_BEARISH
        return StructureTransition.CONFIRMED_BEARISH

    if base == StructureLabel.RANGE:
        return StructureTransition.TRANSITION

    # UNDETERMINED / mixed
    if bull_marks >= 2 and bear_marks == 0:
        return StructureTransition.WEAKENING_BULLISH
    if bear_marks >= 2 and bull_marks == 0:
        return StructureTransition.WEAKENING_BEARISH
    return StructureTransition.TRANSITION
