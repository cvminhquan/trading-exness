"""Tests for closed-candle detection."""

from datetime import UTC, datetime, timedelta

import pandas as pd

from exness_bot.domain.enums import Timeframe
from exness_bot.market_data.candles import (
    bars_through_closed_candle,
    get_latest_closed_candle,
    is_candle_closed,
)


def _make_m15_bars(count: int, *, start: datetime | None = None) -> pd.DataFrame:
    start = start or datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    timestamps = [start + timedelta(minutes=15 * i) for i in range(count)]
    closes = [2350.0 + i * 0.1 for i in range(count)]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [100.0] * count,
        }
    )


class TestClosedCandleDetection:
    def test_is_candle_closed_after_period(self) -> None:
        open_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        now = datetime(2026, 1, 1, 10, 15, tzinfo=UTC)
        assert is_candle_closed(open_time, Timeframe.M15, now=now) is True

    def test_is_candle_open_before_period_end(self) -> None:
        open_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        now = datetime(2026, 1, 1, 10, 14, tzinfo=UTC)
        assert is_candle_closed(open_time, Timeframe.M15, now=now) is False

    def test_get_latest_closed_candle_excludes_forming_bar(self) -> None:
        bars = _make_m15_bars(3, start=datetime(2026, 1, 1, 10, 0, tzinfo=UTC))
        now = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
        closed = get_latest_closed_candle(bars, Timeframe.M15, now=now)
        assert closed is not None
        assert closed["timestamp"] == datetime(2026, 1, 1, 10, 15, tzinfo=UTC)

    def test_bars_through_closed_candle(self) -> None:
        bars = _make_m15_bars(5)
        closed = bars.iloc[2]
        trimmed = bars_through_closed_candle(bars, closed)
        assert len(trimmed) == 3
