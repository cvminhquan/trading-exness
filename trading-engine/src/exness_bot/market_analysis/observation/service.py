"""Read-only observation service: capture / ingest / resume / summary.

Không import eligibility, candidate, execution orchestrator, hay MT5 order paths.
"""

from __future__ import annotations

from datetime import datetime

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.contract.models import CanonicalTradeSetup
from exness_bot.market_analysis.observation.engine import (
    initial_checkpoints,
    process_closed_candles,
    risk_distance,
)
from exness_bot.market_analysis.observation.models import (
    FirstOutcome,
    ObservationSummary,
    SetupObservationRecord,
)
from exness_bot.market_analysis.observation.store import ObservationStore
from exness_bot.market_data.candles import normalize_timestamp


def _tp1_price(setup: CanonicalTradeSetup) -> float | None:
    for tp in setup.take_profits:
        if tp.level == 1:
            return float(tp.price)
    if setup.take_profits:
        return float(setup.take_profits[0].price)
    return None


def build_observation_from_setup(
    setup: CanonicalTradeSetup,
    *,
    signal_price: float | None = None,
    now: datetime | None = None,
) -> SetupObservationRecord:
    """Tạo observation snapshot từ immutable CanonicalTradeSetup."""
    created = normalize_timestamp(setup.created_at)
    dist = risk_distance(entry_price=setup.entry_price, stop_loss=setup.stop_loss)
    return SetupObservationRecord(
        setup_id=setup.setup_id,
        strategy_id=setup.strategy_id,
        symbol=setup.symbol,
        direction=setup.direction,
        created_at=created,
        expires_at=normalize_timestamp(setup.expires_at),
        source_candle_timestamp=normalize_timestamp(setup.source_candle_timestamp),
        primary_timeframe=setup.primary_timeframe,
        signal_price=signal_price if signal_price is not None else setup.entry_price,
        entry_price=float(setup.entry_price),
        entry_zone_low=float(setup.entry_zone_low),
        entry_zone_high=float(setup.entry_zone_high),
        stop_loss=float(setup.stop_loss),
        tp1_price=_tp1_price(setup),
        risk_distance=dist,
        checkpoints=initial_checkpoints(created_at=created),
        terminal_lifecycle_state=setup.state.value,
        observation_updated_at=normalize_timestamp(now) if now else created,
    )


class SetupObservationService:
    """Capture + forward ingest — độc lập execution."""

    def __init__(self, store: ObservationStore) -> None:
        self._store = store

    def capture(
        self,
        setup: CanonicalTradeSetup,
        *,
        signal_price: float | None = None,
        now: datetime | None = None,
    ) -> SetupObservationRecord:
        """Idempotent: cùng setup_id không tạo duplicate / không ghi đè geometry."""
        existing = self._store.get(setup.setup_id)
        if existing is not None:
            return existing
        record = build_observation_from_setup(
            setup, signal_price=signal_price, now=now
        )
        self._store.upsert(record)
        return record

    def ingest_candles(
        self,
        setup_id: str,
        *,
        candles: list[Candle],
        now: datetime,
        timeframe: Timeframe | None = None,
        terminal_lifecycle_state: str | None = None,
    ) -> SetupObservationRecord | None:
        current = self._store.get(setup_id)
        if current is None:
            return None
        updated = process_closed_candles(
            current,
            candles=candles,
            now=now,
            timeframe=timeframe,
            terminal_lifecycle_state=terminal_lifecycle_state,
        )
        self._store.upsert(updated)
        return updated

    def resume_pending(
        self,
        *,
        candles_by_symbol: dict[str, list[Candle]],
        now: datetime,
    ) -> list[SetupObservationRecord]:
        """Resume pending observations sau restart bằng closed candles đã có."""
        results: list[SetupObservationRecord] = []
        for record in self._store.list_pending():
            candles = candles_by_symbol.get(record.symbol.upper()) or candles_by_symbol.get(
                record.symbol
            )
            if not candles:
                results.append(record)
                continue
            updated = process_closed_candles(record, candles=candles, now=now)
            self._store.upsert(updated)
            results.append(updated)
        return results

    def get(self, setup_id: str) -> SetupObservationRecord | None:
        return self._store.get(setup_id)

    def summarize(self) -> ObservationSummary:
        records = self._store.list_all()
        by_symbol: dict[str, int] = {}
        by_direction: dict[str, int] = {}
        entry_touched = 0
        expired_no_entry = 0
        tp1_first = 0
        sl_first = 0
        ambiguous = 0
        open_unresolved = 0

        for r in records:
            by_symbol[r.symbol] = by_symbol.get(r.symbol, 0) + 1
            by_direction[r.direction] = by_direction.get(r.direction, 0) + 1
            if r.entry_touched:
                entry_touched += 1
            if r.first_outcome == FirstOutcome.EXPIRED_NO_ENTRY:
                expired_no_entry += 1
            elif r.first_outcome == FirstOutcome.TP1_FIRST:
                tp1_first += 1
            elif r.first_outcome == FirstOutcome.SL_FIRST:
                sl_first += 1
            elif r.first_outcome == FirstOutcome.AMBIGUOUS:
                ambiguous += 1
            elif r.first_outcome in {
                FirstOutcome.OPEN,
                FirstOutcome.ENTRY_TOUCHED,
                FirstOutcome.UNRESOLVED,
            }:
                open_unresolved += 1

        return ObservationSummary(
            total_captured=len(records),
            entry_touched_count=entry_touched,
            expired_no_entry_count=expired_no_entry,
            tp1_first_count=tp1_first,
            sl_first_count=sl_first,
            ambiguous_count=ambiguous,
            open_unresolved_count=open_unresolved,
            by_symbol=by_symbol,
            by_direction=by_direction,
        )
