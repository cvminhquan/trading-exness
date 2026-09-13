"""Durable SQLite store for setup forward observations — restart-safe, idempotent."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from exness_bot.market_analysis.observation.models import (
    CheckpointObservation,
    CheckpointStatus,
    FirstOutcome,
    SetupObservationRecord,
)
from exness_bot.persistence.sqlite_repository import parse_sqlite_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS setup_forward_observation (
    setup_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    payload TEXT NOT NULL,
    first_outcome TEXT NOT NULL,
    entry_touched INTEGER NOT NULL,
    last_processed_candle_ts TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_setup_fwd_obs_symbol
ON setup_forward_observation(symbol);

CREATE INDEX IF NOT EXISTS idx_setup_fwd_obs_outcome
ON setup_forward_observation(first_outcome);
"""


class ObservationStore(Protocol):
    def get(self, setup_id: str) -> SetupObservationRecord | None: ...

    def upsert(self, record: SetupObservationRecord) -> None: ...

    def list_all(self) -> list[SetupObservationRecord]: ...

    def list_pending(self) -> list[SetupObservationRecord]: ...


def _to_iso(ts: datetime) -> str:
    return ts.isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def serialize_observation(record: SetupObservationRecord) -> str:
    payload = {
        "setup_id": record.setup_id,
        "strategy_id": record.strategy_id,
        "symbol": record.symbol,
        "direction": record.direction,
        "created_at": _to_iso(record.created_at),
        "expires_at": _to_iso(record.expires_at),
        "source_candle_timestamp": _to_iso(record.source_candle_timestamp),
        "primary_timeframe": record.primary_timeframe,
        "signal_price": record.signal_price,
        "entry_price": record.entry_price,
        "entry_zone_low": record.entry_zone_low,
        "entry_zone_high": record.entry_zone_high,
        "stop_loss": record.stop_loss,
        "tp1_price": record.tp1_price,
        "risk_distance": record.risk_distance,
        "entry_touched": record.entry_touched,
        "first_entry_touch_at": (
            _to_iso(record.first_entry_touch_at)
            if record.first_entry_touch_at
            else None
        ),
        "mfe_price": record.mfe_price,
        "mae_price": record.mae_price,
        "mfe_r": record.mfe_r,
        "mae_r": record.mae_r,
        "mfe_extreme_at": (
            _to_iso(record.mfe_extreme_at) if record.mfe_extreme_at else None
        ),
        "mae_extreme_at": (
            _to_iso(record.mae_extreme_at) if record.mae_extreme_at else None
        ),
        "tp1_touched_at": (
            _to_iso(record.tp1_touched_at) if record.tp1_touched_at else None
        ),
        "sl_touched_at": (
            _to_iso(record.sl_touched_at) if record.sl_touched_at else None
        ),
        "first_outcome": record.first_outcome.value,
        "checkpoints": [
            {
                "label": cp.label,
                "due_at": _to_iso(cp.due_at),
                "status": cp.status.value,
                "candle_timestamp": (
                    _to_iso(cp.candle_timestamp) if cp.candle_timestamp else None
                ),
                "open": cp.open,
                "high": cp.high,
                "low": cp.low,
                "close": cp.close,
            }
            for cp in record.checkpoints
        ],
        "terminal_lifecycle_state": record.terminal_lifecycle_state,
        "last_processed_candle_ts": (
            _to_iso(record.last_processed_candle_ts)
            if record.last_processed_candle_ts
            else None
        ),
        "observed_open_timestamps": [
            _to_iso(ts) for ts in record.observed_open_timestamps
        ],
        "observation_updated_at": (
            _to_iso(record.observation_updated_at)
            if record.observation_updated_at
            else None
        ),
        "notes": list(record.notes),
    }
    return json.dumps(payload, sort_keys=True)


