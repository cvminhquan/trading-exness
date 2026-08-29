"""CSV serialization for exported MT5 history."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy.typing as npt

EXPORT_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "real_volume",
)


def rates_to_csv_lines(rates: npt.NDArray[Any]) -> list[str]:
    """Convert MT5 rates array to CSV lines (excluding header)."""
    if rates is None or len(rates) == 0:
        return []

    dtype_names = rates.dtype.names or ()
    lines: list[str] = []
    for row in rates:
        ts = datetime.fromtimestamp(int(row["time"]), tz=UTC).isoformat()
        tick_volume = int(row["tick_volume"]) if "tick_volume" in dtype_names else 0
        real_volume = int(row["real_volume"]) if "real_volume" in dtype_names else 0
        spread = int(row["spread"]) if "spread" in dtype_names else 0
        lines.append(
            f"{ts},{row['open']},{row['high']},{row['low']},{row['close']},"
            f"{tick_volume},{spread},{real_volume}"
        )
    return lines


def write_history_csv(path: Path, rates: npt.NDArray[Any]) -> None:
    """Write exported rates to CSV compatible with the backtest loader."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ",".join(EXPORT_COLUMNS)
    body = rates_to_csv_lines(rates)
    path.write_text(header + "\n" + "\n".join(body) + ("\n" if body else ""), encoding="utf-8")


def timestamp_from_rate_row(row: npt.NDArray[Any]) -> datetime:
    """Extract UTC timestamp from a single MT5 rate row."""
    return datetime.fromtimestamp(int(row["time"]), tz=UTC)
