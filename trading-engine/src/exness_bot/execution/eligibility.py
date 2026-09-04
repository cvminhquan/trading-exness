"""Execution eligibility kinds — catch-up/replay must not become broker-eligible."""

from __future__ import annotations

from enum import StrEnum


class ExecutionEventKind(StrEnum):
    """
    How the upstream event was classified for execution eligibility.

    LIVE_EVENT — current closed live candle / actionable live signal.
    CATCH_UP_EVENT — historical gap / startup catch-up.
    REPLAY_EVENT — explicit replay/backfill (never broker-eligible).
    """

    LIVE = "LIVE_EVENT"
    CATCH_UP = "CATCH_UP_EVENT"
    REPLAY = "REPLAY_EVENT"


def is_broker_eligible(kind: ExecutionEventKind) -> bool:
    """Only LIVE events may proceed toward a broker-capable ExecutionPort."""
    return kind is ExecutionEventKind.LIVE
