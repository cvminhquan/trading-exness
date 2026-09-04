"""UTC clock abstraction for deterministic candle-engine tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Source of 'now' — production uses wall clock, tests use FakeClock."""

    def now_utc(self) -> datetime:
        """Return the current instant in UTC."""
        ...


class SystemClock:
    """Wall-clock UTC."""

    def now_utc(self) -> datetime:
        return datetime.now(tz=UTC)


def _as_utc(instant: datetime) -> datetime:
    if instant.tzinfo is None:
        return instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC)


class FakeClock:
    """Mutable clock for deterministic tests."""

    def __init__(self, instant: datetime) -> None:
        self._instant = _as_utc(instant)

    def now_utc(self) -> datetime:
        return self._instant

    def set(self, instant: datetime) -> None:
        self._instant = _as_utc(instant)

    def advance(self, delta: timedelta) -> None:
        self._instant = self._instant + delta
