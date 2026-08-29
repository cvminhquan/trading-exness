"""Historical dataset discovery and quality inspection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from exness_bot.backtest.loader import load_candles_from_csv
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_data.candles import normalize_timestamp, timeframe_duration

# Minimum candles for any baseline metrics (excluding warm-up context).
MIN_MEANINGFUL_CANDLES = 5_000
RECOMMENDED_CANDLES = 20_000


@dataclass(frozen=True)
class GapRecord:
    """Single missing M15 interval."""

    after_timestamp: datetime
    expected_next: datetime
    actual_next: datetime
    missing_bars: int


@dataclass(frozen=True)
class DatasetProfile:
    """Quality profile for a CSV candle file."""

    path: str
    symbol: str
    timeframe: Timeframe
    start_timestamp: datetime | None
    end_timestamp: datetime | None
    total_candles: int
    duplicate_timestamps: int
    missing_periods: int
    missing_bars_total: int
    timezone: str
    weekend_gaps: int
    session_gaps: int
    is_sorted: bool
    is_valid_ohlc: bool
    is_meaningful: bool
    gaps: tuple[GapRecord, ...]

    @property
    def duration_days(self) -> float:
        if self.start_timestamp is None or self.end_timestamp is None:
            return 0.0
        delta = self.end_timestamp - self.start_timestamp
        return delta.total_seconds() / 86_400


def discover_csv_datasets(search_roots: tuple[str, ...] = ("data",)) -> list[Path]:
    """Find CSV files under project data directories."""
    found: list[Path] = []
    for root in search_roots:
        base = Path(root)
        if not base.exists():
            continue
        found.extend(sorted(base.rglob("*.csv")))
    return found


def inspect_csv_dataset(
    path: str | Path,
    *,
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.M15,
) -> DatasetProfile:
    """Inspect a CSV without enforcing strict backtest validation."""
    file_path = Path(path)
    frame = pd.read_csv(file_path)
    frame.columns = [str(c).strip().lower() for c in frame.columns]

    timestamp_col = next(
        (c for c in ("timestamp", "time", "datetime", "date") if c in frame.columns),
        None,
    )
    if timestamp_col is None:
        return _empty_profile(str(file_path), symbol, timeframe)

    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], utc=True, errors="coerce")
    timestamps = frame[timestamp_col].dropna().tolist()
    if not timestamps:
        return _empty_profile(str(file_path), symbol, timeframe)

    normalized = [normalize_timestamp(ts) for ts in timestamps]
    if normalized[0].tzinfo is None:
        normalized = [ts.replace(tzinfo=UTC) for ts in normalized]

    duplicate_count = len(normalized) - len(set(ts.isoformat() for ts in normalized))
    sorted_ts = sorted(normalized)
    is_sorted = normalized == sorted_ts

    gaps: list[GapRecord] = []
    step = timeframe_duration(timeframe)
    missing_bars_total = 0
    weekend_gaps = 0
    session_gaps = 0

    for i in range(1, len(sorted_ts)):
        prev_ts = sorted_ts[i - 1]
        curr_ts = sorted_ts[i]
        delta = curr_ts - prev_ts
        if delta > step * 1.001:
            missing = round(delta / step) - 1
            missing_bars_total += max(missing, 0)
            gaps.append(
                GapRecord(
                    after_timestamp=prev_ts,
                    expected_next=prev_ts + step,
                    actual_next=curr_ts,
                    missing_bars=missing,
                )
            )
            if prev_ts.weekday() >= 4 or curr_ts.weekday() == 0:
                weekend_gaps += 1
            else:
                session_gaps += 1

    is_valid_ohlc = True
    for col in ("open", "high", "low", "close"):
        if col not in frame.columns:
            is_valid_ohlc = False
            break
    if is_valid_ohlc:
        for _, row in frame.iterrows():
            if row["high"] < row["low"]:
                is_valid_ohlc = False
                break

    total = len(sorted_ts)
    return DatasetProfile(
        path=str(file_path),
        symbol=symbol,
        timeframe=timeframe,
        start_timestamp=sorted_ts[0],
        end_timestamp=sorted_ts[-1],
        total_candles=total,
        duplicate_timestamps=duplicate_count,
        missing_periods=len(gaps),
        missing_bars_total=missing_bars_total,
        timezone="UTC",
        weekend_gaps=weekend_gaps,
        session_gaps=session_gaps,
        is_sorted=is_sorted,
        is_valid_ohlc=is_valid_ohlc,
        is_meaningful=total >= MIN_MEANINGFUL_CANDLES,
        gaps=tuple(gaps[:20]),
    )


def select_best_dataset(
    paths: list[Path],
    *,
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.M15,
) -> DatasetProfile | None:
    """Return the largest clean dataset profile, if any."""
    profiles = [inspect_csv_dataset(p, symbol=symbol, timeframe=timeframe) for p in paths]
    valid = [
        p
        for p in profiles
        if p.total_candles > 0 and p.duplicate_timestamps == 0 and p.is_valid_ohlc
    ]
    if not valid:
        return None
    return max(valid, key=lambda p: p.total_candles)


def load_validated_candles(path: str | Path, *, symbol: str, timeframe: Timeframe) -> list[Candle]:
    """Load candles for backtest after strict validation."""
    from exness_bot.backtest.validation import validate_candle_series

    candles = load_candles_from_csv(path, symbol=symbol, timeframe=timeframe)
    validate_candle_series(candles, timeframe, warmup_bars=200, strict_gaps=True)
    return candles


def _empty_profile(path: str, symbol: str, timeframe: Timeframe) -> DatasetProfile:
    return DatasetProfile(
        path=path,
        symbol=symbol,
        timeframe=timeframe,
        start_timestamp=None,
        end_timestamp=None,
        total_candles=0,
        duplicate_timestamps=0,
        missing_periods=0,
        missing_bars_total=0,
        timezone="UTC",
        weekend_gaps=0,
        session_gaps=0,
        is_sorted=True,
        is_valid_ohlc=False,
        is_meaningful=False,
        gaps=(),
    )
