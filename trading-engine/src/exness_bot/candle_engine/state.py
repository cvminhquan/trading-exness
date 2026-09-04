"""Idempotency cursor for the live candle engine — no database in this phase."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from exness_bot.market_data.candles import normalize_timestamp


@dataclass(frozen=True)
class CandleCursor:
    symbol: str
    timeframe: str
    last_processed_timestamp: datetime | None


class CandleStateStore(Protocol):
    def load(self) -> CandleCursor: ...

    def save(self, cursor: CandleCursor) -> None: ...


class InMemoryCandleStateStore:
    def __init__(self, cursor: CandleCursor | None = None) -> None:
        self._lock = threading.Lock()
        self._cursor = cursor or CandleCursor(
            symbol="",
            timeframe="",
            last_processed_timestamp=None,
        )

    def load(self) -> CandleCursor:
        with self._lock:
            return self._cursor

    def save(self, cursor: CandleCursor) -> None:
        with self._lock:
            self._cursor = cursor


class FileCandleStateStore:
    """JSON file cursor so a restart does not re-emit the last candle."""

    def __init__(self, path: Path, *, symbol: str, timeframe: str) -> None:
        self._path = path
        self._symbol = symbol
        self._timeframe = timeframe
        self._lock = threading.Lock()

    def load(self) -> CandleCursor:
        with self._lock:
            if not self._path.is_file():
                return CandleCursor(
                    symbol=self._symbol,
                    timeframe=self._timeframe,
                    last_processed_timestamp=None,
                )
            raw_obj: object = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw_obj, dict):
                return CandleCursor(
                    symbol=self._symbol,
                    timeframe=self._timeframe,
                    last_processed_timestamp=None,
                )
            stamp = raw_obj.get("lastProcessedTimestamp") or raw_obj.get("last_processed_timestamp")
            parsed: datetime | None = None
            if isinstance(stamp, str) and stamp:
                parsed = normalize_timestamp(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
            return CandleCursor(
                symbol=str(raw_obj.get("symbol") or self._symbol),
                timeframe=str(raw_obj.get("timeframe") or self._timeframe),
                last_processed_timestamp=parsed,
            )

    def save(self, cursor: CandleCursor) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            stamp = cursor.last_processed_timestamp
            payload = {
                "symbol": cursor.symbol,
                "timeframe": cursor.timeframe,
                "lastProcessedTimestamp": stamp.astimezone(UTC).isoformat() if stamp else None,
            }
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
