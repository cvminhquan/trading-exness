"""Closed-candle detection utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle

TIMEFRAME_DURATIONS: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}


def timeframe_duration(timeframe: Timeframe) -> timedelta:
    """Return candle duration for a timeframe."""
    if timeframe not in TIMEFRAME_DURATIONS:
        msg = f"Unsupported timeframe: {timeframe.value}"
        raise ValueError(msg)
    return TIMEFRAME_DURATIONS[timeframe]


def normalize_timestamp(value: object) -> datetime:
    """Normalize bar timestamps to timezone-aware UTC datetimes."""
    if isinstance(value, pd.Timestamp):
        ts = value.to_pydatetime()
    elif isinstance(value, datetime):
        ts = value
    else:
        msg = f"Unsupported timestamp type: {type(value)!r}"
        raise TypeError(msg)

    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def candle_close_time(open_time: datetime, timeframe: Timeframe) -> datetime:
    """Return when a candle becomes closed."""
    return normalize_timestamp(open_time) + timeframe_duration(timeframe)


def is_candle_closed(
    open_time: datetime,
    timeframe: Timeframe,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True when the candle period has finished."""
    reference = now or datetime.now(tz=UTC)
    return reference >= candle_close_time(open_time, timeframe)


def candles_to_dataframe(candles: list[Candle]) -> pd.DataFrame:
    """Convert domain candles to an ascending OHLCV DataFrame."""
    if not candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    rows = [
        {
            "timestamp": normalize_timestamp(c.timestamp),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]
    frame = pd.DataFrame(rows)
    return frame.sort_values("timestamp").reset_index(drop=True)


def get_latest_closed_candle(
    bars: pd.DataFrame,
    timeframe: Timeframe,
    *,
    now: datetime | None = None,
) -> pd.Series | None:
    """
    Return the latest fully closed candle row from OHLCV bars.

    Forming (incomplete) candles are excluded.
    """
    if bars.empty or "timestamp" not in bars.columns:
        return None

    reference = now or datetime.now(tz=UTC)
    timestamps = bars["timestamp"].map(normalize_timestamp)
    close_times = timestamps.map(lambda ts: candle_close_time(ts, timeframe))
    closed_mask = close_times <= reference
    closed_bars = bars.loc[closed_mask]
    if closed_bars.empty:
        return None
    return closed_bars.iloc[-1]


def bars_through_closed_candle(
    bars: pd.DataFrame,
    closed_candle: pd.Series,
) -> pd.DataFrame:
    """Return bars up to and including the given closed candle."""
    closed_ts = normalize_timestamp(closed_candle["timestamp"])
    timestamps = bars["timestamp"].map(normalize_timestamp)
    return bars.loc[timestamps <= closed_ts].reset_index(drop=True)
