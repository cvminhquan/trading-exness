"""Phase 17.1 — ExecutionCandidate → ExecutionOrchestrator (FAKE transport only).

Never imports LiveMT5ExecutionTransport / build_gated_mt5_execution_port / order_send.
"""

from __future__ import annotations

from exness_bot.execution.integration.adapter import (
    build_candidate_idempotency_key,
    map_candidate_to_execution_plan,
)
from exness_bot.execution.integration.models import (
    CandidateExecutionPrecheck,
    CandidateExecutionResult,
    PrecheckVerdict,
)
from exness_bot.execution.integration.service import CandidateExecutionService

__all__ = [
    "CandidateExecutionPrecheck",
    "CandidateExecutionResult",
    "CandidateExecutionService",
    "PrecheckVerdict",
    "build_candidate_idempotency_key",
    "map_candidate_to_execution_plan",
]
