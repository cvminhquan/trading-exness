"""Generate MT5-like rate arrays for export tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np


def make_rates_array(
    *,
    start: datetime,
    bars: int,
    step_minutes: int = 15,
    start_price: float = 2300.0,
    spread: int = 20,
) -> np.ndarray:
    """Build a structured numpy array matching MT5 copy_rates output."""
    rows: list[tuple[int, float, float, float, float, int, int, int]] = []
    price = start_price
    ts = start.astimezone(UTC)
    for _ in range(bars):
        open_price = price
        close_price = price + 0.5
        high_price = close_price + 1.0
        low_price = open_price - 0.5
        rows.append(
            (
                int(ts.timestamp()),
                open_price,
                high_price,
                low_price,
                close_price,
                100,
                spread,
                0,
            )
        )
        price = close_price
        ts += timedelta(minutes=step_minutes)

    return np.array(
        rows,
        dtype=[
            ("time", "i8"),
            ("open", "f8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
            ("tick_volume", "i8"),
            ("spread", "i4"),
            ("real_volume", "i8"),
        ],
    )
