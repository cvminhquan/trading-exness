"""Durable auto-demo decision store — per closed-M15 idempotency + audit."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from exness_bot.market_analysis.contract.identity import MTF_STRATEGY_ID


class AutoDemoDecisionState(StrEnum):
    OBSERVED = "OBSERVED"
    EVALUATING = "EVALUATING"
    BLOCKED = "BLOCKED"
    ELIGIBLE = "ELIGIBLE"
    IN_FLIGHT = "IN_FLIGHT"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    SKIPPED = "SKIPPED"


# States that must never auto-resubmit for the same decision_id.
_NO_RESUBMIT = frozenset(
    {
        AutoDemoDecisionState.BLOCKED,
        AutoDemoDecisionState.SKIPPED,
        AutoDemoDecisionState.SUBMITTED,
        AutoDemoDecisionState.ACCEPTED,
        AutoDemoDecisionState.REJECTED,
        AutoDemoDecisionState.IN_FLIGHT,
        AutoDemoDecisionState.UNKNOWN,
    }
)


def build_decision_id(
    *,
    symbol: str,
    timeframe: str,
    closed_m15_timestamp: datetime,
    strategy_id: str = MTF_STRATEGY_ID,
) -> str:
    ts = closed_m15_timestamp
    ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    return f"{symbol}|{timeframe}|{ts.isoformat()}|{strategy_id}"


def should_skip_existing(state: AutoDemoDecisionState | str | None) -> bool:
    if state is None:
        return False
    value = state if isinstance(state, AutoDemoDecisionState) else AutoDemoDecisionState(state)
    return value in _NO_RESUBMIT


@dataclass
class AutoDemoDecisionRecord:
    decision_id: str
    symbol: str
    timeframe: str
    closed_m15_timestamp: str
    strategy_id: str
    state: str
    candidate_id: str | None = None
    signal: str | None = None
    eligibility: str | None = None
    blocked_reasons: list[str] = field(default_factory=list)
    risk_snapshot: dict[str, Any] = field(default_factory=dict)
    spread: float | None = None
    requested_volume: float | None = None
    execution_plan_id: str | None = None
    broker_request_id: str | None = None
    broker_response: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sqlite_path_from_database_url(database_url: str) -> Path | None:
    """Resolve sqlite URL to a filesystem path (relative paths stay relative)."""
    from exness_bot.persistence.sqlite_repository import parse_sqlite_path

    raw = (database_url or "").strip()
    if not raw:
        return None
    if raw == ":memory:" or raw.lower().endswith(":memory:"):
        return None
    if not raw.lower().startswith("sqlite"):
        # Bare path fallback
        return Path(raw)
    path_str = parse_sqlite_path(raw).strip()
    if not path_str or path_str == ":memory:":
        return None
    return Path(path_str)


class SqliteAutoDemoDecisionStore:
    """SQLite-backed decision audit + idempotency for autonomous DEMO."""

    def __init__(self, path: Path) -> None:
        self._path = path if path.is_absolute() else path.resolve()
        self._lock = threading.RLock()
        if self._path.parent != self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @classmethod
    def from_settings_database_url(
        cls, database_url: str, *, fallback: Path
    ) -> SqliteAutoDemoDecisionStore:
        path = sqlite_path_from_database_url(database_url) or fallback
        # Prefer sibling file next to main db when possible.
        if path.suffix:
            decision_path = path.with_name(f"{path.stem}_auto_demo_decisions.db")
        else:
            decision_path = fallback
        return cls(decision_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auto_demo_decisions (
                    decision_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    closed_m15_timestamp TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    candidate_id TEXT,
                    signal TEXT,
                    eligibility TEXT,
                    blocked_reasons TEXT NOT NULL DEFAULT '[]',
                    risk_snapshot TEXT NOT NULL DEFAULT '{}',
                    spread REAL,
                    requested_volume REAL,
                    execution_plan_id TEXT,
                    broker_request_id TEXT,
                    broker_response TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_auto_demo_updated "
                "ON auto_demo_decisions(updated_at DESC)"
            )
            conn.commit()

    def get(self, decision_id: str) -> AutoDemoDecisionRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auto_demo_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def latest(self) -> AutoDemoDecisionRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auto_demo_decisions ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return None if row is None else self._from_row(row)

    def upsert(self, record: AutoDemoDecisionRecord) -> AutoDemoDecisionRecord:
        now = datetime.now(tz=UTC).isoformat()
        existing = self.get(record.decision_id)
        if existing and existing.created_at:
            created = existing.created_at
        else:
            created = record.created_at or now
        record.created_at = created
        record.updated_at = now
        payload = (
            record.decision_id,
            record.symbol,
            record.timeframe,
            record.closed_m15_timestamp,
            record.strategy_id,
            record.state,
            record.candidate_id,
            record.signal,
            record.eligibility,
            json.dumps(list(record.blocked_reasons)),
            json.dumps(record.risk_snapshot or {}),
            record.spread,
            record.requested_volume,
            record.execution_plan_id,
            record.broker_request_id,
            record.broker_response,
            record.created_at,
            record.updated_at,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO auto_demo_decisions (
                    decision_id, symbol, timeframe, closed_m15_timestamp, strategy_id,
                    state, candidate_id, signal, eligibility, blocked_reasons,
                    risk_snapshot, spread, requested_volume, execution_plan_id,
                    broker_request_id, broker_response, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    state=excluded.state,
                    candidate_id=excluded.candidate_id,
                    signal=excluded.signal,
                    eligibility=excluded.eligibility,
                    blocked_reasons=excluded.blocked_reasons,
                    risk_snapshot=excluded.risk_snapshot,
                    spread=excluded.spread,
                    requested_volume=excluded.requested_volume,
                    execution_plan_id=excluded.execution_plan_id,
                    broker_request_id=excluded.broker_request_id,
                    broker_response=excluded.broker_response,
                    updated_at=excluded.updated_at
                """,
                payload,
            )
            conn.commit()
        return record

    def _from_row(self, row: sqlite3.Row) -> AutoDemoDecisionRecord:
        return AutoDemoDecisionRecord(
            decision_id=row["decision_id"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            closed_m15_timestamp=row["closed_m15_timestamp"],
            strategy_id=row["strategy_id"],
            state=row["state"],
            candidate_id=row["candidate_id"],
            signal=row["signal"],
            eligibility=row["eligibility"],
            blocked_reasons=json.loads(row["blocked_reasons"] or "[]"),
            risk_snapshot=json.loads(row["risk_snapshot"] or "{}"),
            spread=row["spread"],
            requested_volume=row["requested_volume"],
            execution_plan_id=row["execution_plan_id"],
            broker_request_id=row["broker_request_id"],
            broker_response=row["broker_response"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
