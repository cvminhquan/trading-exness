"""Generate deterministic backtest CSV fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path


def write_uptrend_csv(path: Path, *, bars: int = 260, start_price: float = 2300.0) -> Path:
    """Write ascending M15 OHLC CSV suitable for strategy warm-up."""
    start = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    lines = ["timestamp,open,high,low,close,volume"]
    price = start_price
    for i in range(bars):
        ts = start + timedelta(minutes=15 * i)
        open_price = price
        close_price = price + 0.5
        high_price = close_price + 2.0
        low_price = open_price - 1.0
        lines.append(
            f"{ts.isoformat()},{open_price},{high_price},{low_price},{close_price},100"
        )
        price = close_price

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
