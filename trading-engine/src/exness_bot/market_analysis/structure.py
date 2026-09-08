"""HH/HL/LH/LL and market structure classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from exness_bot.market_analysis.swings import ConfirmedSwing, SwingKind


class StructureLabel(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGE = "RANGE"
    UNDETERMINED = "UNDETERMINED"


class SwingLabel(StrEnum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"


@dataclass(frozen=True)
class LabeledSwing:
    swing: ConfirmedSwing
    label: SwingLabel | None


@dataclass(frozen=True)
class StructureSnapshot:
    classification: StructureLabel
    sequence: list[str]
    labeled: list[LabeledSwing]
    latest_swing_high: float | None
    latest_swing_low: float | None


def label_swings(swings: list[ConfirmedSwing]) -> list[LabeledSwing]:
    """Label successive highs/lows relative to the previous same-kind swing."""
    labeled: list[LabeledSwing] = []
    prev_high: float | None = None
    prev_low: float | None = None
    for swing in swings:
        label: SwingLabel | None = None
        if swing.kind == SwingKind.HIGH:
            if prev_high is not None:
                label = SwingLabel.HH if swing.price > prev_high else SwingLabel.LH
            prev_high = swing.price
        else:
            if prev_low is not None:
                label = SwingLabel.HL if swing.price > prev_low else SwingLabel.LL
            prev_low = swing.price
        labeled.append(LabeledSwing(swing=swing, label=label))
    return labeled


def classify_structure(labeled: list[LabeledSwing]) -> StructureSnapshot:
    """Classify from recent HH/HL vs LH/LL pairs. Insufficient → UNDETERMINED."""
    highs = [item for item in labeled if item.swing.kind == SwingKind.HIGH]
    lows = [item for item in labeled if item.swing.kind == SwingKind.LOW]
    latest_high = highs[-1].swing.price if highs else None
    latest_low = lows[-1].swing.price if lows else None

    sequence = [item.label.value for item in labeled if item.label is not None]
    if len(sequence) < 2:
        return StructureSnapshot(
            classification=StructureLabel.UNDETERMINED,
            sequence=sequence,
            labeled=labeled,
            latest_swing_high=latest_high,
            latest_swing_low=latest_low,
        )

    # Use the last two comparable labels among recent swings
    recent = sequence[-4:] if len(sequence) >= 4 else sequence
    has_hh = "HH" in recent
    has_hl = "HL" in recent
    has_lh = "LH" in recent
    has_ll = "LL" in recent

    bullish = has_hh and has_hl and not (has_lh and has_ll)
    bearish = has_lh and has_ll and not (has_hh and has_hl)

    # Prefer last two labeled swings if they form a clear pair
    last_two = sequence[-2:]
    if set(last_two) == {"HH", "HL"} or last_two == ["HH", "HL"] or last_two == ["HL", "HH"]:
        bullish = True
        bearish = False
    elif set(last_two) == {"LH", "LL"} or last_two == ["LH", "LL"] or last_two == ["LL", "LH"]:
        bearish = True
        bullish = False

    if bullish and not bearish:
        classification = StructureLabel.BULLISH
    elif bearish and not bullish:
        classification = StructureLabel.BEARISH
    elif has_hh or has_hl or has_lh or has_ll:
        classification = StructureLabel.RANGE
    else:
        classification = StructureLabel.UNDETERMINED

    return StructureSnapshot(
        classification=classification,
        sequence=sequence,
        labeled=labeled,
        latest_swing_high=latest_high,
        latest_swing_low=latest_low,
    )
