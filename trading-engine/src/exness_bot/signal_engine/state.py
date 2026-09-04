"""JSON/in-memory cursor for the Signal Engine — no database."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from exness_bot.market_data.candles import normalize_timestamp


@dataclass(frozen=True)
class SignalCursor:
    symbol: str
    timeframe: str
    strategy: str
    last_processed_timestamp: datetime | None


class SignalStateStore(Protocol):
    def load(self) -> SignalCursor: ...

    def save(self, cursor: SignalCursor) -> None: ...


class InMemorySignalStateStore:
    def __init__(self, cursor: SignalCursor | None = None) -> None:
        self._lock = threading.Lock()
        self._cursor = cursor or SignalCursor(
            symbol="",
            timeframe="",
            strategy="",
            last_processed_timestamp=None,
        )

    def load(self) -> SignalCursor:
        with self._lock:
            return self._cursor

    def save(self, cursor: SignalCursor) -> None:
        with self._lock:
            self._cursor = cursor


class FileSignalStateStore:
    def __init__(self, path: Path, *, symbol: str, timeframe: str, strategy: str) -> None:
        self._path = path
        self._symbol = symbol
        self._timeframe = timeframe
        self._strategy = strategy
        self._lock = threading.Lock()

    def load(self) -> SignalCursor:
        with self._lock:
            if not self._path.is_file():
                return SignalCursor(
                    symbol=self._symbol,
                    timeframe=self._timeframe,
                    strategy=self._strategy,
                    last_processed_timestamp=None,
                )
            raw_obj: object = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw_obj, dict):
                return SignalCursor(
                    symbol=self._symbol,
                    timeframe=self._timeframe,
                    strategy=self._strategy,
                    last_processed_timestamp=None,
                )
            stored_strategy = str(raw_obj.get("strategy") or self._strategy)
            if stored_strategy != self._strategy:
                return SignalCursor(
                    symbol=self._symbol,
                    timeframe=self._timeframe,
                    strategy=self._strategy,
                    last_processed_timestamp=None,
                )
            stamp = raw_obj.get("lastProcessedTimestamp")
            parsed: datetime | None = None
            if isinstance(stamp, str) and stamp:
                parsed = normalize_timestamp(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
            return SignalCursor(
                symbol=str(raw_obj.get("symbol") or self._symbol),
                timeframe=str(raw_obj.get("timeframe") or self._timeframe),
                strategy=stored_strategy,
                last_processed_timestamp=parsed,
            )

    def save(self, cursor: SignalCursor) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            stamp = cursor.last_processed_timestamp
            payload = {
                "symbol": cursor.symbol,
                "timeframe": cursor.timeframe,
                "strategy": cursor.strategy,
                "lastProcessedTimestamp": stamp.astimezone(UTC).isoformat() if stamp else None,
            }
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
