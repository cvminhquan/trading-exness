"""One-shot transport wrapper — max one broker send. No retry."""

from __future__ import annotations

from typing import Any

from exness_bot.broker.mt5.execution_transport import (
    MT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)


class OneShotExecutionTransport:
    """
    Guarantees at most one transport.send() call.

    A second call returns UNKNOWN without invoking the inner transport
    (fail-closed — never a second broker mutation).
    """

    def __init__(self, inner: MT5ExecutionTransport) -> None:
        self._inner = inner
        self.send_count = 0
        self._sent = False

    def send(self, request: dict[str, Any]) -> MT5TransportResult:
        if self._sent:
            self.send_count += 1
            return MT5TransportResult(
                outcome=TransportOutcome.UNKNOWN,
                comment="ONE_SHOT_VIOLATION: second submission blocked",
            )
        self._sent = True
        self.send_count += 1
        return self._inner.send(request)

    @property
    def already_sent(self) -> bool:
        return self._sent
