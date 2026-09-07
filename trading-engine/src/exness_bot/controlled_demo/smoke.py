"""Controlled DEMO smoke orchestrator — exactly one order, no strategy loop.

Canonical path (Phase 12.9):

    demo-execution-smoke
        → ExecutionOrchestrator
        → GatedMT5ExecutionPort
        → MT5Executor
        → OneShotExecutionTransport
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from exness_bot.backtest.config import BacktestConfig
from exness_bot.broker.mt5.execution_transport import MT5ExecutionTransport
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.enablement import (
    DemoEnablementResult,
    DemoPreflightContext,
    evaluate_demo_controlled_enablement,
)
from exness_bot.controlled_demo.evidence import BrokerSmokeEvidence, build_evidence, mask_login
from exness_bot.controlled_demo.identity import (
    DemoBrokerProbe,
    DemoIdentitySnapshot,
    DemoMarketSnapshot,
    resolve_broker_symbol_explicit,
)
from exness_bot.controlled_demo.intent_factory import (
    CONTROLLED_DEMO_TEST_VOLUME,
    build_controlled_demo_plan,
)
from exness_bot.controlled_demo.ledger import DemoSmokeLedger
from exness_bot.controlled_demo.oneshot_transport import OneShotExecutionTransport
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.enums import SignalDirection
from exness_bot.execution.guard import default_orchestration_guards
from exness_bot.execution.mt5.factory import build_gated_mt5_execution_port
from exness_bot.execution.mt5.gated_port import GatedMT5ExecutionPort
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.result import OrchestrationOutcome
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionQuery,
    UnavailableBrokerExecutionQuery,
)
from exness_bot.paper_execution.contract import (
    ExecutionAck,
    ExecutionIntent,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from exness_bot.paper_execution.models import PaperSnapshot
from exness_bot.paper_execution.state import FilePaperStateStore
from exness_bot.paper_execution.unknown_recovery import apply_reconcile_to_intent

logger = structlog.get_logger(__name__)

CONFIRM_PHRASE = "DEMO-EXECUTE"

EnablementFn = Callable[[DemoPreflightContext], DemoEnablementResult]


@dataclass(frozen=True)
class DemoSmokeResult:
    blocked: bool
    message: str
    enablement: DemoEnablementResult | None
    intent: ExecutionIntent | None = None
    ack: ExecutionAck | None = None
    lifecycle: IntentLifecycle | None = None
    transport_send_count: int = 0
    positions_before: tuple[dict[str, Any], ...] = ()
    positions_after: tuple[dict[str, Any], ...] = ()
    reconcile_status: str | None = None
    broker_symbol: str | None = None
    identity: DemoIdentitySnapshot | None = None
    market: DemoMarketSnapshot | None = None
    submitted: bool = False
    evidence: BrokerSmokeEvidence | None = None
    real_broker_submission: bool = False
    session_id: str | None = None
    used_gated_port: bool = False
    orchestration_outcome: str | None = None


@dataclass
class ControlledDemoSmoke:
    """
    One controlled DEMO submission boundary.

    Never starts a strategy loop. Never retries UNKNOWN.
    Uses GatedMT5ExecutionPort — does not duplicate safety gates.
    """

    settings: Settings
    probe: DemoBrokerProbe
    transport: MT5ExecutionTransport
    approval: OneShotApproval
    state_path: Path
    ledger_path: Path
    confirm_phrase: str | None = None
    execute: bool = False
    broker_query: BrokerExecutionQuery | None = None
    enablement_fn: EnablementFn = field(default=evaluate_demo_controlled_enablement)
    side: SignalDirection = SignalDirection.LONG
    real_broker_submission: bool = False
    session_id: str | None = None

    def run(self) -> DemoSmokeResult:
        ledger = DemoSmokeLedger(self.ledger_path)
        prior = ledger.load().submission_count
        session_id = self.session_id or f"demo-smoke-{uuid4().hex[:12]}"

        try:
            broker_symbol = resolve_broker_symbol_explicit(self.settings)
            identity = self.probe.fetch_account()
            market = self.probe.fetch_market(broker_symbol)
        except Exception as exc:
            return DemoSmokeResult(
                blocked=True,
                message=f"Read-only probe failed: {exc}",
                enablement=None,
            )

        if not identity.trade_allowed:
            return DemoSmokeResult(
                blocked=True,
                message="Account trade_allowed=false — BLOCK.",
                enablement=None,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
            )

        quote_fresh = market.freshness is QuoteFreshness.LIVE
        intents, store_error = _load_intents(self.state_path)

        context = DemoPreflightContext(
            settings=self.settings,
            symbol_info=market.symbol,
            intents=intents,
            intent_store_error=store_error,
            broker_query=self.broker_query or UnavailableBrokerExecutionQuery(),
            broker_login=identity.login,
            broker_server=identity.server,
            account_trade_mode=identity.trade_mode,
            trade_allowed=identity.trade_allowed,
            terminal_trade_allowed=identity.terminal_trade_allowed,
            quote_fresh=quote_fresh,
            quote_age_seconds=market.age_seconds,
            approval=self.approval,
            prior_submission_count=prior,
        )
        enablement = self.enablement_fn(context)
        if not enablement.allowed:
            return DemoSmokeResult(
                blocked=True,
                message=enablement.message,
                enablement=enablement,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
            )

        if not self.execute:
            return DemoSmokeResult(
                blocked=True,
                message=(
                    "Preflight PASSED but --execute not set. "
                    "No broker submission. Pass --execute --confirm DEMO-EXECUTE."
                ),
                enablement=enablement,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
            )

        if self.confirm_phrase != CONFIRM_PHRASE:
            return DemoSmokeResult(
                blocked=True,
                message=(
                    f"Confirmation required: --confirm {CONFIRM_PHRASE}. "
                    "Ambiguous/missing confirmation — NO SUBMISSION."
                ),
                enablement=enablement,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
            )

        _print_banner(
            identity=identity,
            market=market,
            broker_symbol=broker_symbol,
            side=self.side,
            volume=CONTROLLED_DEMO_TEST_VOLUME,
        )

        config = BacktestConfig.from_settings(self.settings)
        paper = PaperExecutor(
            _load_or_fresh_snapshot(self.state_path, config),
            config=config,
        )
        store = SnapshotIntentStore(paper, persist=lambda: _persist(self.state_path, paper))
        now = datetime.now(tz=UTC)

        try:
            plan = build_controlled_demo_plan(
                symbol=market.symbol,
                canonical_symbol=self.settings.symbol,
                timeframe=self.settings.timeframe,
                now=now,
                max_position_lots=self.settings.max_position_lots,
                side=self.side,
            )
        except ValueError as exc:
            return DemoSmokeResult(
                blocked=True,
                message=f"Controlled intent/risk blocked: {exc}",
                enablement=enablement,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
            )

        positions_before = self.probe.list_positions(broker_symbol)

        oneshot = OneShotExecutionTransport(self.transport)

        # Freeze prior intents BEFORE orchestrator creates IN_FLIGHT for this plan.
        # Gated recheck must see unresolved *prior* state only — not the intent
        # that ExecutionOrchestrator is currently committing.
        prior_intents = tuple(paper.snapshot.intents)

        def snapshot_provider() -> GatedExecutionSnapshot:
            return GatedExecutionSnapshot(
                account_trade_mode=identity.trade_mode,
                trade_allowed=identity.trade_allowed,
                terminal_trade_allowed=identity.terminal_trade_allowed,
                broker_login=identity.login,
                broker_server=identity.server,
                quote_fresh=quote_fresh,
                quote_age_seconds=market.age_seconds,
                approval=self.approval,
                prior_submission_count=ledger.load().submission_count,
                intents=prior_intents,
                intent_store_error=None,
            )

        gated: GatedMT5ExecutionPort = build_gated_mt5_execution_port(
            self.settings,
            transport=oneshot,
            snapshot_provider=snapshot_provider,
            wrap_oneshot=False,
        )

        orch = ExecutionOrchestrator(
            store=store,
            port=gated,
            clock=lambda: datetime.now(tz=UTC),
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: (
                f"demo-smoke-{p.plan_id.removeprefix('demo-smoke-plan-')}"
            ),
        )

        orch_result = orch.execute(plan, quote=market.symbol)
        intent = orch_result.intent
        ack = orch_result.ack
        lifecycle = orch_result.lifecycle

        # Durable one-shot: only after MT5Executor was reached (side-effect boundary).
        if gated.executor_submit_count > 0 and intent is not None:
            ledger.record_submission(
                intent_id=intent.intent_id,
                ack_status=(ack.status.value if ack is not None else "UNKNOWN"),
            )
            self.approval.try_consume(intent_id=intent.intent_id)

        submitted = gated.executor_submit_count > 0
        if not submitted:
            return DemoSmokeResult(
                blocked=True,
                message=(
                    orch_result.message
                    or "Gated path blocked before MT5Executor — NO SUBMISSION."
                ),
                enablement=gated.last_enablement or enablement,
                intent=intent,
                ack=ack,
                lifecycle=lifecycle,
                transport_send_count=oneshot.send_count,
                positions_before=positions_before,
                broker_symbol=broker_symbol,
                identity=identity,
                market=market,
                submitted=False,
                used_gated_port=True,
                orchestration_outcome=orch_result.outcome,
                session_id=session_id,
            )

        reconcile_status = None
        query = self.broker_query
        if query is not None and lifecycle is IntentLifecycle.UNKNOWN and intent is not None:
            record = store.get(intent.intent_id)
            if record is not None:
                result = query.find_execution(record)
                reconcile_status = result.status.value
                apply_reconcile_to_intent(
                    store, record, result, now=datetime.now(tz=UTC)
                )
                _persist(self.state_path, paper)
                updated = store.get(intent.intent_id)
                if updated is not None:
                    lifecycle = updated.lifecycle

        positions_after = self.probe.list_positions(broker_symbol)

        if (
            query is not None
            and reconcile_status is None
            and lifecycle is IntentLifecycle.FILLED
            and intent is not None
        ):
            record = store.get(intent.intent_id)
            if record is not None:
                qres = query.find_execution(record)
                reconcile_status = qres.status.value

        assert intent is not None
        assert ack is not None
        evidence = build_evidence(
            session_id=session_id,
            intent=intent,
            ack=ack,
            lifecycle=lifecycle.value if lifecycle else "UNKNOWN",
            masked_login=mask_login(identity.login),
            broker_server=identity.server,
            broker_symbol=broker_symbol,
            transport_send_count=oneshot.send_count,
            reconcile_status=reconcile_status,
            positions_before=positions_before,
            positions_after=positions_after,
            real_broker_submission=self.real_broker_submission,
            bid=market.symbol.bid,
            ask=market.symbol.ask,
            quote_age_seconds=market.age_seconds,
            quote_status="FRESH" if quote_fresh else "STALE",
            trade_mode=identity.trade_mode,
        )

        logger.info(
            "demo_smoke_complete",
            session_id=session_id,
            intent_id=intent.intent_id,
            ack=ack.status.value,
            lifecycle=lifecycle.value if lifecycle else None,
            transport_send_count=oneshot.send_count,
            position_match=evidence.position_match,
            real_broker_submission=self.real_broker_submission,
            submitted=True,
            gated_port=True,
            orchestration_outcome=orch_result.outcome,
        )
        if lifecycle is IntentLifecycle.UNKNOWN:
            logger.warning(
                "demo_smoke_unknown_procedure",
                message=(
                    "EXECUTION STATE: UNKNOWN | "
                    "ACTION REQUIRED: READ-ONLY BROKER RECONCILIATION | "
                    "AUTOMATIC RESUBMISSION: DISABLED"
                ),
            )
            print(
                "\n".join(
                    [
                        "",
                        "EXECUTION STATE: UNKNOWN",
                        "ACTION REQUIRED: READ-ONLY BROKER RECONCILIATION",
                        "AUTOMATIC RESUBMISSION: DISABLED",
                        "DO NOT RETRY. DO NOT RESUBMIT. DO NOT AUTO-CLOSE.",
                        "",
                    ]
                )
            )
        if evidence.open_positions_after:
            logger.warning(
                "demo_smoke_open_position",
                message=(
                    "Position remains open and requires separate explicit operator action."
                ),
                positions=list(evidence.open_positions_after),
            )
            print(
                "Position remains open and requires separate explicit operator action."
            )
            for pos in evidence.open_positions_after:
                print(
                    f"  ticket={pos.get('ticket')} symbol={pos.get('symbol')} "
                    f"volume={pos.get('volume')} price_open={pos.get('price_open')} "
                    f"sl={pos.get('sl')} tp={pos.get('tp')}"
                )

        blocked = orch_result.outcome not in {
            OrchestrationOutcome.FILLED,
            OrchestrationOutcome.REJECTED,
            OrchestrationOutcome.UNKNOWN,
        }
        return DemoSmokeResult(
            blocked=blocked,
            message="Controlled DEMO smoke completed (exactly one submission attempt).",
            enablement=gated.last_enablement or enablement,
            intent=intent,
            ack=ack,
            lifecycle=lifecycle,
            transport_send_count=oneshot.send_count,
            positions_before=positions_before,
            positions_after=positions_after,
            reconcile_status=reconcile_status,
            broker_symbol=broker_symbol,
            identity=identity,
            market=market,
            submitted=True,
            evidence=evidence,
            real_broker_submission=self.real_broker_submission,
            session_id=session_id,
            used_gated_port=True,
            orchestration_outcome=orch_result.outcome,
        )


def _load_intents(path: Path) -> tuple[tuple[IntentRecord, ...], str | None]:
    if not path.is_file():
        return (), None
    try:
        snap = FilePaperStateStore(path).load()
        return snap.intents, None
    except Exception as exc:
        return (), str(exc)


def _load_or_fresh_snapshot(path: Path, config: BacktestConfig) -> PaperSnapshot:
    del config
    if path.is_file():
        try:
            return FilePaperStateStore(path).load()
        except Exception:
            pass
    return PaperSnapshot.initial(10_000.0)


def _persist(path: Path, paper: PaperExecutor) -> None:
    FilePaperStateStore(path).save(paper.snapshot)


def _print_banner(
    *,
    identity: DemoIdentitySnapshot,
    market: DemoMarketSnapshot,
    broker_symbol: str,
    side: SignalDirection,
    volume: float,
) -> None:
    side_label = "BUY" if side is SignalDirection.LONG else "SELL"
    login_mask = str(identity.login)
    if len(login_mask) > 4:
        login_mask = f"***{login_mask[-4:]}"
    lines = [
        "",
        "==================================================",
        "CONTROLLED MT5 DEMO EXECUTION",
        "=============================",
        "",
        "ENVIRONMENT: DEMO",
        f"BROKER/SERVER: {identity.server}",
        f"ACCOUNT: {login_mask}",
        f"TRADE_MODE: {identity.trade_mode}",
        f"CURRENCY: {identity.currency}",
        f"SYMBOL: {broker_symbol}",
        f"SIDE: {side_label}",
        f"VOLUME: {volume} (explicit controlled DEMO test lot)",
        f"BID: {market.symbol.bid} ASK: {market.symbol.ask}",
        f"SPREAD_POINTS: {market.spread_points:.1f}",
        f"QUOTE_AGE_SECONDS: {market.age_seconds:.2f}",
        "",
        "PATH: ExecutionOrchestrator → GatedMT5ExecutionPort → MT5Executor",
        "KILL SWITCH: DISABLED FOR THIS ONE-SHOT TEST",
        "OPERATOR APPROVAL: REQUIRED (rechecked by GatedMT5ExecutionPort)",
        "",
        "MAX SUBMISSIONS: 1",
        "STRATEGY LOOP: DISABLED",
        "AUTOMATIC RETRY: DISABLED",
        "==================================================",
        "",
    ]
    print("\n".join(lines))
