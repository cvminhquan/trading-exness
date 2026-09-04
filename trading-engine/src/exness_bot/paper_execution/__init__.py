"""Paper execution — virtual orders only. No broker trading APIs."""

from typing import Any

from exness_bot.paper_execution.contract import ExecutionAck, ExecutionIntent
from exness_bot.paper_execution.models import ExecutionMode, ExecutionOutcome
from exness_bot.paper_execution.port import ExecutionPort

__all__ = [
    "ExecutionAck",
    "ExecutionIntent",
    "ExecutionMode",
    "ExecutionOutcome",
    "ExecutionPort",
    "ExecutionService",
]


def __getattr__(name: str) -> Any:
    if name == "ExecutionService":
        from exness_bot.paper_execution.service import ExecutionService

        return ExecutionService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
