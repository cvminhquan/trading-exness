"""Controlled DEMO smoke orchestrator — exactly one order, no strategy loop."""

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
from exness_bot.broker.mt5.executor import MT5Executor
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
from exness_bot.controlled_demo.intent_factory import build_controlled_demo_intent
from exness_bot.controlled_demo.ledger import DemoSmokeLedger
from exness_bot.controlled_demo.oneshot_transport import OneShotExecutionTransport
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionQuery,
    UnavailableBrokerExecutionQuery,
)
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionAck,
    ExecutionIntent,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import (
    ExecutionEvidence,
    SnapshotIntentStore,
    UnknownReason,
)
from exness_bot.paper_execution.models import PaperSnapshot
from exness_bot.paper_execution.state import FilePaperStateStore
from exness_bot.paper_execution.unknown_recovery import apply_reconcile_to_intent
from exness_bot.risk.manager import RiskManager

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


@dataclass
class ControlledDemoSmoke:
    """
    One controlled DEMO submission boundary.

    Never starts a strategy loop. Never retries UNKNOWN.
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
        )

        config = BacktestConfig.from_settings(self.settings)
        paper = PaperExecutor(
            _load_or_fresh_snapshot(self.state_path, config),
            config=config,
        )
        store = SnapshotIntentStore(paper, persist=lambda: _persist(self.state_path, paper))
        now = datetime.now(tz=UTC)

        try:
            intent = build_controlled_demo_intent(
                symbol=market.symbol,
                canonical_symbol=self.settings.symbol,
                timeframe=self.settings.timeframe,
                now=now,
                account=identity.account,
                risk=RiskManager(self.settings),
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

        if not self.approval.try_consume(intent_id=intent.intent_id):
            return DemoSmokeResult(
                blocked=True,
                message="Operator approval consume failed — NO SUBMISSION.",
                enablement=enablement,
                intent=intent,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
            )

        positions_before = self.probe.list_positions(broker_symbol)
        created = store.create_intent(intent, now=now)
        if not created.created:
            return DemoSmokeResult(
                blocked=True,
                message="Idempotency collision — NO SUBMISSION.",
                enablement=enablement,
                intent=intent,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
            )
        # IN_FLIGHT BEFORE transport.send
        store.mark_in_flight(intent.intent_id, now=datetime.now(tz=UTC))
        _persist(self.state_path, paper)

        oneshot = OneShotExecutionTransport(self.transport)

        def _demo_enablement(_ctx: Any) -> Any:
            # Executor gate: re-check kill switch / env; approval already consumed —
            # pass a synthetic allowed path only when kill switch still off.
            from exness_bot.config.live_enablement import (
                LiveEnablementResult,
                LiveReadinessStatus,
            )

            # Use demo enablement result: after consume, DEMO_APPROVAL gate would fail.
            # Executor must not re-evaluate approval; smoke already consumed it.
            # Provide a thin LiveEnablementResult that mirrors remaining safety.
            if self.settings.live_kill_switch or self.settings.allow_legacy_run:
                return LiveEnablementResult(
                    allowed=False,
                    configuration_preflight_ready=False,
                    execution_capability=True,
                    readiness_status=LiveReadinessStatus.BLOCKED,
                    gates=(),
                    blocking_reasons=("post-approval safety recheck failed",),
                    evaluated_at=datetime.now(tz=UTC),
                    message="Blocked on recheck",
                )
            if self.settings.trading_env.strip().lower() != "demo":
                return LiveEnablementResult(
                    allowed=False,
                    configuration_preflight_ready=False,
                    execution_capability=True,
                    readiness_status=LiveReadinessStatus.BLOCKED,
                    gates=(),
                    blocking_reasons=("TRADING_ENV no longer demo",),
                    evaluated_at=datetime.now(tz=UTC),
                    message="Blocked",
                )
            return LiveEnablementResult(
                allowed=True,
                configuration_preflight_ready=True,
                execution_capability=True,
                readiness_status=LiveReadinessStatus.PREFLIGHT_READY,
                gates=(),
                blocking_reasons=(),
                evaluated_at=datetime.now(tz=UTC),
                message="Demo one-shot authorized",
                mt5_executor_implemented=True,
            )

        executor = MT5Executor(
            transport=oneshot,
            settings=self.settings,
            require_enablement=True,
            enablement_evaluator=_demo_enablement,
        )
        # Quote SymbolInfo may use broker name; keep domain validations working
        quote = market.symbol
        ack = executor.submit(intent, quote=quote)
        ledger.record_submission(intent_id=intent.intent_id, ack_status=ack.status.value)

        lifecycle = _finalize_intent(store, intent.intent_id, ack)
        _persist(self.state_path, paper)

        reconcile_status = None
        query = self.broker_query
        if query is not None and lifecycle is IntentLifecycle.UNKNOWN:
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

        # Optional read-only intent query even for FILLED (evidence enrichment)
        if (
            query is not None
            and reconcile_status is None
            and lifecycle is IntentLifecycle.FILLED
        ):
            record = store.get(intent.intent_id)
            if record is not None:
                qres = query.find_execution(record)
                reconcile_status = qres.status.value

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

        return DemoSmokeResult(
            blocked=False,
            message="Controlled DEMO smoke completed (exactly one submission attempt).",
            enablement=enablement,
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
        )


def _finalize_intent(
    store: SnapshotIntentStore,
    intent_id: str,
    ack: ExecutionAck,
) -> IntentLifecycle:
    now = datetime.now(tz=UTC)
    evidence = ExecutionEvidence(
        fill_price=ack.fill_price,
        broker_order_id=ack.broker_order_id,
        broker_deal_id=ack.broker_position_id,
        reason=ack.reason,
        ack_status=ack.status.value,
    )
    if ack.status is AckStatus.FILLED:
        store.mark_filled(intent_id, evidence, now=now)
        return IntentLifecycle.FILLED
    if ack.status is AckStatus.REJECTED:
        store.mark_rejected(intent_id, evidence, now=now)
        return IntentLifecycle.REJECTED
    if ack.status is AckStatus.TIMEOUT:
        reason = UnknownReason.ACK_TIMEOUT
    else:
        reason = UnknownReason.ACK_UNKNOWN
    store.mark_unknown(intent_id, reason, now=now, detail=ack.reason)
    return IntentLifecycle.UNKNOWN


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
        f"VOLUME: {market.symbol.volume_min} (min lot — finalized after risk)",
        f"BID: {market.symbol.bid} ASK: {market.symbol.ask}",
        f"SPREAD_POINTS: {market.spread_points:.1f}",
        f"QUOTE_AGE_SECONDS: {market.age_seconds:.2f}",
        "",
        "KILL SWITCH: DISABLED FOR THIS ONE-SHOT TEST",
        "OPERATOR APPROVAL: REQUIRED / CONSUMING",
        "",
        "MAX SUBMISSIONS: 1",
        "STRATEGY LOOP: DISABLED",
        "AUTOMATIC RETRY: DISABLED",
        "==================================================",
        "",
    ]
    print("\n".join(lines))
