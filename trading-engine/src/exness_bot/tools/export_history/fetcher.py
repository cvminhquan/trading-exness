"""Fetch historical rates from MT5 (read-only)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import numpy.typing as npt
import structlog

from exness_bot.broker.mt5.client import MT5Client
from exness_bot.broker.mt5.mapper import timeframe_to_mt5
from exness_bot.domain.enums import Timeframe
from exness_bot.market_data.candles import timeframe_duration

logger = structlog.get_logger(__name__)

CHUNK_SIZE = 10_000


class EmptyHistoryError(ValueError):
    """Raised when MT5 returns no bars for the requested range."""


def fetch_historical_rates(
    client: MT5Client,
    *,
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> npt.NDArray[Any]:
    """Download OHLCV rates for a UTC date range without placing orders."""
    mt5_timeframe = timeframe_to_mt5(timeframe)
    date_from = _as_mt5_datetime(start)
    date_to = _as_mt5_datetime(end)

    rates = client.copy_rates_range(symbol, mt5_timeframe, date_from, date_to)
    if rates is not None and len(rates) > 0:
        return _trim_rates_to_range(rates, start, end)

    logger.info("copy_rates_range_empty_retry_chunked", symbol=symbol, start=start, end=end)
    rates = _fetch_chunked(client, symbol, mt5_timeframe, timeframe, start, end)
    if rates is None or len(rates) == 0:
        code, description = client.last_error()
        msg = (
            f"No historical data returned for {symbol} {timeframe.value} "
            f"between {start.isoformat()} and {end.isoformat()} "
            f"[{code}] {description}"
        )
        raise EmptyHistoryError(msg)
    return rates


def _fetch_chunked(
    client: MT5Client,
    symbol: str,
    mt5_timeframe: int,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> npt.NDArray[Any] | None:
    """Fallback chunked download using copy_rates_from."""
    step = timeframe_duration(timeframe)
    cursor = _as_mt5_datetime(start)
    end_naive = _as_mt5_datetime(end)
    chunks: list[npt.NDArray[Any]] = []

    while cursor <= end_naive:
        chunk = client.copy_rates_from(symbol, mt5_timeframe, cursor, CHUNK_SIZE)
        if chunk is None or len(chunk) == 0:
            break

        chunks.append(chunk)
        last_unix = int(chunk[-1]["time"])
        next_cursor = datetime.fromtimestamp(last_unix, tz=UTC) + step
        cursor = _as_mt5_datetime(next_cursor)
        if next_cursor > end:
            break

    if not chunks:
        return None

    merged = np.concatenate(chunks)
    return _trim_rates_to_range(merged, start, end)


def _trim_rates_to_range(
    rates: npt.NDArray[Any],
    start: datetime,
    end: datetime,
) -> npt.NDArray[Any]:
    """Keep only bars whose open time falls within [start, end] UTC."""
    if len(rates) == 0:
        return rates

    start_unix = int(start.timestamp())
    end_unix = int(end.timestamp())
    mask = (rates["time"] >= start_unix) & (rates["time"] <= end_unix)
    trimmed = rates[mask]
    if len(trimmed) == 0:
        return trimmed

    order = np.argsort(trimmed["time"])
    return trimmed[order]


def _as_mt5_datetime(value: datetime) -> datetime:
    """Convert aware UTC datetimes to naive UTC for MT5 API calls."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
