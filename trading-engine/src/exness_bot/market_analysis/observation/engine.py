"""Closed-candle measurement helpers for forward observation.

AMBIGUOUS khi cùng một closed candle chạm cả TP1 và SL — không giả định thứ tự.
TP1/SL race chỉ bắt đầu sau khi Entry Zone đã được chạm.
EXPIRED_NO_ENTRY chỉ khi có đủ closed-candle coverage toàn lifetime.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.observation.models import (
    CHECKPOINT_OFFSETS_MINUTES,
    CheckpointObservation,
    CheckpointStatus,
    FirstOutcome,
    SetupObservationRecord,
)
from exness_bot.market_data.candles import (
    candle_close_time,
    is_candle_closed,
    normalize_timestamp,
    timeframe_duration,
)

_TERMINAL_OUTCOMES = frozenset(
    {
        FirstOutcome.TP1_FIRST,
        FirstOutcome.SL_FIRST,
        FirstOutcome.AMBIGUOUS,
        FirstOutcome.EXPIRED_NO_ENTRY,
    }
)


def risk_distance(*, entry_price: float, stop_loss: float) -> float | None:
    dist = abs(entry_price - stop_loss)
    if dist <= 0:
        return None
    return dist


def entry_zone_intersects_candle(
    *,
    direction: str,
    zone_low: float,
    zone_high: float,
    high: float,
    low: float,
) -> bool:
    """True khi OHLC range giao với Entry Zone (không phụ thuộc direction cho overlap)."""
    _ = direction
    return low <= zone_high and high >= zone_low


def candle_touches_price(*, high: float, low: float, price: float) -> bool:
    return low <= price <= high


def expected_lifetime_open_timestamps(
    *,
    source_candle_timestamp: datetime,
    expires_at: datetime,
    timeframe: Timeframe,
) -> tuple[datetime, ...]:
    """Các open-timestamp closed candle cần có để cover [source, expires)."""
    source = normalize_timestamp(source_candle_timestamp)
    expires = normalize_timestamp(expires_at)
    step = timeframe_duration(timeframe)
    expected: list[datetime] = []
    ts = source + step
    while ts < expires:
        expected.append(ts)
        ts = ts + step
    return tuple(expected)


def has_full_lifetime_coverage(
    *,
    source_candle_timestamp: datetime,
    expires_at: datetime,
    timeframe: Timeframe,
    observed_open_timestamps: tuple[datetime, ...] | set[datetime],
) -> bool:
    """True chỉ khi mọi M15 open trong lifetime đều đã được quan sát."""
    expected = expected_lifetime_open_timestamps(
        source_candle_timestamp=source_candle_timestamp,
        expires_at=expires_at,
        timeframe=timeframe,
    )
    if not expected:
        return True
    observed = {normalize_timestamp(ts) for ts in observed_open_timestamps}
    return all(ts in observed for ts in expected)


def update_mfe_mae(
    record: SetupObservationRecord,
    *,
    high: float,
    low: float,
    candle_ts: datetime,
) -> SetupObservationRecord:
    """Cập nhật MFE/MAE direction-aware theo entry_price tham chiếu."""
    entry = record.entry_price
    if record.direction.upper() == "LONG":
        fav = high - entry
        adv = entry - low
    else:
        fav = entry - low
        adv = high - entry

    mfe_price = record.mfe_price
    mae_price = record.mae_price
    mfe_at = record.mfe_extreme_at
    mae_at = record.mae_extreme_at

    if fav > mfe_price:
        mfe_price = fav
        mfe_at = candle_ts
    if adv > mae_price:
        mae_price = adv
        mae_at = candle_ts

    mfe_r: float | None = None
    mae_r: float | None = None
    if record.risk_distance is not None and record.risk_distance > 0:
        mfe_r = round(mfe_price / record.risk_distance, 6)
        mae_r = round(mae_price / record.risk_distance, 6)

    return replace(
        record,
        mfe_price=round(mfe_price, 6),
        mae_price=round(mae_price, 6),
        mfe_r=mfe_r,
        mae_r=mae_r,
        mfe_extreme_at=mfe_at,
        mae_extreme_at=mae_at,
    )


def initial_checkpoints(*, created_at: datetime) -> tuple[CheckpointObservation, ...]:
    created = normalize_timestamp(created_at)
    return tuple(
        CheckpointObservation(
            label=label,
            due_at=created + timedelta(minutes=minutes),
            status=CheckpointStatus.PENDING,
        )
        for label, minutes in CHECKPOINT_OFFSETS_MINUTES
    )


def _finalize_checkpoints(
    record: SetupObservationRecord,
    *,
    candles: list[Candle],
    timeframe: Timeframe,
    now: datetime,
) -> tuple[CheckpointObservation, ...]:
    """Finalize checkpoint khi đã có closed candle đủ horizon; thiếu data → giữ PENDING."""
    updated: list[CheckpointObservation] = []
    for cp in record.checkpoints:
        if cp.status == CheckpointStatus.FINALIZED:
            updated.append(cp)
            continue

        if now < cp.due_at:
            updated.append(cp)
            continue

        eligible = [
            c
            for c in candles
            if is_candle_closed(c.timestamp, timeframe, now=now)
            and candle_close_time(c.timestamp, timeframe) >= cp.due_at
        ]
        if not eligible:
            updated.append(cp)
            continue

        candle = min(eligible, key=lambda c: normalize_timestamp(c.timestamp))
        updated.append(
            CheckpointObservation(
                label=cp.label,
                due_at=cp.due_at,
                status=CheckpointStatus.FINALIZED,
                candle_timestamp=normalize_timestamp(candle.timestamp),
                open=float(candle.open),
                high=float(candle.high),
                low=float(candle.low),
                close=float(candle.close),
            )
        )
    return tuple(updated)


def _merge_observed_timestamps(
    existing: tuple[datetime, ...],
    *,
    candles: list[Candle],
    source_ts: datetime,
    expires_at: datetime,
    timeframe: Timeframe,
    now: datetime,
) -> tuple[datetime, ...]:
    stamps = {normalize_timestamp(ts) for ts in existing}
    for candle in candles:
        ts = normalize_timestamp(candle.timestamp)
        if not (source_ts < ts < expires_at):
            continue
        if not is_candle_closed(candle.timestamp, timeframe, now=now):
            continue
        stamps.add(ts)
    return tuple(sorted(stamps))


def _apply_tp1_sl_race(
    current: SetupObservationRecord,
    *,
    high: float,
    low: float,
    ts: datetime,
) -> SetupObservationRecord:
    """Resolve TP1/SL chỉ khi entry đã chạm; same-candle both => AMBIGUOUS."""
    if current.first_outcome in {
        FirstOutcome.TP1_FIRST,
        FirstOutcome.SL_FIRST,
        FirstOutcome.AMBIGUOUS,
        FirstOutcome.EXPIRED_NO_ENTRY,
    }:
        return current

    tp1 = current.tp1_price
    hit_tp1 = tp1 is not None and candle_touches_price(high=high, low=low, price=tp1)
    hit_sl = candle_touches_price(high=high, low=low, price=current.stop_loss)
    if hit_tp1 and hit_sl:
        return replace(
            current,
            tp1_touched_at=ts,
            sl_touched_at=ts,
            first_outcome=FirstOutcome.AMBIGUOUS,
            notes=(*current.notes, "SAME_CANDLE_TP1_AND_SL"),
        )
    if hit_tp1:
        return replace(
            current,
            tp1_touched_at=ts,
            first_outcome=FirstOutcome.TP1_FIRST,
        )
    if hit_sl:
        return replace(
            current,
            sl_touched_at=ts,
            first_outcome=FirstOutcome.SL_FIRST,
        )
    return current


def process_closed_candles(
    record: SetupObservationRecord,
    *,
    candles: list[Candle],
    now: datetime,
    timeframe: Timeframe | None = None,
    terminal_lifecycle_state: str | None = None,
) -> SetupObservationRecord:
    """Ingest closed candles theo thứ tự thời gian; không dùng forming candle."""
    tf = timeframe or Timeframe(record.primary_timeframe)
    now_ts = normalize_timestamp(now)
    source_ts = normalize_timestamp(record.source_candle_timestamp)
    expires_at = normalize_timestamp(record.expires_at)

    observed = _merge_observed_timestamps(
        record.observed_open_timestamps,
        candles=candles,
        source_ts=source_ts,
        expires_at=expires_at,
        timeframe=tf,
        now=now_ts,
    )

    closed = [
        c
        for c in candles
        if is_candle_closed(c.timestamp, tf, now=now_ts)
        and normalize_timestamp(c.timestamp) > source_ts
    ]
    closed.sort(key=lambda c: normalize_timestamp(c.timestamp))

    if record.last_processed_candle_ts is not None:
        cursor = normalize_timestamp(record.last_processed_candle_ts)
        closed = [c for c in closed if normalize_timestamp(c.timestamp) > cursor]

    current = record
    if terminal_lifecycle_state is not None:
        current = replace(current, terminal_lifecycle_state=terminal_lifecycle_state)

    last_ts = record.last_processed_candle_ts

    for candle in closed:
        ts = normalize_timestamp(candle.timestamp)
        if ts >= expires_at:
            break

        high = float(candle.high)
        low = float(candle.low)
        current = update_mfe_mae(current, high=high, low=low, candle_ts=ts)

        if not current.entry_touched and entry_zone_intersects_candle(
            direction=current.direction,
            zone_low=current.entry_zone_low,
            zone_high=current.entry_zone_high,
            high=high,
            low=low,
        ):
            outcome = (
                FirstOutcome.ENTRY_TOUCHED
                if current.first_outcome == FirstOutcome.OPEN
                else current.first_outcome
            )
            current = replace(
                current,
                entry_touched=True,
                first_entry_touch_at=ts,
                first_outcome=outcome,
            )

        # TP1/SL race chỉ sau khi Entry Zone đã chạm (cùng candle entry vẫn được)
        if current.entry_touched:
            current = _apply_tp1_sl_race(current, high=high, low=low, ts=ts)

        last_ts = ts

    coverage_ok = has_full_lifetime_coverage(
        source_candle_timestamp=source_ts,
        expires_at=expires_at,
        timeframe=tf,
        observed_open_timestamps=observed,
    )

    if now_ts >= expires_at and not current.entry_touched:
        if current.first_outcome in {FirstOutcome.OPEN, FirstOutcome.UNRESOLVED}:
            if coverage_ok:
                current = replace(current, first_outcome=FirstOutcome.EXPIRED_NO_ENTRY)
            else:
                notes = current.notes
                if "INCOMPLETE_LIFETIME_COVERAGE" not in notes:
                    notes = (*notes, "INCOMPLETE_LIFETIME_COVERAGE")
                current = replace(
                    current,
                    first_outcome=FirstOutcome.UNRESOLVED,
                    notes=notes,
                )
    elif (
        now_ts >= expires_at
        and current.entry_touched
        and current.first_outcome
        in {FirstOutcome.OPEN, FirstOutcome.ENTRY_TOUCHED, FirstOutcome.UNRESOLVED}
    ):
        current = replace(current, first_outcome=FirstOutcome.UNRESOLVED)

    all_closed_for_cp = [
        c
        for c in candles
        if is_candle_closed(c.timestamp, tf, now=now_ts)
        and normalize_timestamp(c.timestamp) > source_ts
    ]
    checkpoints = _finalize_checkpoints(
        current, candles=all_closed_for_cp, timeframe=tf, now=now_ts
    )

    return replace(
        current,
        checkpoints=checkpoints,
        last_processed_candle_ts=last_ts,
        observed_open_timestamps=observed,
        observation_updated_at=now_ts,
    )


def is_observation_resolved(record: SetupObservationRecord) -> bool:
    return record.first_outcome in _TERMINAL_OUTCOMES
