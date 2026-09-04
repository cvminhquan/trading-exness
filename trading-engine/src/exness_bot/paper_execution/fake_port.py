"""Fake ExecutionPort for lifecycle tests — no MT5, no trading APIs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from exness_bot.domain.models import SymbolInfo
from exness_bot.paper_execution.contract import AckStatus, ExecutionAck, ExecutionIntent


class FakeExecutionPort:
    """
    Deterministic test double for ExecutionPort.submit.

    Not wired into production. Never imports broker trading types.
    Does not manage PaperAccount / VirtualPosition (pure port surface).
    """

    def __init__(
        self,
        *,
        responses: AckStatus | Sequence[AckStatus] = AckStatus.FILLED,
    ) -> None:
        if isinstance(responses, AckStatus):
            self._queue: list[AckStatus] = [responses]
            self._repeat = responses
        else:
            items = list(responses)
            if not items:
                msg = "FakeExecutionPort requires at least one response"
                raise ValueError(msg)
            self._queue = items
            self._repeat = items[-1]
        self.calls: list[ExecutionIntent] = []

    def submit(self, intent: ExecutionIntent, *, quote: SymbolInfo) -> ExecutionAck:
        del quote
        self.calls.append(intent)
        status = self._queue.pop(0) if self._queue else self._repeat
        now = datetime.now(tz=UTC)
        if status == AckStatus.FILLED:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.FILLED,
                timestamp=now,
                requested_price=None,
                fill_price=None,
                filled_quantity=intent.requested_quantity,
                reason="fake_filled",
            )
        if status == AckStatus.ACCEPTED:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.ACCEPTED,
                timestamp=now,
                reason="fake_accepted",
            )
        if status == AckStatus.REJECTED:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.REJECTED,
                timestamp=now,
                reason="fake_rejected",
            )
        if status == AckStatus.TIMEOUT:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.TIMEOUT,
                timestamp=now,
                reason="fake_timeout",
            )
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.UNKNOWN,
            timestamp=now,
            reason="fake_unknown",
        )
