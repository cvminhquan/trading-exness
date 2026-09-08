"""Historical M15 load, deterministic resample, validation, chronological split."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.backtest.loader import load_candles_from_csv
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle

# Candle open timestamps are treated as UTC (exporter / loader normalize to UTC).
# Resample buckets use UTC floor to period start; only fully closed buckets kept
# relative to the last M15 open (exclude incomplete final HTF bar).
TIMEZONE_NOTE = "UTC (timestamps normalized by load_candles_from_csv)"


@dataclass(frozen=True)
class DatasetReport:
    broker_symbol: str
    path: str
    timezone: str
    start: datetime | None
    end: datetime | None
    m15_count: int
    h1_count: int
    h4_count: int
    d1_count: int
    gap_count: int
    duplicate_count: int
    sufficient_for_split: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ChronoSplit:
    development: list[Candle]
    validation: list[Candle]
    holdout: list[Candle]


def _period_delta(tf: Timeframe) -> timedelta:
    if tf == Timeframe.H1:
        return timedelta(hours=1)
    if tf == Timeframe.H4:
        return timedelta(hours=4)
    if tf == Timeframe.D1:
        return timedelta(days=1)
    msg = f"Unsupported resample target: {tf}"
    raise ValueError(msg)


def _floor_timestamp(ts: datetime, tf: Timeframe) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    ts = ts.astimezone(UTC)
    if tf == Timeframe.H1:
        return ts.replace(minute=0, second=0, microsecond=0)
    if tf == Timeframe.H4:
        hour = (ts.hour // 4) * 4
        return ts.replace(hour=hour, minute=0, second=0, microsecond=0)
    if tf == Timeframe.D1:
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    msg = f"Unsupported floor target: {tf}"
    raise ValueError(msg)


def resample_from_m15(
    m15: list[Candle],
    target: Timeframe,
    *,
    symbol: str,
) -> list[Candle]:
    """Deterministic OHLCV resample from M15 opens (UTC). Closed buckets only."""
    if target == Timeframe.M15:
        return list(m15)
    if not m15:
        return []

    buckets: dict[datetime, list[Candle]] = {}
    for c in m15:
        key = _floor_timestamp(c.timestamp, target)
        buckets.setdefault(key, []).append(c)

    period = _period_delta(target)
    last_m15 = m15[-1].timestamp
    if last_m15.tzinfo is None:
        last_m15 = last_m15.replace(tzinfo=UTC)

    out: list[Candle] = []
    for key in sorted(buckets):
        # Bucket is closed only if next period start <= last_m15 + M15 step? 
        # Conservative: require bucket_end <= last_m15 (last M15 open still in bucket
        # means incomplete for HTF ending after that open+15m). 
        bucket_end = key + period
        # Incomplete if last M15 open is still before bucket_end - 15m? Simpler:
        # drop bucket if max candle timestamp in bucket is the global last AND
        # now would still be inside bucket — for historical CSV all bars closed,
        # keep all full-length buckets that contain expected number of M15s is hard
        # (weekends). Keep bucket if bucket_end <= last_m15 + 15m.
        if bucket_end > last_m15 + timedelta(minutes=15):
            continue
        group = buckets[key]
        out.append(
            Candle(
                symbol=symbol,
                timeframe=target,
                timestamp=key,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(float(c.volume or 0.0) for c in group),
                spread=group[-1].spread,
                tick_volume=sum(float(c.tick_volume or c.volume or 0.0) for c in group),
                real_volume=0.0,
            )
        )
    return out


def count_m15_gaps(m15: list[Candle]) -> tuple[int, int]:
    """Return (gap_count, duplicate_count) for 15m steps (skip weekend >3d)."""
    if len(m15) < 2:
        return 0, 0
    gaps = 0
    dupes = 0
    for a, b in itertools.pairwise(m15):
        delta = b.timestamp - a.timestamp
        if delta == timedelta(0) or delta < timedelta(minutes=15):
            dupes += 1
        elif delta > timedelta(minutes=15) and delta < timedelta(days=3):
            # session gap / missing bars
            steps = int(delta / timedelta(minutes=15)) - 1
            gaps += max(0, steps)
    return gaps, dupes


def chronological_split(m15: list[Candle]) -> ChronoSplit:
    n = len(m15)
    i_dev = int(n * 0.60)
    i_val = int(n * 0.80)
    return ChronoSplit(
        development=m15[:i_dev],
        validation=m15[i_dev:i_val],
        holdout=m15[i_val:],
    )


def validate_dataset(
    m15: list[Candle],
    *,
    path: str | Path,
    broker_symbol: str,
    min_m15_for_split: int = 5_000,
) -> tuple[DatasetReport, dict[str, list[Candle]]]:
    symbol = broker_symbol
    h1 = resample_from_m15(m15, Timeframe.H1, symbol=symbol)
    h4 = resample_from_m15(m15, Timeframe.H4, symbol=symbol)
    d1 = resample_from_m15(m15, Timeframe.D1, symbol=symbol)
    gaps, dupes = count_m15_gaps(m15)
    sufficient = len(m15) >= min_m15_for_split
    notes: list[str] = []
    if not sufficient:
        notes.append(
            f"M15 count {len(m15)} < {min_m15_for_split}; "
            "holdout claim limited to PROMISING_V2_REQUIRES_MORE_DATA ceiling"
        )
    report = DatasetReport(
        broker_symbol=broker_symbol,
        path=str(path),
        timezone=TIMEZONE_NOTE,
        start=m15[0].timestamp if m15 else None,
        end=m15[-1].timestamp if m15 else None,
        m15_count=len(m15),
        h1_count=len(h1),
        h4_count=len(h4),
        d1_count=len(d1),
        gap_count=gaps,
        duplicate_count=dupes,
        sufficient_for_split=sufficient,
        notes=tuple(notes),
    )
    frames = {"M15": m15, "H1": h1, "H4": h4, "D1": d1}
    return report, frames


def load_m15_csv(path: str | Path, *, symbol: str = "XAUUSD") -> list[Candle]:
    return load_candles_from_csv(path, symbol=symbol, timeframe=Timeframe.M15)


def discover_default_m15_path() -> Path | None:
    # historical.py → research → market_analysis → exness_bot → src → trading-engine
    engine_root = Path(__file__).resolve().parents[4]
    root = engine_root / "data" / "historical"
    if not root.exists():
        return None
    candidates = sorted(root.glob("*M15*.csv")) + sorted(root.glob("*_m15.csv"))
    return candidates[0] if candidates else None
