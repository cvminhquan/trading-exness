"""Historical candle loading for backtests."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pandas as pd

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_data.candles import normalize_timestamp

REQUIRED_COLUMNS = {"open", "high", "low", "close"}
OPTIONAL_COLUMNS = {"volume", "spread", "timestamp", "time", "datetime"}


def load_candles_from_csv(
    path: str | Path,
    *,
    symbol: str,
    timeframe: Timeframe,
) -> list[Candle]:
    """
    Load OHLCV candles from CSV sorted oldest-first.

    Expected columns: timestamp (or time/datetime), open, high, low, close.
    Volume and spread are optional.
    """
    file_path = Path(path)
    if not file_path.exists():
        msg = f"Backtest data file not found: {file_path}"
        raise FileNotFoundError(msg)

    frame = pd.read_csv(file_path)
    normalized = _normalize_column_names(frame)
    missing = REQUIRED_COLUMNS - set(normalized.columns)
    if missing:
        msg = f"CSV missing required columns: {sorted(missing)}"
        raise ValueError(msg)

    timestamp_col = _resolve_timestamp_column(normalized)
    if timestamp_col in normalized.columns:
        normalized[timestamp_col] = pd.to_datetime(normalized[timestamp_col], utc=True)

    candles: list[Candle] = []
    for _, row in normalized.iterrows():
        ts = normalize_timestamp(row[timestamp_col])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        volume = _resolve_volume(row)
        spread_raw = row.get("spread")
        spread = int(spread_raw) if spread_raw is not None and pd.notna(spread_raw) else None

        candles.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=volume,
                spread=spread,
            )
        )

    candles.sort(key=lambda c: c.timestamp)
    return candles


def candles_to_backtest_frame(candles: list[Candle]) -> pd.DataFrame:
    """Convert candles to ascending OHLCV DataFrame."""
    if not candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    rows = [
        {
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles
    ]
    return pd.DataFrame(rows)


def _resolve_volume(row: pd.Series) -> float:
    """Resolve volume from volume, tick_volume, or real_volume columns."""
    for key in ("volume", "tick_volume", "real_volume"):
        if key in row.index:
            raw = row.get(key)
            if raw is not None and pd.notna(raw):
                return float(raw)
    return 0.0


def _normalize_column_names(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.copy()
    renamed.columns = [str(col).strip().lower() for col in renamed.columns]
    return renamed


def _resolve_timestamp_column(frame: pd.DataFrame) -> str:
    for candidate in ("timestamp", "time", "datetime", "date"):
        if candidate in frame.columns:
            return candidate
    msg = "CSV must include a timestamp column (timestamp, time, datetime, or date)"
    raise ValueError(msg)
