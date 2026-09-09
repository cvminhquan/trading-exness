"""Autonomous DEMO execution loop — closed M15 trigger only."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from exness_bot.config.settings import Settings
from exness_bot.domain.models import AccountInfo, Position
from exness_bot.execution.auto_demo.decision_store import (
    AutoDemoDecisionRecord,
    AutoDemoDecisionState,
    SqliteAutoDemoDecisionStore,
    build_decision_id,
    should_skip_existing,
)
from exness_bot.execution.auto_demo.hot_read import hot_read_safety_settings
from exness_bot.execution.auto_demo.risk_gates import evaluate_auto_demo_risk_gates
from exness_bot.execution.integration.service import (
    CandidateExecutionContext,
    CandidateExecutionService,
)
from exness_bot.execution.result import OrchestrationOutcome
from exness_bot.market_analysis.contract.identity import MTF_STRATEGY_ID
from exness_bot.market_analysis.contract.models import ExecutionCandidate
from exness_bot.paper_execution.contract import IntentLifecycle
from exness_bot.risk.models import RiskState

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ClosedM15Observation:
    symbol: str
    timeframe: str
    closed_at: datetime


@dataclass(frozen=True)
class AutoDemoCandidateBundle:
    candidate: ExecutionCandidate | None
    context: CandidateExecutionContext
    blocked_reasons: tuple[str, ...] = ()
    signal: str | None = None


ObserveClosedM15 = Callable[[], ClosedM15Observation | None]
BuildCandidateBundle = Callable[[ClosedM15Observation], AutoDemoCandidateBundle]
AccountProvider = Callable[[], AccountInfo | None]
PositionsProvider = Callable[[], list[Position]]
RiskStateProvider = Callable[[AccountInfo | None], RiskState | None]
SettingsProvider = Callable[[], Settings]
SleepFn = Callable[[float], None]
ShouldStop = Callable[[], bool]


@dataclass
class AutonomousDemoExecutionLoop:
    """
    Observe new closed M15 → evaluate → ExecutionOrchestrator (when eligible).

    Does not own broker mechanics. Does not auto-start with API/dashboard.
    Operator runs: ``python -m exness_bot.execution.auto_demo run|once``.
    """

    settings: Settings
    decision_store: SqliteAutoDemoDecisionStore
    observe_closed_m15: ObserveClosedM15
    build_bundle: BuildCandidateBundle
    service: CandidateExecutionService
    account_provider: AccountProvider | None = None
    positions_provider: PositionsProvider | None = None
    risk_state_provider: RiskStateProvider | None = None
    settings_provider: SettingsProvider | None = None
    sleep_fn: SleepFn | None = None
    should_stop: ShouldStop | None = None
    poll_seconds: float = 5.0
    strategy_id: str = MTF_STRATEGY_ID

    def __post_init__(self) -> None:
        self.last_observation: ClosedM15Observation | None = None
        self.last_decision: AutoDemoDecisionRecord | None = None
        self.last_blocked_reason: str | None = None
        self.evaluations: int = 0
        self.submissions: int = 0

    def run_once(self) -> AutoDemoDecisionRecord | None:
        return self._evaluate_latest_closed()

    def run_forever(self) -> None:
        sleep = self.sleep_fn or __import__("time").sleep
        stop = self.should_stop or (lambda: False)
        while not stop():
            self._evaluate_latest_closed()
            if stop():
                break
            sleep(self.poll_seconds)

    def _live_settings(self) -> Settings:
        if self.settings_provider is not None:
            return self.settings_provider()
        return hot_read_safety_settings(self.settings)

    def _evaluate_latest_closed(self) -> AutoDemoDecisionRecord | None:
        observation = self.observe_closed_m15()
        if observation is None:
            return None
        self.last_observation = observation
        logger.info(
            "auto_demo_candle_observed",
            symbol=observation.symbol,
            timeframe=observation.timeframe,
            closed_at=observation.closed_at.isoformat(),
        )
        return self._process_decision(observation)

    def _process_decision(
        self, observation: ClosedM15Observation
    ) -> AutoDemoDecisionRecord:
        self.evaluations += 1
        decision_id = build_decision_id(
            symbol=observation.symbol,
            timeframe=observation.timeframe,
            closed_m15_timestamp=observation.closed_at,
            strategy_id=self.strategy_id,
        )
        existing = self.decision_store.get(decision_id)
        if existing is not None and should_skip_existing(existing.state):
            logger.info(
                "auto_demo_skipped_duplicate",
                decision_id=decision_id,
                state=existing.state,
            )
            self.last_decision = existing
            return existing

        closed_iso = (
            observation.closed_at.replace(tzinfo=UTC).isoformat()
            if observation.closed_at.tzinfo is None
            else observation.closed_at.astimezone(UTC).isoformat()
        )
        record = AutoDemoDecisionRecord(
            decision_id=decision_id,
            symbol=observation.symbol,
            timeframe=observation.timeframe,
            closed_m15_timestamp=closed_iso,
            strategy_id=self.strategy_id,
            state=AutoDemoDecisionState.OBSERVED.value,
        )
        try:
            record = self.decision_store.upsert(record)
        except Exception as exc:
            logger.error("auto_demo_persist_failed", stage="OBSERVED", error=str(exc))
            raise

        live = self._live_settings()
        if not live.auto_demo_execution_enabled:
            return self._persist_block(
                record,
                reasons=("AUTO_DEMO_EXECUTION_ENABLED=false",),
                eligibility="DISABLED",
            )
        if live.live_kill_switch:
            return self._persist_block(
                record,
                reasons=("LIVE_KILL_SWITCH=true",),
                eligibility="KILL_SWITCH",
            )

        record.state = AutoDemoDecisionState.EVALUATING.value
        record = self.decision_store.upsert(record)

        try:
            bundle = self.build_bundle(observation)
        except Exception as exc:
            logger.warning("auto_demo_candidate_build_error", error=str(exc))
            return self._persist_block(
                record,
                reasons=(f"CANDIDATE_BUILD_ERROR: {exc}",),
                eligibility="ERROR",
            )

        record.signal = bundle.signal
        if bundle.candidate is not None:
            record.candidate_id = bundle.candidate.candidate_id
            logger.info(
                "auto_demo_candidate_built",
                decision_id=decision_id,
                candidate_id=bundle.candidate.candidate_id,
                signal=bundle.signal,
            )

        if bundle.blocked_reasons or bundle.candidate is None:
            reasons = bundle.blocked_reasons or ("NO_ELIGIBLE_CANDIDATE",)
            return self._persist_block(
                record,
                reasons=reasons,
                eligibility="CANDIDATE_BLOCKED",
                signal=bundle.signal,
                candidate_id=None if bundle.candidate is None else bundle.candidate.candidate_id,
            )

        account = None if self.account_provider is None else self.account_provider()
        positions = [] if self.positions_provider is None else self.positions_provider()
        risk_state = None
        if self.risk_state_provider is not None:
            risk_state = self.risk_state_provider(account)

        quote = bundle.context.quote
        volume = bundle.candidate.proposed_volume
        risk = evaluate_auto_demo_risk_gates(
            live,
            account=account,
            quote=quote,
            open_positions=positions,
            requested_volume=volume,
            risk_state=risk_state,
        )
        record.risk_snapshot = risk.as_dict()
        record.spread = risk.spread_points
        record.requested_volume = volume
        if risk.reasons:
            return self._persist_block(
                record,
                reasons=risk.reasons,
                eligibility="RISK_BLOCKED",
                signal=bundle.signal,
                candidate_id=bundle.candidate.candidate_id,
            )

        pre = self.service.precheck(bundle.candidate, bundle.context)
        if not pre.allowed:
            return self._persist_block(
                record,
                reasons=pre.reasons,
                eligibility="PRECHECK_BLOCKED",
                signal=bundle.signal,
                candidate_id=bundle.candidate.candidate_id,
            )

        record.state = AutoDemoDecisionState.ELIGIBLE.value
        record.eligibility = "ELIGIBLE"
        record = self.decision_store.upsert(record)

        # Persist IN_FLIGHT BEFORE any broker side effect.
        record.state = AutoDemoDecisionState.IN_FLIGHT.value
        try:
            record = self.decision_store.upsert(record)
        except Exception as exc:
            logger.error(
                "auto_demo_persist_failed",
                stage="IN_FLIGHT",
                error=str(exc),
                note="NO order_send — fail closed before side effect",
            )
            raise

        logger.info("auto_demo_in_flight", decision_id=decision_id)

        # Re-check kill switch / enablement immediately before consume.
        live = self._live_settings()
        if live.live_kill_switch or not live.auto_demo_execution_enabled:
            reason = (
                "LIVE_KILL_SWITCH=true"
                if live.live_kill_switch
                else "AUTO_DEMO_EXECUTION_ENABLED=false"
            )
            return self._persist_block(
                record,
                reasons=(reason,),
                eligibility="HOT_READ_BLOCKED",
                signal=bundle.signal,
                candidate_id=bundle.candidate.candidate_id,
            )

        result = self.service.consume(bundle.candidate, bundle.context)
        return self._finalize(record, result)

    def _persist_block(
        self,
        record: AutoDemoDecisionRecord,
        *,
        reasons: tuple[str, ...] | list[str],
        eligibility: str,
        signal: str | None = None,
        candidate_id: str | None = None,
    ) -> AutoDemoDecisionRecord:
        reason_list = list(reasons)
        record.state = AutoDemoDecisionState.BLOCKED.value
        record.blocked_reasons = reason_list
        record.eligibility = eligibility
        if signal is not None:
            record.signal = signal
        if candidate_id is not None:
            record.candidate_id = candidate_id
        record = self.decision_store.upsert(record)
        self.last_decision = record
        self.last_blocked_reason = "; ".join(reason_list) if reason_list else None
        logger.info(
            "auto_demo_blocked",
            decision_id=record.decision_id,
            eligibility=eligibility,
            reasons=reason_list,
        )
        return record

    def _finalize(
        self,
        record: AutoDemoDecisionRecord,
        result: Any,
    ) -> AutoDemoDecisionRecord:
        orch = result.orchestration
        if orch is None:
            record.state = AutoDemoDecisionState.BLOCKED.value
            record.blocked_reasons = list(result.reasons or ("ORCHESTRATION_MISSING",))
            record.eligibility = "ORCHESTRATION_BLOCKED"
            record = self.decision_store.upsert(record)
            self.last_decision = record
            logger.info("auto_demo_blocked", decision_id=record.decision_id)
            return record

        record.execution_plan_id = orch.plan_id
        if orch.ack is not None:
            record.broker_request_id = getattr(orch.ack, "broker_order_id", None) or getattr(
                orch.ack, "order_ticket", None
            )
            record.broker_response = str(orch.ack.status)

        outcome = orch.outcome
        lifecycle = orch.lifecycle
        if (
            outcome == OrchestrationOutcome.UNKNOWN
            or lifecycle == IntentLifecycle.UNKNOWN
        ):
            record.state = AutoDemoDecisionState.UNKNOWN.value
            logger.warning(
                "auto_demo_unknown",
                decision_id=record.decision_id,
                note="NO automatic resubmit",
            )
        elif outcome == OrchestrationOutcome.FILLED or lifecycle == IntentLifecycle.FILLED:
            record.state = AutoDemoDecisionState.ACCEPTED.value
            self.submissions += 1
            logger.info("auto_demo_accepted", decision_id=record.decision_id)
        elif outcome in {
            OrchestrationOutcome.REJECTED,
            OrchestrationOutcome.BLOCKED,
            OrchestrationOutcome.DUPLICATE,
        }:
            record.state = AutoDemoDecisionState.REJECTED.value
            record.blocked_reasons = [orch.message]
            logger.info(
                "auto_demo_rejected",
                decision_id=record.decision_id,
                message=orch.message,
            )
        elif result.port_submit_count > 0:
            record.state = AutoDemoDecisionState.SUBMITTED.value
            self.submissions += 1
            logger.info("auto_demo_submitted", decision_id=record.decision_id)
        else:
            record.state = AutoDemoDecisionState.REJECTED.value
            record.blocked_reasons = [orch.message or str(outcome)]
            logger.info("auto_demo_rejected", decision_id=record.decision_id)

        record = self.decision_store.upsert(record)
        self.last_decision = record
        return record
