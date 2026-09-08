"""Durable setup lifecycle store (SQLite) — no broker calls."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Protocol

from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    SetupLifecycleState,
)
from exness_bot.market_analysis.models import AnalysisReason
from exness_bot.market_analysis.setup import TakeProfitLevel
from exness_bot.persistence.sqlite_repository import parse_sqlite_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_setup_lifecycle (
    setup_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    state TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analysis_setup_symbol_state
ON analysis_setup_lifecycle(symbol, state);
"""


class SetupLifecycleStore(Protocol):
    def get(self, setup_id: str) -> CanonicalTradeSetup | None: ...

    def get_active_for_symbol(self, symbol: str) -> CanonicalTradeSetup | None: ...

    def upsert(self, setup: CanonicalTradeSetup) -> None: ...

    def mark_state(
        self, setup_id: str, state: SetupLifecycleState, *, now: datetime
    ) -> CanonicalTradeSetup | None: ...


def _to_iso(ts: datetime) -> str:
    return ts.isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def serialize_setup(setup: CanonicalTradeSetup) -> str:
    payload = {
        "setup_id": setup.setup_id,
        "strategy_id": setup.strategy_id,
        "symbol": setup.symbol,
        "broker_symbol": setup.broker_symbol,
        "primary_timeframe": setup.primary_timeframe,
        "direction": setup.direction,
        "source_candle_timestamp": _to_iso(setup.source_candle_timestamp),
        "created_at": _to_iso(setup.created_at),
        "expires_at": _to_iso(setup.expires_at),
        "entry_type": setup.entry_type,
        "entry_zone_low": setup.entry_zone_low,
        "entry_zone_high": setup.entry_zone_high,
        "entry_price": setup.entry_price,
        "stop_loss": setup.stop_loss,
        "take_profits": [
            {
                "level": tp.level,
                "price": tp.price,
                "allocation_pct": tp.allocation_pct,
                "rr": tp.rr,
                "reason": tp.reason,
            }
            for tp in setup.take_profits
        ],
        "confidence_score": setup.confidence_score,
        "confidence_meaning": setup.confidence_meaning,
        "analysis_fingerprint": setup.analysis_fingerprint,
        "state": setup.state.value,
        "risk_snapshot": setup.risk_snapshot,
        "reasons": [
            {"code": r.code, "passed": r.passed, "message": r.message}
            for r in setup.reasons
        ],
        "warnings": [
            {"code": r.code, "passed": r.passed, "message": r.message}
            for r in setup.warnings
        ],
        "contract_version": setup.contract_version,
    }
    return json.dumps(payload, sort_keys=True)


def deserialize_setup(raw: str) -> CanonicalTradeSetup:
    data = json.loads(raw)
    return CanonicalTradeSetup(
        setup_id=data["setup_id"],
        strategy_id=data["strategy_id"],
        symbol=data["symbol"],
        broker_symbol=data["broker_symbol"],
        primary_timeframe=data["primary_timeframe"],
        direction=data["direction"],
        source_candle_timestamp=_from_iso(data["source_candle_timestamp"]),
        created_at=_from_iso(data["created_at"]),
        expires_at=_from_iso(data["expires_at"]),
        entry_type=data["entry_type"],
        entry_zone_low=float(data["entry_zone_low"]),
        entry_zone_high=float(data["entry_zone_high"]),
        entry_price=float(data["entry_price"]),
        stop_loss=float(data["stop_loss"]),
        take_profits=tuple(
            TakeProfitLevel(
                level=int(tp["level"]),
                price=float(tp["price"]),
                allocation_pct=float(tp["allocation_pct"]),
                rr=float(tp["rr"]),
                reason=str(tp["reason"]),
            )
            for tp in data.get("take_profits", [])
        ),
        confidence_score=float(data["confidence_score"]),
        confidence_meaning=data["confidence_meaning"],
        analysis_fingerprint=data["analysis_fingerprint"],
        state=SetupLifecycleState(data["state"]),
        risk_snapshot=dict(data.get("risk_snapshot") or {}),
        reasons=tuple(
            AnalysisReason(
                code=r["code"], passed=bool(r["passed"]), message=r["message"]
            )
            for r in data.get("reasons", [])
        ),
        warnings=tuple(
            AnalysisReason(
                code=r["code"], passed=bool(r["passed"]), message=r["message"]
            )
            for r in data.get("warnings", [])
        ),
        contract_version=str(data.get("contract_version", "1")),
    )


class InMemorySetupLifecycleStore:
    """Test / ephemeral store."""

    def __init__(self) -> None:
        self._by_id: dict[str, CanonicalTradeSetup] = {}
        self._lock = threading.RLock()

    def get(self, setup_id: str) -> CanonicalTradeSetup | None:
        with self._lock:
            return self._by_id.get(setup_id)

    def get_active_for_symbol(self, symbol: str) -> CanonicalTradeSetup | None:
        active = {
            SetupLifecycleState.WAITING_FOR_ENTRY,
            SetupLifecycleState.ENTRY_ZONE,
        }
        with self._lock:
            matches = [
                s
                for s in self._by_id.values()
                if s.symbol.upper() == symbol.upper() and s.state in active
            ]
        if not matches:
            return None
        return max(matches, key=lambda s: s.created_at)

    def upsert(self, setup: CanonicalTradeSetup) -> None:
        with self._lock:
            self._by_id[setup.setup_id] = setup

    def mark_state(
        self, setup_id: str, state: SetupLifecycleState, *, now: datetime
    ) -> CanonicalTradeSetup | None:
        with self._lock:
            current = self._by_id.get(setup_id)
            if current is None:
                return None
            updated = CanonicalTradeSetup(
                **{**current.__dict__, "state": state}
            )
            self._by_id[setup_id] = updated
            return updated


class SqliteSetupLifecycleStore:
    """Durable lifecycle across API polls."""

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

    def get(self, setup_id: str) -> CanonicalTradeSetup | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM analysis_setup_lifecycle WHERE setup_id = ?",
                (setup_id,),
            ).fetchone()
        if row is None:
            return None
        return deserialize_setup(row["payload"])

    def get_active_for_symbol(self, symbol: str) -> CanonicalTradeSetup | None:
        active = (
            SetupLifecycleState.WAITING_FOR_ENTRY.value,
            SetupLifecycleState.ENTRY_ZONE.value,
        )
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM analysis_setup_lifecycle
                WHERE upper(symbol) = upper(?) AND state IN (?, ?)
                """,
                (symbol, *active),
            ).fetchall()
        setups = [deserialize_setup(r["payload"]) for r in rows]
        if not setups:
            return None
        return max(setups, key=lambda s: s.created_at)

    def upsert(self, setup: CanonicalTradeSetup) -> None:
        payload = serialize_setup(setup)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_setup_lifecycle
                    (setup_id, symbol, strategy_id, payload, state, fingerprint, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(setup_id) DO UPDATE SET
                    payload=excluded.payload,
                    state=excluded.state,
                    fingerprint=excluded.fingerprint,
                    updated_at=excluded.updated_at
                """,
                (
                    setup.setup_id,
                    setup.symbol,
                    setup.strategy_id,
                    payload,
                    setup.state.value,
                    setup.analysis_fingerprint,
                    _to_iso(setup.created_at),
                ),
            )
            conn.commit()

    def mark_state(
        self, setup_id: str, state: SetupLifecycleState, *, now: datetime
    ) -> CanonicalTradeSetup | None:
        current = self.get(setup_id)
        if current is None:
            return None
        updated = CanonicalTradeSetup(**{**current.__dict__, "state": state})
        self.upsert(updated)
        return updated
