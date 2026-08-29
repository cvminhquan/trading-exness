"""SQLite-backed trading persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import structlog

from exness_bot.persistence.models import TradingEventRecord
from exness_bot.risk.models import RiskState

logger = structlog.get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_candles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    candle_timestamp TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (symbol, timeframe, candle_timestamp)
);

CREATE TABLE IF NOT EXISTS trading_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    candle_timestamp TEXT NOT NULL,
    stage TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    day_start_equity REAL NOT NULL,
    peak_equity REAL NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def parse_sqlite_path(database_url: str) -> str:
    """Extract filesystem path from a sqlite database URL."""
    if database_url.startswith("sqlite:///"):
        return database_url.removeprefix("sqlite:///")
    if database_url.startswith("sqlite://"):
        return database_url.removeprefix("sqlite://")
    return database_url


class SQLiteTradingRepository:
    """SQLite implementation for processed candles and audit events."""

    def __init__(self, database_path: str) -> None:
        self._path = database_path
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(database_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def health_check(self) -> bool:
        try:
            self._conn.execute("SELECT 1")
            return True
        except sqlite3.Error as exc:
            logger.error("repository_health_check_failed", error=str(exc))
            return False

    def try_claim_candle(
        self,
        symbol: str,
        timeframe: str,
        candle_timestamp: datetime,
    ) -> bool:
        ts = _format_timestamp(candle_timestamp)
        now = _format_timestamp(datetime.now(tz=UTC))
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO processed_candles
                (symbol, timeframe, candle_timestamp, processed_at)
            VALUES (?, ?, ?, ?)
            """,
            (symbol, timeframe, ts, now),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def is_candle_processed(
        self,
        symbol: str,
        timeframe: str,
        candle_timestamp: datetime,
    ) -> bool:
        ts = _format_timestamp(candle_timestamp)
        row = self._conn.execute(
            """
            SELECT 1 FROM processed_candles
            WHERE symbol = ? AND timeframe = ? AND candle_timestamp = ?
            """,
            (symbol, timeframe, ts),
        ).fetchone()
        return row is not None

    def save_event(self, event: TradingEventRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO trading_events
                (symbol, timeframe, candle_timestamp, stage, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.symbol,
                event.timeframe,
                _format_timestamp(event.candle_timestamp),
                event.stage,
                json.dumps(event.payload, default=str),
                _format_timestamp(event.created_at),
            ),
        )
        self._conn.commit()

    def load_risk_state(self) -> RiskState | None:
        row = self._conn.execute(
            "SELECT day_start_equity, peak_equity FROM risk_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        return RiskState(
            day_start_equity=float(row["day_start_equity"]),
            peak_equity=float(row["peak_equity"]),
        )

    def save_risk_state(self, state: RiskState) -> None:
        now = _format_timestamp(datetime.now(tz=UTC))
        self._conn.execute(
            """
            INSERT INTO risk_state (id, day_start_equity, peak_equity, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                day_start_equity = excluded.day_start_equity,
                peak_equity = excluded.peak_equity,
                updated_at = excluded.updated_at
            """,
            (state.day_start_equity, state.peak_equity, now),
        )
        self._conn.commit()


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
