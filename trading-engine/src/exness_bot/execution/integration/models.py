"""Integration result models — no broker side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from exness_bot.execution.result import OrchestrationResult


class PrecheckVerdict(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CandidateExecutionPrecheck:
    allowed: bool
    verdict: PrecheckVerdict
    reasons: tuple[str, ...]
    candidate_id: str | None = None
    setup_id: str | None = None
    intent_id: str | None = None


@dataclass(frozen=True)
class CandidateExecutionResult:
    precheck: CandidateExecutionPrecheck
    orchestration: OrchestrationResult | None = None
    port_submit_count: int = 0
    transport: str = "FAKE"
    reconciliation: str | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def submitted(self) -> bool:
        return self.port_submit_count > 0
