"""Conservative deterministic pattern tags (no vague chart patterns)."""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.market_analysis.structure import StructureLabel
from exness_bot.market_analysis.trend import TrendLabel


@dataclass(frozen=True)
class PatternSnapshot:
    type: str  # NONE or specific code
    confidence: float  # 0..100 evidence alignment for this tag
    evidence: list[str]


def detect_pattern(
    *,
    trend: TrendLabel,
    structure: StructureLabel,
    close: float | None,
    nearest_support: float | None,
    nearest_resistance: float | None,
    atr14: float | None,
    volume_state: str,
    prior_close: float | None,
) -> PatternSnapshot:
    """Return a single conservative pattern or NONE."""
    if close is None or atr14 is None or atr14 <= 0:
        return PatternSnapshot("NONE", 0.0, ["insufficient_price_or_atr"])

    evidence: list[str] = []

    # HH/HL continuation
    if structure == StructureLabel.BULLISH and trend == TrendLabel.UPTREND:
        evidence = ["structure_bullish", "trend_uptrend"]
        conf = 70.0
        if volume_state == "HIGH":
            evidence.append("volume_high")
            conf = 80.0
        return PatternSnapshot("HH_HL_CONTINUATION", conf, evidence)

    if structure == StructureLabel.BEARISH and trend == TrendLabel.DOWNTREND:
        evidence = ["structure_bearish", "trend_downtrend"]
        conf = 70.0
        if volume_state == "HIGH":
            evidence.append("volume_high")
            conf = 80.0
        return PatternSnapshot("LH_LL_CONTINUATION", conf, evidence)

    # Support rejection
    if (
        nearest_support is not None
        and close - nearest_support <= atr14 * 0.35
        and prior_close is not None
        and close > prior_close
    ):
        return PatternSnapshot(
            "SUPPORT_REJECTION",
            65.0,
            ["near_support", "close_rebounded"],
        )

    # Resistance rejection
    if (
        nearest_resistance is not None
        and nearest_resistance - close <= atr14 * 0.35
        and prior_close is not None
        and close < prior_close
    ):
        return PatternSnapshot(
            "RESISTANCE_REJECTION",
            65.0,
            ["near_resistance", "close_rejected"],
        )

    # Breakout / breakdown vs prior resistance/support with volume
    if (
        nearest_resistance is not None
        and prior_close is not None
        and prior_close <= nearest_resistance < close
        and volume_state == "HIGH"
    ):
        return PatternSnapshot(
            "BULLISH_BREAKOUT",
            75.0,
            ["close_above_resistance", "volume_high"],
        )

    if (
        nearest_support is not None
        and prior_close is not None
        and prior_close >= nearest_support > close
        and volume_state == "HIGH"
    ):
        return PatternSnapshot(
            "BEARISH_BREAKDOWN",
            75.0,
            ["close_below_support", "volume_high"],
        )

    return PatternSnapshot("NONE", 0.0, ["no_deterministic_pattern"])
