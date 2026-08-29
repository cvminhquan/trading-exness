"""Candle data quality validation for backtests."""

from __future__ import annotations

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_data.candles import timeframe_duration


def validate_candle_series(
    candles: list[Candle],
    timeframe: Timeframe,
    *,
    warmup_bars: int,
    strict_gaps: bool = True,
) -> None:
    """
    Validate loaded candles before running a backtest.

    Raises ValueError when data is unsafe to simulate.
    """
    if len(candles) <= warmup_bars:
        msg = f"Need more than {warmup_bars} candles, got {len(candles)}"
        raise ValueError(msg)

    seen: set[str] = set()
    previous_ts = None
    step = timeframe_duration(timeframe)

    for index, candle in enumerate(candles):
        key = candle.timestamp.isoformat()
        if key in seen:
            msg = f"Duplicate candle timestamp at index {index}: {key}"
            raise ValueError(msg)
        seen.add(key)

        if candle.high < candle.low:
            msg = f"Invalid OHLC at index {index}: high < low"
            raise ValueError(msg)
        if candle.high < max(candle.open, candle.close):
            msg = f"Invalid OHLC at index {index}: high below open/close"
            raise ValueError(msg)
        if candle.low > min(candle.open, candle.close):
            msg = f"Invalid OHLC at index {index}: low above open/close"
            raise ValueError(msg)

        if previous_ts is not None:
            delta = candle.timestamp - previous_ts
            if delta <= step * 0:
                msg = f"Non-increasing timestamp at index {index}"
                raise ValueError(msg)
            if strict_gaps and delta > step * 1.001:
                msg = (
                    f"Missing candle gap at index {index}: "
                    f"expected {step}, got {delta}"
                )
                raise ValueError(msg)

        previous_ts = candle.timestamp
