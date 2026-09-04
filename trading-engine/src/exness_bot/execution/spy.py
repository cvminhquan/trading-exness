"""Spy ExecutionPort — count side effects. Never touches MT5."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from exness_bot.domain.models import SymbolInfo
from exness_bot.paper_execution.contract import AckStatus, ExecutionAck, ExecutionIntent


class SpyExecutionPort:
    """
    Deterministic ExecutionPort for Phase 12.6 tests.

    Capabilities: calls, intents, configured acknowledgements, configured exceptions.
    """

    def __init__(
        self,
        *,
        responses: AckStatus | Sequence[AckStatus] | None = AckStatus.FILLED,
        exceptions: Sequence[BaseException] | None = None,
        fill_price: float | None = 2350.0,
        on_submit: Callable[[ExecutionIntent], None] | None = None,
    ) -> None:
        if responses is None:
            self._queue: list[AckStatus] = [AckStatus.FILLED]
            self._repeat = AckStatus.FILLED
        elif isinstance(responses, AckStatus):
            self._queue = [responses]
            self._repeat = responses
        else:
            items = list(responses)
            if not items:
                msg = "SpyExecutionPort requires at least one response"
                raise ValueError(msg)
            self._queue = items
            self._repeat = items[-1]
        self._exceptions = list(exceptions or ())
        self._fill_price = fill_price
        self._on_submit = on_submit
        self.calls: list[ExecutionIntent] = []

    @property
    def intents(self) -> tuple[ExecutionIntent, ...]:
        return tuple(self.calls)

    def submit(self, intent: ExecutionIntent, *, quote: SymbolInfo) -> ExecutionAck:
        del quote
        if self._on_submit is not None:
            self._on_submit(intent)
        if self._exceptions:
            exc = self._exceptions.pop(0)
            self.calls.append(intent)
            raise exc
        self.calls.append(intent)
        status = self._queue.pop(0) if self._queue else self._repeat
        now = datetime.now(tz=UTC)
        if status is AckStatus.FILLED:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.FILLED,
                timestamp=now,
                fill_price=self._fill_price,
                filled_quantity=intent.requested_quantity,
                reason="spy_filled",
            )
        if status is AckStatus.REJECTED:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.REJECTED,
                timestamp=now,
                reason="spy_rejected",
            )
        if status is AckStatus.TIMEOUT:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.TIMEOUT,
                timestamp=now,
                reason="spy_timeout",
            )
        if status is AckStatus.ACCEPTED:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.ACCEPTED,
                timestamp=now,
                reason="spy_accepted",
            )
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.UNKNOWN,
            timestamp=now,
            reason="spy_unknown",
        )
