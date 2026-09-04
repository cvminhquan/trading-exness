"""Execution port — broker-agnostic. Intent in; acknowledgement out."""

from __future__ import annotations

from typing import Protocol

from exness_bot.domain.models import SymbolInfo
from exness_bot.paper_execution.contract import ExecutionAck, ExecutionIntent


class ExecutionPort(Protocol):
    """
    Pure execution contract for Phase 11 and future live.

    Implementations must only depend on ExecutionIntent / ExecutionAck / SymbolInfo.
    Paper-specific account and position types stay behind PaperExecutor.

    A future live executor (not implemented in Phase 11) should implement submit only.
    """

    def submit(self, intent: ExecutionIntent, *, quote: SymbolInfo) -> ExecutionAck:
        """
        Submit an execution intent.

        Fill is produced by the executor when status is FILLED.
        ACCEPTED means accepted-but-not-final — never treat as FILLED.
        """
        ...
