"""Spread point math for analysis / eligibility — display & compare consistently."""

from __future__ import annotations

# Equality tolerance: spread <= max must pass when values are effectively equal.
SPREAD_COMPARE_EPS = 1e-6
# Stabilize binary float noise from ask/bid/point division.
SPREAD_NORMALIZE_DECIMALS = 9


def compute_raw_spread_points(*, bid: float, ask: float, point: float) -> float:
    """Raw (ask-bid)/point — no rounding."""
    if point <= 0:
        msg = "point must be positive to compute spread points"
        raise ValueError(msg)
    return abs(float(ask) - float(bid)) / float(point)


def normalize_spread_points(raw_spread_points: float) -> float:
    """Normalize for comparison / diagnostics (does not change MAX_SPREAD_POINTS)."""
    return round(float(raw_spread_points), SPREAD_NORMALIZE_DECIMALS)


def spread_exceeds_max(
    raw_spread_points: float,
    max_spread_points: int,
    *,
    eps: float = SPREAD_COMPARE_EPS,
) -> bool:
    """
    True only when spread is strictly above max.

    Semantic: spread <= max → allowed; spread > max → blocked.
    Uses normalized value + eps so float noise at equality does not block.
    """
    normalized = normalize_spread_points(raw_spread_points)
    return normalized > float(max_spread_points) + eps
