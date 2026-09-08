"""CandidateExecutionService — consume eligible ExecutionCandidate via orchestrator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.data.models import ProviderSnapshot
from exness_bot.domain.models import SymbolInfo, Tick
from exness_bot.execution.integration.adapter import map_candidate_to_execution_plan
from exness_bot.execution.integration.models import (
    CandidateExecutionPrecheck,
    CandidateExecutionResult,
    PrecheckVerdict,
)
from exness_bot.execution.integration.precheck import precheck_candidate_execution
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.result import OrchestrationOutcome
from exness_bot.market_analysis.contract.identity import MTF_STRATEGY_ID
from exness_bot.market_analysis.contract.models import (
    ExecutionCandidate,
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.store import SetupLifecycleStore
from exness_bot.paper_execution.contract import IntentLifecycle
from exness_bot.paper_execution.intent_store import DurableIntentStore

ClockFn = Callable[[], datetime]


@dataclass
class CandidateExecutionContext:
    """Fresh inputs required immediately before orchestrator consumption."""

    tick: Tick | None
    quote: SymbolInfo | None
    snapshot: ProviderSnapshot | None
    timeframe_status: dict[str, str]
    now: datetime | None = None


class CandidateExecutionService:
    """
    ExecutionCandidate → precheck → ExecutionOrchestrator (exactly once).

    Phase 17.1 default: Fake/Spy. Phase 17.2 DEMO: GatedMT5 via demo_factory only.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        setup_store: SetupLifecycleStore,
        intent_store: DurableIntentStore,
        orchestrator: ExecutionOrchestrator,
        port: Any,
        clock: ClockFn | None = None,
        strategy_id: str = MTF_STRATEGY_ID,
        transport_label: str = "FAKE",
        require_demo_market_revalidate: bool = False,
    ) -> None:
        self._settings = settings
        self._setup_store = setup_store
        self._intent_store = intent_store
        self._orchestrator = orchestrator
        self._port = port
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._strategy_id = strategy_id
        self._transport_label = transport_label
        self._require_demo_market_revalidate = require_demo_market_revalidate

    def precheck(
        self,
        candidate: ExecutionCandidate | None,
        context: CandidateExecutionContext,
    ) -> CandidateExecutionPrecheck:
        now = context.now or self._clock()
        setup = None
        if candidate is not None:
            setup = self._setup_store.get(candidate.setup_id)
            if setup is None:
                active = self._setup_store.get_active_for_symbol(candidate.symbol)
                if active is not None and active.setup_id == candidate.setup_id:
                    setup = active

        allowed, reasons = precheck_candidate_execution(
            strategy_id=self._strategy_id,
            candidate=candidate,
            setup=setup,
            setup_store=self._setup_store,
            intent_store=self._intent_store,
            tick=context.tick,
            quote=context.quote,
            snapshot=context.snapshot,
            timeframe_status=context.timeframe_status,
            now=now,
            quote_max_age_seconds=float(self._settings.live_data_stale_seconds),
            account_max_age_seconds=float(
                getattr(self._settings, "account_snapshot_max_age_seconds", 10)
            ),
            max_spread_points=int(self._settings.max_spread_points),
        )

        if (
            allowed
            and self._require_demo_market_revalidate
            and candidate is not None
            and setup is not None
            and context.tick is not None
            and context.quote is not None
        ):
            from exness_bot.execution.integration.demo_revalidate import (
                revalidate_candidate_market,
            )

            extra = revalidate_candidate_market(
                candidate=candidate,
                setup=setup,
                tick=context.tick,
                quote=context.quote,
                max_spread_points=int(self._settings.max_spread_points),
                now=now,
            )
            if extra:
                reasons = list(dict.fromkeys([*reasons, *extra]))
                allowed = False

        return CandidateExecutionPrecheck(
            allowed=allowed,
            verdict=PrecheckVerdict.READY if allowed else PrecheckVerdict.BLOCKED,
            reasons=tuple(reasons),
            candidate_id=None if candidate is None else candidate.candidate_id,
            setup_id=None if candidate is None else candidate.setup_id,
        )

    def consume(
        self,
        candidate: ExecutionCandidate,
        context: CandidateExecutionContext,
    ) -> CandidateExecutionResult:
        """Validate then call ExecutionOrchestrator exactly once when READY."""
        pre = self.precheck(candidate, context)
        if not pre.allowed:
            return CandidateExecutionResult(
                precheck=pre,
                orchestration=None,
                port_submit_count=0,
                transport=self._transport_label,
                reasons=pre.reasons,
            )

        now = context.now or self._clock()
        setup = self._setup_store.get(candidate.setup_id)
        if setup is None or context.quote is None:
            return CandidateExecutionResult(
                precheck=CandidateExecutionPrecheck(
                    allowed=False,
                    verdict=PrecheckVerdict.BLOCKED,
                    reasons=("SETUP_NOT_ACTIVE",),
                    candidate_id=candidate.candidate_id,
                    setup_id=candidate.setup_id,
                ),
                port_submit_count=0,
                transport=self._transport_label,
                reasons=("SETUP_NOT_ACTIVE",),
            )

        if setup.state != SetupLifecycleState.ENTRY_ZONE:
            return CandidateExecutionResult(
                precheck=CandidateExecutionPrecheck(
                    allowed=False,
                    verdict=PrecheckVerdict.BLOCKED,
                    reasons=("SETUP_STATE_NOT_ENTRY_ZONE",),
                    candidate_id=candidate.candidate_id,
                    setup_id=candidate.setup_id,
                ),
                port_submit_count=0,
                transport=self._transport_label,
                reasons=("SETUP_STATE_NOT_ENTRY_ZONE",),
            )

        plan = map_candidate_to_execution_plan(
            candidate, setup, decision_timestamp=now
        )
        before = self._port_call_count()
        orch = self._orchestrator.execute(plan, quote=context.quote)
        after = self._port_call_count()
        submits = max(0, after - before)

        reconciliation = None
        if orch.outcome == OrchestrationOutcome.UNKNOWN or (
            orch.lifecycle == IntentLifecycle.UNKNOWN
        ):
            reconciliation = "READ_ONLY_RECONCILIATION_REQUIRED"

        return CandidateExecutionResult(
            precheck=pre,
            orchestration=orch,
            port_submit_count=submits,
            transport=self._transport_label,
            reconciliation=reconciliation,
            reasons=(),
        )

    def _port_call_count(self) -> int:
        # Spy / Fake port
        calls = getattr(self._port, "calls", None)
        if isinstance(calls, list):
            return len(calls)
        # GatedMT5ExecutionPort — count only executor reaches (past gates)
        executor_submit = getattr(self._port, "executor_submit_count", None)
        if isinstance(executor_submit, int):
            return executor_submit
        submit_count = getattr(self._port, "submit_count", None)
        if isinstance(submit_count, int):
            return submit_count
        return 0
