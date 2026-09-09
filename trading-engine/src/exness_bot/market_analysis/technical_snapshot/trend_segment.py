"""Deterministic trend-segment anchor from confirmed swings.

Algorithm (documented):
1. Require structure classification BULLISH or BEARISH (not RANGE/UNDETERMINED).
2. BEARISH: anchor = most recent confirmed SWING_HIGH at or before last bar;
   current price = last closed close; direction BEARISH.
3. BULLISH: anchor = most recent confirmed SWING_LOW; direction BULLISH.
4. Require anchor index < last bar index (leg must have progressed).
5. If no suitable confirmed pivot → unavailable INSUFFICIENT_CONFIRMED_STRUCTURE.

No future pivots: swings are already confirmation-gated (right bars).
No BOS/CHOCH invention.
"""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.domain.models import Candle
from exness_bot.market_analysis.structure import StructureLabel, StructureSnapshot
from exness_bot.market_analysis.swings import ConfirmedSwing, SwingKind
from exness_bot.market_analysis.technical_snapshot.models import TrendSegment
from exness_bot.market_analysis.trend import TrendLabel


@dataclass(frozen=True)
class TrendSegmentResult:
    segment: TrendSegment | None
    reason: str | None


def _map_trend_direction(trend: TrendLabel, structure: StructureLabel) -> str | None:
    if structure is StructureLabel.BULLISH:
        return "BULLISH"
    if structure is StructureLabel.BEARISH:
        return "BEARISH"
    if trend is TrendLabel.UPTREND:
        return "BULLISH"
    if trend is TrendLabel.DOWNTREND:
        return "BEARISH"
    return None


def derive_trend_segment(
    candles: list[Candle],
    *,
    swings: list[ConfirmedSwing],
    structure: StructureSnapshot,
    trend: TrendLabel,
    atr14: float | None,
) -> TrendSegmentResult:
    if len(candles) < 2:
        return TrendSegmentResult(None, "INSUFFICIENT_CONFIRMED_STRUCTURE")

    direction = _map_trend_direction(trend, structure.classification)
    if direction is None:
        return TrendSegmentResult(None, "INSUFFICIENT_CONFIRMED_STRUCTURE")

    last_i = len(candles) - 1
    last = candles[last_i]
    end_price = float(last.close)

    if direction == "BEARISH":
        highs = [s for s in swings if s.kind == SwingKind.HIGH and s.index < last_i]
        if not highs:
            return TrendSegmentResult(None, "INSUFFICIENT_CONFIRMED_STRUCTURE")
        anchor = highs[-1]
        anchor_name = "CONFIRMED_SWING_HIGH"
    else:
        lows = [s for s in swings if s.kind == SwingKind.LOW and s.index < last_i]
        if not lows:
            return TrendSegmentResult(None, "INSUFFICIENT_CONFIRMED_STRUCTURE")
        anchor = lows[-1]
        anchor_name = "CONFIRMED_SWING_LOW"

    start_price = float(anchor.price)
    absolute = end_price - start_price
    if direction == "BEARISH" and absolute > 0:
        # Structure says bearish but price above swing high — not a clean leg
        return TrendSegmentResult(None, "INSUFFICIENT_CONFIRMED_STRUCTURE")
    if direction == "BULLISH" and absolute < 0:
        return TrendSegmentResult(None, "INSUFFICIENT_CONFIRMED_STRUCTURE")

    pct = None
    if abs(start_price) > 1e-12:
        pct = round(100.0 * absolute / start_price, 6)
    move_atr = None
    if atr14 is not None and atr14 > 1e-12:
        move_atr = round(absolute / atr14, 6)

    return TrendSegmentResult(
        TrendSegment(
            start_timestamp=anchor.timestamp.isoformat(),
            start_price=round(start_price, 8),
            current_or_end_timestamp=last.timestamp.isoformat(),
            current_or_end_price=round(end_price, 8),
            direction=direction,
            absolute_move=round(absolute, 8),
            percentage_move=pct,
            move_atr=move_atr,
            bars=last_i - anchor.index,
            anchor=anchor_name,
        ),
        None,
    )