def deserialize_observation(raw: str) -> SetupObservationRecord:
    data = json.loads(raw)
    checkpoints = tuple(
        CheckpointObservation(
            label=str(cp["label"]),
            due_at=datetime.fromisoformat(cp["due_at"]),
            status=CheckpointStatus(cp["status"]),
            candle_timestamp=_from_iso(cp.get("candle_timestamp")),
            open=cp.get("open"),
            high=cp.get("high"),
            low=cp.get("low"),
            close=cp.get("close"),
        )
        for cp in data.get("checkpoints", [])
    )
    return SetupObservationRecord(
        setup_id=data["setup_id"],
        strategy_id=data["strategy_id"],
        symbol=data["symbol"],
        direction=data["direction"],
        created_at=datetime.fromisoformat(data["created_at"]),
        expires_at=datetime.fromisoformat(data["expires_at"]),
        source_candle_timestamp=datetime.fromisoformat(
            data["source_candle_timestamp"]
        ),
        primary_timeframe=data["primary_timeframe"],
        signal_price=data.get("signal_price"),
        entry_price=float(data["entry_price"]),
        entry_zone_low=float(data["entry_zone_low"]),
        entry_zone_high=float(data["entry_zone_high"]),
        stop_loss=float(data["stop_loss"]),
        tp1_price=data.get("tp1_price"),
        risk_distance=data.get("risk_distance"),
        entry_touched=bool(data.get("entry_touched", False)),
        first_entry_touch_at=_from_iso(data.get("first_entry_touch_at")),
        mfe_price=float(data.get("mfe_price", 0.0)),
        mae_price=float(data.get("mae_price", 0.0)),
        mfe_r=data.get("mfe_r"),
        mae_r=data.get("mae_r"),
        mfe_extreme_at=_from_iso(data.get("mfe_extreme_at")),
        mae_extreme_at=_from_iso(data.get("mae_extreme_at")),
        tp1_touched_at=_from_iso(data.get("tp1_touched_at")),
        sl_touched_at=_from_iso(data.get("sl_touched_at")),
        first_outcome=FirstOutcome(data.get("first_outcome", "OPEN")),
        checkpoints=checkpoints,
        terminal_lifecycle_state=data.get("terminal_lifecycle_state"),
        last_processed_candle_ts=_from_iso(data.get("last_processed_candle_ts")),
        observed_open_timestamps=tuple(
            datetime.fromisoformat(ts)
            for ts in data.get("observed_open_timestamps") or []
        ),
        observation_updated_at=_from_iso(data.get("observation_updated_at")),
        notes=tuple(data.get("notes") or ()),
    )


class InMemoryObservationStore:
    """Test / ephemeral store."""

    def __init__(self) -> None:
        self._by_id: dict[str, SetupObservationRecord] = {}
        self._lock = threading.RLock()

    def get(self, setup_id: str) -> SetupObservationRecord | None:
        with self._lock:
            return self._by_id.get(setup_id)

    def upsert(self, record: SetupObservationRecord) -> None:
        with self._lock:
            self._by_id[record.setup_id] = record

    def list_all(self) -> list[SetupObservationRecord]:
        with self._lock:
            return list(self._by_id.values())

    def list_pending(self) -> list[SetupObservationRecord]:
        pending = {
            FirstOutcome.OPEN,
            FirstOutcome.ENTRY_TOUCHED,
            FirstOutcome.UNRESOLVED,
        }
        with self._lock:
            return [r for r in self._by_id.values() if r.first_outcome in pending]


class SqliteObservationStore:
    """Durable observation across process restarts."""

    def __init__(self, database_url: str) -> None:
        self._path = parse_sqlite_path(database_url)
        self._lock = threading.RLock()
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, setup_id: str) -> SetupObservationRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM setup_forward_observation WHERE setup_id = ?",
                (setup_id,),
            ).fetchone()
        if row is None:
            return None
        return deserialize_observation(row["payload"])

    def upsert(self, record: SetupObservationRecord) -> None:
        payload = serialize_observation(record)
        now_ts = datetime.now(tz=UTC)
        last_ts = (
            _to_iso(record.last_processed_candle_ts)
            if record.last_processed_candle_ts
            else None
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO setup_forward_observation
                    (setup_id, symbol, strategy_id, direction, payload,
                     first_outcome, entry_touched, last_processed_candle_ts, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(setup_id) DO UPDATE SET
                    payload=excluded.payload,
                    first_outcome=excluded.first_outcome,
                    entry_touched=excluded.entry_touched,
                    last_processed_candle_ts=excluded.last_processed_candle_ts,
                    updated_at=excluded.updated_at
                """,
                (
                    record.setup_id,
                    record.symbol,
                    record.strategy_id,
                    record.direction,
                    payload,
                    record.first_outcome.value,
                    1 if record.entry_touched else 0,
                    last_ts,
                    _to_iso(now_ts),
                ),
            )
            conn.commit()

    def list_all(self) -> list[SetupObservationRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM setup_forward_observation"
            ).fetchall()
        return [deserialize_observation(r["payload"]) for r in rows]

    def list_pending(self) -> list[SetupObservationRecord]:
        pending = (
            FirstOutcome.OPEN.value,
            FirstOutcome.ENTRY_TOUCHED.value,
            FirstOutcome.UNRESOLVED.value,
        )
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM setup_forward_observation
                WHERE first_outcome IN (?, ?, ?)
                """,
                pending,
            ).fetchall()
        return [deserialize_observation(r["payload"]) for r in rows]
