"""Phase 17.3.2 — forward observation models (read-only research).

Không feed ngược vào eligibility / candidate / execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class FirstOutcome(StrEnum):
    """Kết quả quan sát đầu tiên có thể suy ra từ closed candles."""

    OPEN = "OPEN"
    ENTRY_TOUCHED = "ENTRY_TOUCHED"
    TP1_FIRST = "TP1_FIRST"
    SL_FIRST = "SL_FIRST"
    AMBIGUOUS = "AMBIGUOUS"
    EXPIRED_NO_ENTRY = "EXPIRED_NO_ENTRY"
    UNRESOLVED = "UNRESOLVED"


class CheckpointStatus(StrEnum):
    PENDING = "PENDING"
    FINALIZED = "FINALIZED"
    UNKNOWN = "UNKNOWN"


CHECKPOINT_OFFSETS_MINUTES: tuple[tuple[str, int], ...] = (
    ("+15m", 15),
    ("+30m", 30),
    ("+1h", 60),
    ("+2h", 120),
)


@dataclass(frozen=True)
class CheckpointObservation:
    label: str
    due_at: datetime
    status: CheckpointStatus
    candle_timestamp: datetime | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None


@dataclass(frozen=True)
class SetupObservationRecord:
    """Durable forward-observation gắn với một immutable setup_id."""

    setup_id: str
    strategy_id: str
    symbol: str
    direction: str
    created_at: datetime
    expires_at: datetime
    source_candle_timestamp: datetime
    primary_timeframe: str

    # Frozen geometry snapshot (không đổi sau capture)
    signal_price: float | None
    entry_price: float
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    tp1_price: float | None
    risk_distance: float | None

    entry_touched: bool = False
    first_entry_touch_at: datetime | None = None

    mfe_price: float = 0.0
    mae_price: float = 0.0
    mfe_r: float | None = None
    mae_r: float | None = None
    mfe_extreme_at: datetime | None = None
    mae_extreme_at: datetime | None = None

    tp1_touched_at: datetime | None = None
    sl_touched_at: datetime | None = None
    first_outcome: FirstOutcome = FirstOutcome.OPEN

    checkpoints: tuple[CheckpointObservation, ...] = ()
    terminal_lifecycle_state: str | None = None

    last_processed_candle_ts: datetime | None = None
    # Các open-timestamp closed candle đã quan sát trong lifetime (để chứng minh coverage)
    observed_open_timestamps: tuple[datetime, ...] = ()
    observation_updated_at: datetime | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ObservationSummary:
    total_captured: int
    entry_touched_count: int
    expired_no_entry_count: int
    tp1_first_count: int
    sl_first_count: int
    ambiguous_count: int
    open_unresolved_count: int
    by_symbol: dict[str, int] = field(default_factory=dict)
    by_direction: dict[str, int] = field(default_factory=dict)
