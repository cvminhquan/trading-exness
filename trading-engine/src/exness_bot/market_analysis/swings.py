"""Confirmed swing detection — no look-ahead / no forming candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from exness_bot.domain.models import Candle


class SwingKind(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class ConfirmedSwing:
    kind: SwingKind
    index: int
    price: float
    timestamp: datetime
    """Bar open time of the swing candle (must already be closed)."""
    confirmed_at_index: int
    """First closed-bar index at which the swing becomes confirmed (= index + right)."""


def detect_confirmed_swings(
    candles: list[Candle],
    *,
    left: int = 2,
    right: int = 2,
) -> list[ConfirmedSwing]:
    """Detect pivots that are confirmed only after ``right`` CLOSED bars to the right.

    For index ``i``, a swing is confirmed when bars ``0..i+right`` exist in the
    closed-candle series (inclusive). The currently-forming candle must already
    be excluded by the caller.

    Swing High at ``i``:
        high[i] > high[j] for all j in [i-left, i) U (i, i+right]

    Swing Low at ``i``:
        low[i] < low[j] for all j in [i-left, i) U (i, i+right]
    """
    if left < 1 or right < 1:
        msg = "SWING_LEFT_BARS and SWING_RIGHT_BARS must be >= 1"
        raise ValueError(msg)
    n = len(candles)
    if n < left + right + 1:
        return []

    swings: list[ConfirmedSwing] = []
    # i can be a pivot only if i-left >= 0 and i+right <= n-1
    for i in range(left, n - right):
        hi = float(candles[i].high)
        lo = float(candles[i].low)
        left_slice = candles[i - left : i]
        right_slice = candles[i + 1 : i + right + 1]

        is_high = all(hi > float(c.high) for c in left_slice) and all(
            hi > float(c.high) for c in right_slice
        )
        is_low = all(lo < float(c.low) for c in left_slice) and all(
            lo < float(c.low) for c in right_slice
        )

        confirmed_at = i + right
        if is_high:
            swings.append(
                ConfirmedSwing(
                    kind=SwingKind.HIGH,
                    index=i,
                    price=hi,
                    timestamp=candles[i].timestamp,
                    confirmed_at_index=confirmed_at,
                )
            )
        if is_low:
            swings.append(
                ConfirmedSwing(
                    kind=SwingKind.LOW,
                    index=i,
                    price=lo,
                    timestamp=candles[i].timestamp,
                    confirmed_at_index=confirmed_at,
                )
            )

    swings.sort(key=lambda s: (s.index, 0 if s.kind == SwingKind.LOW else 1))
    return swings
