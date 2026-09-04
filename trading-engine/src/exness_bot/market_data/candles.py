"""Closed-candle detection utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from exness_bot.domain.clock import Clock
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
    clock: Clock | None = None,
) -> bool:
    """Return True when candle.timestamp + duration <= current_time (inclusive)."""
    if now is not None:
        reference = normalize_timestamp(now)
    elif clock is not None:
        reference = normalize_timestamp(clock.now_utc())
    else:
        reference = datetime.now(tz=UTC)
    return candle_close_time(open_time, timeframe) <= reference


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


def sort_candles_oldest_first(candles: list[Candle]) -> list[Candle]:
    """Normalize provider ordering: oldest timestamp first."""
    return sorted(candles, key=lambda item: normalize_timestamp(item.timestamp))


def dedupe_candles_by_timestamp(candles: list[Candle]) -> list[Candle]:
    """Keep the first occurrence of each timestamp (after sorting)."""
    seen: set[datetime] = set()
    unique: list[Candle] = []
    for candle in candles:
        stamp = normalize_timestamp(candle.timestamp)
        if stamp in seen:
            continue
        seen.add(stamp)
        unique.append(candle)
    return unique


def validate_live_candle(
    candle: Candle,
    *,
    symbol: str,
    timeframe: Timeframe,
) -> str | None:
    """Return an error code, or None when the candle is safe to emit."""
    try:
        stamp = normalize_timestamp(candle.timestamp)
    except (TypeError, ValueError):
        return "timestamp"
    if stamp.tzinfo is None:
        return "timestamp"
    if candle.symbol != symbol:
        return "symbol"
    if candle.timeframe != timeframe:
        return "timeframe"
    if candle.high < candle.low:
        return "ohlc"
    if candle.high < max(candle.open, candle.close):
        return "ohlc"
    if candle.low > min(candle.open, candle.close):
        return "ohlc"
    volume = candle.tick_volume if candle.tick_volume is not None else candle.volume
    if volume < 0:
        return "volume"
    if candle.real_volume is not None and candle.real_volume < 0:
        return "volume"
    return None


def closed_candles_only(
    candles: list[Candle],
    timeframe: Timeframe,
    *,
    now: datetime,
) -> list[Candle]:
    """Return closed candles only, oldest first. Forming bars are excluded."""
    ordered = dedupe_candles_by_timestamp(sort_candles_oldest_first(candles))
    return [
        candle
        for candle in ordered
        if is_candle_closed(candle.timestamp, timeframe, now=now)
    ]
