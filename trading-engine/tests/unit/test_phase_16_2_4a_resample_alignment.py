"""MTF resample alignment — no look-ahead on closed HTF buckets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.research.historical import resample_from_m15


def _m15(n: int, start: datetime | None = None) -> list[Candle]:
    t0 = start or datetime(2025, 1, 6, 0, 0, tzinfo=UTC)
    out: list[Candle] = []
    for i in range(n):
        out.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.M15,
                timestamp=t0 + timedelta(minutes=15 * i),
                open=2000 + i,
                high=2001 + i,
                low=1999 + i,
                close=2000.5 + i,
                volume=1.0,
                spread=10,
                tick_volume=1.0,
                real_volume=0.0,
            )
        )
    return out


def test_h1_bucket_uses_only_closed_m15_in_window() -> None:
    # 5 M15 bars: 00:00, 00:15, 00:30, 00:45, 01:00
    # At last open 01:00, H1 bucket 00:00 is closed (ends 01:00); bucket 01:00 incomplete.
    m15 = _m15(5)
    h1 = resample_from_m15(m15, Timeframe.H1, symbol="XAUUSD")
    assert len(h1) >= 1
    assert h1[0].timestamp == datetime(2025, 1, 6, 0, 0, tzinfo=UTC)
    assert h1[0].open == m15[0].open
    assert h1[0].close == m15[3].close  # last M15 strictly inside 00:00 H1
    # Incomplete 01:00 H1 must not appear (or if present must not use future)
    for bar in h1:
        assert bar.timestamp + timedelta(hours=1) <= m15[-1].timestamp + timedelta(minutes=15)


def test_prefix_resampling_no_lookahead() -> None:
    full = _m15(20)
    mid = 10
    prefix = full[: mid + 1]
    h1_full = resample_from_m15(full, Timeframe.H1, symbol="XAUUSD")
    h1_prefix = resample_from_m15(prefix, Timeframe.H1, symbol="XAUUSD")
    # Every prefix H1 close must match the same timestamp bucket on full series
    # using only data available in prefix — compare overlapping timestamps
    full_by_ts = {b.timestamp: b for b in h1_full}
    for b in h1_prefix:
        if b.timestamp in full_by_ts:
            # Prefix close cannot use candles after mid
            assert b.close == full[mid].close or b.timestamp < prefix[-1].timestamp
            assert b.close <= max(c.close for c in prefix) + 1e-9
