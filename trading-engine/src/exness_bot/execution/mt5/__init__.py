"""MT5 integration boundary for Phase 12.8 — not imported by strategy/signal/risk."""

from exness_bot.execution.mt5.factory import build_gated_mt5_execution_port
from exness_bot.execution.mt5.gated_port import GatedExecutionBlocked, GatedMT5ExecutionPort
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot

__all__ = [
    "GatedExecutionBlocked",
    "GatedExecutionSnapshot",
    "GatedMT5ExecutionPort",
    "build_gated_mt5_execution_port",
]
