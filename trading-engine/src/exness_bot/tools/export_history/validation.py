"""Post-export validation for historical CSV data."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean
from typing import Any

import numpy.typing as npt

from exness_bot.domain.enums import Timeframe
from exness_bot.market_data.candles import normalize_timestamp, timeframe_duration
from exness_bot.tools.export_history.models import (
    ClassifiedGap,
    ExportValidationReport,
    GapKind,
    SpreadStatistics,
)
from exness_bot.tools.export_history.serializer import timestamp_from_rate_row


def validate_exported_rates(
    rates: npt.NDArray[Any],
    *,
    timeframe: Timeframe,
) -> ExportValidationReport:
    """Analyze exported rates for gaps, duplicates, OHLC validity, and spread stats."""
    if rates is None or len(rates) == 0:
        return ExportValidationReport(
            candle_count=0,
            first_timestamp=None,
            last_timestamp=None,
            duplicate_count=0,
            normal_session_gaps=0,
            unexpected_gaps=0,
            missing_bars_total=0,
            ohlc_valid=False,
            timezone="UTC",
            spread=None,
        )

    timestamps = [timestamp_from_rate_row(row) for row in rates]
    duplicate_count = len(timestamps) - len({ts.isoformat() for ts in timestamps})
    sorted_pairs = sorted(zip(timestamps, rates, strict=True), key=lambda item: item[0])

    step = timeframe_duration(timeframe)
    gaps: list[ClassifiedGap] = []
    normal_gaps = 0
    unexpected_gaps = 0
    missing_bars_total = 0

    for index in range(1, len(sorted_pairs)):
        prev_ts, _ = sorted_pairs[index - 1]
        curr_ts, _ = sorted_pairs[index]
        delta = curr_ts - prev_ts
        if delta <= step * 1.001:
            continue

        missing = round(delta / step) - 1
        missing = max(missing, 0)
        missing_bars_total += missing
        kind = classify_gap(prev_ts, curr_ts, delta)
        if kind == GapKind.NORMAL_SESSION:
            normal_gaps += 1
        else:
            unexpected_gaps += 1
        gaps.append(
            ClassifiedGap(
                after_timestamp=prev_ts,
                expected_next=prev_ts + step,
                actual_next=curr_ts,
                missing_bars=missing,
                kind=kind,
            )
        )

    ohlc_valid = _validate_ohlc([row for _, row in sorted_pairs])
    spread_stats = _spread_statistics(rates)

    return ExportValidationReport(
        candle_count=len(sorted_pairs),
        first_timestamp=sorted_pairs[0][0],
        last_timestamp=sorted_pairs[-1][0],
        duplicate_count=duplicate_count,
        normal_session_gaps=normal_gaps,
        unexpected_gaps=unexpected_gaps,
        missing_bars_total=missing_bars_total,
        ohlc_valid=ohlc_valid,
        timezone="UTC",
        spread=spread_stats,
        gaps=gaps[:50],
    )


def classify_gap(prev_ts: datetime, curr_ts: datetime, delta: timedelta) -> GapKind:
    """Distinguish expected market-closed gaps from unexpected missing data."""
    prev_ts = normalize_timestamp(prev_ts)
    curr_ts = normalize_timestamp(curr_ts)

    if prev_ts.weekday() >= 4 or curr_ts.weekday() == 0:
        return GapKind.NORMAL_SESSION

    if delta <= timedelta(hours=4):
        return GapKind.NORMAL_SESSION

    return GapKind.UNEXPECTED


def _validate_ohlc(rows: list[npt.NDArray[Any]]) -> bool:
    for row in rows:
        high = float(row["high"])
        low = float(row["low"])
        open_price = float(row["open"])
        close = float(row["close"])
        if high < low:
            return False
        if open_price < low or open_price > high:
            return False
        if close < low or close > high:
            return False
    return True


def _spread_statistics(rates: npt.NDArray[Any]) -> SpreadStatistics | None:
    dtype_names = rates.dtype.names or ()
    if "spread" not in dtype_names:
        return None

    values = [int(row["spread"]) for row in rates]
    if not values:
        return None

    return SpreadStatistics(
        minimum=min(values),
        maximum=max(values),
        average=round(mean(values), 2),
        samples=len(values),
    )
