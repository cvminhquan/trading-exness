"""Phase 17.2 — candidate-demo-execution-smoke (preview default; human mutate only).

AI / Cursor agents MUST NEVER run with --execute --confirm DEMO-EXECUTE.
Automated tests MUST inject FakeMT5ExecutionTransport.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from exness_bot.backtest.config import BacktestConfig
from exness_bot.broker.mt5.execution_transport import MT5ExecutionTransport
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.enablement import (
    DemoEnablementResult,
    DemoPreflightContext,
    evaluate_demo_controlled_enablement,
)
from exness_bot.controlled_demo.evidence import mask_login
from exness_bot.controlled_demo.identity import (
    DemoBrokerProbe,
    DemoIdentitySnapshot,
    DemoMarketSnapshot,
    resolve_broker_symbol_explicit,
)
from exness_bot.controlled_demo.oneshot_transport import OneShotExecutionTransport
from exness_bot.controlled_demo.smoke import CONFIRM_PHRASE
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.data.models import DataSourceMode, ProviderConnectionStatus, ProviderSnapshot
from exness_bot.execution.integration.candidate_status import (
    CandidateBuildResult,
    build_candidate_status_from_mtf_provider,
)
from exness_bot.execution.integration.demo_factory import (
    build_controlled_demo_candidate_execution_service,
)
from exness_bot.execution.integration.demo_revalidate import (
    EXECUTED_TP_POLICY,
    executable_price,
    revalidate_candidate_market,
)
from exness_bot.execution.integration.factory import require_durable_setup_store
from exness_bot.execution.integration.models import (
    CandidateExecutionPrecheck,
    PrecheckVerdict,
)
from exness_bot.execution.integration.precheck import precheck_candidate_execution
from exness_bot.execution.integration.service import CandidateExecutionContext
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot
from exness_bot.market_analysis.contract.identity import MTF_STRATEGY_ID
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    ExecutionCandidate,
)
from exness_bot.market_analysis.contract.spread import (
    compute_raw_spread_points,
    normalize_spread_points,
)
from exness_bot.market_analysis.contract.store import SetupLifecycleStore
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionQuery,
    UnavailableBrokerExecutionQuery,
)
from exness_bot.paper_execution.contract import IntentLifecycle
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from exness_bot.paper_execution.models import PaperSnapshot
from exness_bot.paper_execution.state import FilePaperStateStore
from exness_bot.paper_execution.unknown_recovery import apply_reconcile_to_intent

AGENT_PROHIBITION = (
    "The AI/Cursor agent must NEVER run: "
    "candidate-demo-execution-smoke --execute --confirm DEMO-EXECUTE. "
    "Only a human operator may authorize broker mutation."
)


@dataclass(frozen=True)
class CandidateDemoSmokeResult:
    mode: str  # PREVIEW | EXECUTE
    blocked: bool
    message: str
    candidate_precheck: CandidateExecutionPrecheck | None = None
    enablement: DemoEnablementResult | None = None
    transport_send_count: int = 0
    executor_submit_count: int = 0
    lifecycle: IntentLifecycle | None = None
    reconcile_status: str | None = None
    real_broker_submission: bool = False
    identity: DemoIdentitySnapshot | None = None
    market: DemoMarketSnapshot | None = None
    broker_symbol: str | None = None
    proposed_volume: float | None = None
    tp_policy: str = EXECUTED_TP_POLICY
    session_id: str | None = None
    orchestration_outcome: str | None = None


@dataclass
class ControlledCandidateDemoSmoke:
    """Operator-triggered candidate → gated DEMO path."""

    settings: Settings
    probe: DemoBrokerProbe
    transport: MT5ExecutionTransport
    approval: OneShotApproval
    state_path: Path
    setup_store: SetupLifecycleStore
    candidate: ExecutionCandidate
    setup: CanonicalTradeSetup
    timeframe_status: dict[str, str]
    confirm_phrase: str | None = None
    execute: bool = False
    broker_query: BrokerExecutionQuery | None = None
    real_broker_submission: bool = False
    clock: Any | None = None

    def run(self) -> CandidateDemoSmokeResult:
        now = self.clock() if self.clock else datetime.now(tz=UTC)
        session_id = f"cand-demo-{uuid4().hex[:12]}"
        mode = "EXECUTE" if self.execute else "PREVIEW"

        try:
            broker_symbol = resolve_broker_symbol_explicit(self.settings)
            identity = self.probe.fetch_account()
            market = self.probe.fetch_market(broker_symbol)
        except Exception as exc:
            return CandidateDemoSmokeResult(
                mode=mode,
                blocked=True,
                message=f"Read-only probe failed: {exc}",
                session_id=session_id,
            )

        self.setup_store.upsert(self.setup)
        snapshot = ProviderSnapshot(
            connection_status=ProviderConnectionStatus.CONNECTED,
            data_source=DataSourceMode.MT5,
            account=identity.account,
            positions=(),
            updated_at=now,
        )
        ctx = CandidateExecutionContext(
            tick=market.tick,
            quote=market.symbol,
            snapshot=snapshot,
            timeframe_status=self.timeframe_status,
            now=now,
        )

        intent_store = _intent_store_for_path(self.state_path, self.settings)
        prior_intents = tuple(intent_store._executor.snapshot.intents)
        pre = _full_candidate_precheck(
            settings=self.settings,
            candidate=self.candidate,
            setup=self.setup,
            setup_store=self.setup_store,
            intent_store=intent_store,
            context=ctx,
            now=now,
        )

        quote_fresh = market.freshness is QuoteFreshness.LIVE
        enablement = evaluate_demo_controlled_enablement(
            DemoPreflightContext(
                settings=self.settings,
                symbol_info=market.symbol,
                intents=prior_intents,
                intent_store_error=None,
                broker_query=self.broker_query or UnavailableBrokerExecutionQuery(),
                broker_login=identity.login,
                broker_server=identity.server,
                account_trade_mode=identity.trade_mode,
                trade_allowed=identity.trade_allowed,
                terminal_trade_allowed=identity.terminal_trade_allowed,
                quote_fresh=quote_fresh,
                quote_age_seconds=market.age_seconds,
                approval=self.approval,
                prior_submission_count=0,
            )
        )

        _print_preview(
            identity=identity,
            market=market,
            broker_symbol=broker_symbol,
            candidate=self.candidate,
            setup=self.setup,
            precheck=pre,
            enablement=enablement,
            max_spread_points=int(self.settings.max_spread_points),
            risk_per_trade_pct=float(self.settings.risk_per_trade_pct),
        )

        if not self.execute:
            ready = pre.allowed and enablement.allowed
            return CandidateDemoSmokeResult(
                mode="PREVIEW",
                blocked=not ready,
                message=(
                    "CONTROLLED DEMO PREVIEW complete — REAL order_send: NO. "
                    + AGENT_PROHIBITION
                ),
                candidate_precheck=pre,
                enablement=enablement,
                transport_send_count=0,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
                proposed_volume=self.candidate.proposed_volume,
                session_id=session_id,
                real_broker_submission=False,
            )

        if not pre.allowed:
            return CandidateDemoSmokeResult(
                mode="EXECUTE",
                blocked=True,
                message="Candidate precheck BLOCKED — NO order_send.",
                candidate_precheck=pre,
                enablement=enablement,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
                proposed_volume=self.candidate.proposed_volume,
                session_id=session_id,
            )

        if not enablement.allowed:
            return CandidateDemoSmokeResult(
                mode="EXECUTE",
                blocked=True,
                message=f"DEMO gates BLOCKED — NO order_send. {enablement.message}",
                candidate_precheck=pre,
                enablement=enablement,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
                proposed_volume=self.candidate.proposed_volume,
                session_id=session_id,
            )

        if self.confirm_phrase != CONFIRM_PHRASE:
            return CandidateDemoSmokeResult(
                mode="EXECUTE",
                blocked=True,
                message=(
                    f"Confirmation required: --confirm {CONFIRM_PHRASE}. NO order_send."
                ),
                candidate_precheck=pre,
                enablement=enablement,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
                proposed_volume=self.candidate.proposed_volume,
                session_id=session_id,
            )

        if self.candidate.proposed_volume is None or self.candidate.proposed_volume <= 0:
            return CandidateDemoSmokeResult(
                mode="EXECUTE",
                blocked=True,
                message=(
                    "proposed_volume missing — "
                    "NO CONTROLLED_DEMO_TEST_VOLUME=0.01 override."
                ),
                candidate_precheck=pre,
                enablement=enablement,
                identity=identity,
                market=market,
                broker_symbol=broker_symbol,
                session_id=session_id,
            )

        _print_execute_banner(
            identity=identity,
            market=market,
            broker_symbol=broker_symbol,
            candidate=self.candidate,
        )

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
                prior_submission_count=0,
                intents=prior_intents,
                intent_store_error=None,
            )

        service, gated, consume_store, oneshot = (
            build_controlled_demo_candidate_execution_service(
                self.settings,
                transport=self.transport,
                snapshot_provider=snapshot_provider,
                setup_store=self.setup_store,
                state_path=self.state_path,
                wrap_oneshot=True,
                clock=lambda: now,
            )
        )
        self.setup_store.upsert(self.setup)
        consume = service.consume(self.candidate, ctx)

        send_count = (
            oneshot.send_count
            if isinstance(oneshot, OneShotExecutionTransport)
            else len(getattr(self.transport, "calls", []))
        )
        lifecycle = (
            None if consume.orchestration is None else consume.orchestration.lifecycle
        )
        outcome = (
            None
            if consume.orchestration is None
            else str(consume.orchestration.outcome)
        )

        reconcile_status = None
        query = self.broker_query
        if (
            query is not None
            and lifecycle is IntentLifecycle.UNKNOWN
            and consume.orchestration is not None
            and consume.orchestration.intent is not None
        ):
            record = consume_store.get(consume.orchestration.intent.intent_id)
            if record is not None:
                result = query.find_execution(record)
                reconcile_status = result.status.value
                apply_reconcile_to_intent(consume_store, record, result, now=now)
                updated = consume_store.get(record.intent_id)
                if updated is not None:
                    lifecycle = updated.lifecycle

        if lifecycle is IntentLifecycle.UNKNOWN:
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

        submitted = gated.executor_submit_count > 0
        return CandidateDemoSmokeResult(
            mode="EXECUTE",
            blocked=not submitted,
            message=(
                "Controlled candidate DEMO path completed."
                if submitted
                else (
                    consume.orchestration.message
                    if consume.orchestration
                    else "Blocked before submit"
                )
            ),
            candidate_precheck=pre,
            enablement=gated.last_enablement or enablement,
            transport_send_count=send_count,
            executor_submit_count=gated.executor_submit_count,
            lifecycle=lifecycle,
            reconcile_status=reconcile_status,
            real_broker_submission=self.real_broker_submission and submitted,
            identity=identity,
            market=market,
            broker_symbol=broker_symbol,
            proposed_volume=self.candidate.proposed_volume,
            session_id=session_id,
            orchestration_outcome=outcome,
        )


def run_candidate_demo_execution_smoke(
    *,
    symbol: str = "XAUUSD",
    execute: bool = False,
    confirm: str = "",
    settings: Settings | None = None,
    probe: DemoBrokerProbe | None = None,
    transport: MT5ExecutionTransport | None = None,
    candidate: ExecutionCandidate | None = None,
    setup: CanonicalTradeSetup | None = None,
    timeframe_status: dict[str, str] | None = None,
    broker_query: BrokerExecutionQuery | None = None,
    real_broker_submission: bool = False,
    state_path: Path | None = None,
    setup_store: SetupLifecycleStore | None = None,
    clock: Any | None = None,
) -> CandidateDemoSmokeResult:
    """Entry used by CLI and tests. Tests MUST supply Fake transport + probe."""
    from exness_bot.paper_execution.factory import ENGINE_ROOT

    cfg = settings or Settings()
    store = setup_store or require_durable_setup_store(cfg)
    path = state_path or (ENGINE_ROOT / ".candidate_demo_smoke_state.json")
    tf = timeframe_status or {
        "M15": "LIVE",
        "H1": "LIVE",
        "H4": "LIVE",
        "D1": "LIVE",
    }

    if candidate is None or setup is None or probe is None or transport is None:
        return _run_with_mt5_clients(
            symbol=symbol,
            execute=execute,
            confirm=confirm,
            settings=cfg,
            setup_store=store,
            state_path=path,
            timeframe_status=tf,
        )

    return ControlledCandidateDemoSmoke(
        settings=cfg,
        probe=probe,
        transport=transport,
        approval=OneShotApproval(active=cfg.live_demo_approval),
        state_path=path,
        setup_store=store,
        candidate=candidate,
        setup=setup,
        timeframe_status=tf,
        confirm_phrase=confirm,
        execute=execute,
        broker_query=broker_query,
        real_broker_submission=real_broker_submission,
        clock=clock,
    ).run()


def _run_with_mt5_clients(
    *,
    symbol: str,
    execute: bool,
    confirm: str,
    settings: Settings,
    setup_store: SetupLifecycleStore,
    state_path: Path,
    timeframe_status: dict[str, str],
) -> CandidateDemoSmokeResult:
    from contextlib import suppress

    from exness_bot.broker.mt5.connection_manager import ConnectionState, MT5ConnectionManager
    from exness_bot.broker.mt5.execution_query import ReadOnlyMt5BrokerExecutionQuery
    from exness_bot.broker.mt5.execution_transport import (
        FakeMT5ExecutionTransport,
        LiveMT5ExecutionTransport,
        MT5TransportResult,
        TransportOutcome,
    )
    from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient
    from exness_bot.broker.mt5.trading_client import MT5TradingClient
    from exness_bot.config.settings import TradingMode
    from exness_bot.controlled_demo.identity import ReadOnlyMt5DemoProbe
    from exness_bot.data.mt5_provider import MT5TradingDataProvider

    if settings.trading_mode == TradingMode.LIVE:
        return CandidateDemoSmokeResult(
            mode="EXECUTE" if execute else "PREVIEW",
            blocked=True,
            message="TRADING_MODE=live forbidden for controlled DEMO candidate smoke",
        )

    manager: MT5ConnectionManager | None = None
    try:
        if execute:
            trading = MT5TradingClient(settings)
            manager = MT5ConnectionManager(settings, client=trading)
            status = manager.connect()
            if status.state != ConnectionState.CONNECTED:
                return CandidateDemoSmokeResult(
                    mode="EXECUTE",
                    blocked=True,
                    message=f"MT5 unavailable: {status.message}",
                )
            probe_client: MT5ReadOnlyClient = trading
            transport: MT5ExecutionTransport = LiveMT5ExecutionTransport(client=trading)
            broker_query: BrokerExecutionQuery = ReadOnlyMt5BrokerExecutionQuery(trading)
            real = True
        else:
            readonly = MT5ReadOnlyClient(settings)
            manager = MT5ConnectionManager(settings, client=readonly)
            status = manager.connect()
            if status.state != ConnectionState.CONNECTED:
                return CandidateDemoSmokeResult(
                    mode="PREVIEW",
                    blocked=True,
                    message=f"MT5 unavailable: {status.message}",
                )
            probe_client = readonly
            transport = FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.REJECTED,
                    comment="preview_only_no_submit",
                )
            )
            broker_query = ReadOnlyMt5BrokerExecutionQuery(readonly)
            real = False

        # Reuse the same TradingDataProvider contract as Dashboard / Phase 16.2
        # (get_candles / get_tick / get_snapshot / get_symbol_info / resolve_broker_symbol).
        # Do NOT use a partial adapter missing get_candles.
        provider = MT5TradingDataProvider(settings, connection_manager=manager)
        built = build_candidate_status_from_mtf_provider(
            settings=settings,
            provider=provider,
            setup_store=setup_store,
            symbol=symbol,
        )
        if built.blocked_result is not None:
            return CandidateDemoSmokeResult(
                mode="PREVIEW" if not execute else "EXECUTE",
                blocked=True,
                message=built.blocked_result,
                real_broker_submission=False,
                transport_send_count=0,
            )

        assert built.status is not None
        status_c = built.status
        probe = ReadOnlyMt5DemoProbe(
            probe_client,
            stale_after_seconds=settings.live_data_stale_seconds,
        )
        # Preview diagnostics: always attempt market probe (read-only).
        market_diag: DemoMarketSnapshot | None = None
        identity_diag: DemoIdentitySnapshot | None = None
        broker_sym_diag: str | None = None
        try:
            broker_sym_diag = resolve_broker_symbol_explicit(settings)
            identity_diag = probe.fetch_account()
            market_diag = probe.fetch_market(broker_sym_diag)
        except Exception:
            market_diag = None

        if status_c.candidate is None or status_c.setup_id is None:
            setup_partial = (
                setup_store.get(status_c.setup_id) if status_c.setup_id else None
            )
            if not execute and market_diag is not None:
                _print_preview_diagnostics_block(
                    market=market_diag,
                    setup=setup_partial,
                    candidate=status_c.candidate,
                    setup_state=status_c.setup_state,
                    block_reasons=tuple(status_c.reasons),
                    max_spread_points=int(settings.max_spread_points),
                    risk_per_trade_pct=float(settings.risk_per_trade_pct),
                    equity=(
                        float(identity_diag.account.equity)
                        if identity_diag is not None
                        else None
                    ),
                )
            return CandidateDemoSmokeResult(
                mode="PREVIEW" if not execute else "EXECUTE",
                blocked=True,
                message=(
                    f"No eligible ExecutionCandidate for {symbol}. "
                    f"state={status_c.setup_state} reasons={status_c.reasons}"
                ),
                transport_send_count=0,
                real_broker_submission=False,
                identity=identity_diag,
                market=market_diag,
                broker_symbol=broker_sym_diag,
            )

        setup = setup_store.get(status_c.setup_id)
        if setup is None:
            if not execute and market_diag is not None:
                _print_preview_diagnostics_block(
                    market=market_diag,
                    setup=None,
                    candidate=status_c.candidate,
                    setup_state=status_c.setup_state,
                    block_reasons=("SETUP_MISSING_FROM_STORE", *status_c.reasons),
                    max_spread_points=int(settings.max_spread_points),
                    risk_per_trade_pct=float(settings.risk_per_trade_pct),
                    equity=(
                        float(identity_diag.account.equity)
                        if identity_diag is not None
                        else None
                    ),
                )
            return CandidateDemoSmokeResult(
                mode="PREVIEW" if not execute else "EXECUTE",
                blocked=True,
                message="Active setup missing from durable store.",
                transport_send_count=0,
                real_broker_submission=False,
                identity=identity_diag,
                market=market_diag,
                broker_symbol=broker_sym_diag,
            )

        tf_status = built.timeframe_status or timeframe_status
        return ControlledCandidateDemoSmoke(
            settings=settings,
            probe=probe,
            transport=transport,
            approval=OneShotApproval(active=settings.live_demo_approval),
            state_path=state_path,
            setup_store=setup_store,
            candidate=status_c.candidate,
            setup=setup,
            timeframe_status=tf_status,
            confirm_phrase=confirm,
            execute=execute,
            broker_query=broker_query,
            real_broker_submission=real,
        ).run()
    finally:
        if manager is not None:
            with suppress(Exception):
                manager.disconnect()


# Backward-compatible aliases (builder lives in candidate_status.py).
_CandidateBuildResult = CandidateBuildResult


def handle_candidate_demo_execution_smoke(
    *, symbol: str, execute: bool, confirm: str
) -> int:
    result = run_candidate_demo_execution_smoke(
        symbol=symbol,
        execute=execute,
        confirm=confirm,
    )
    print(f"RESULT: blocked={result.blocked} mode={result.mode}")
    print(f"MESSAGE: {result.message}")
    print(f"ORDER_SEND / transport send count: {result.transport_send_count}")
    print(f"REAL broker submission: {result.real_broker_submission}")
    if result.lifecycle is not None:
        print(f"EXECUTION STATE: {result.lifecycle.value}")
    if result.reconcile_status:
        print(f"RECONCILIATION: {result.reconcile_status}")
    if result.mode == "PREVIEW":
        return 0 if not result.blocked else 1
    return 0 if result.real_broker_submission or (
        not result.blocked and result.executor_submit_count > 0
    ) else 1


def _full_candidate_precheck(
    *,
    settings: Settings,
    candidate: ExecutionCandidate,
    setup: CanonicalTradeSetup,
    setup_store: SetupLifecycleStore,
    intent_store: SnapshotIntentStore,
    context: CandidateExecutionContext,
    now: datetime,
) -> CandidateExecutionPrecheck:
    allowed, reasons = precheck_candidate_execution(
        strategy_id=MTF_STRATEGY_ID,
        candidate=candidate,
        setup=setup,
        setup_store=setup_store,
        intent_store=intent_store,
        tick=context.tick,
        quote=context.quote,
        snapshot=context.snapshot,
        timeframe_status=context.timeframe_status,
        now=now,
        quote_max_age_seconds=float(settings.live_data_stale_seconds),
        account_max_age_seconds=float(settings.account_snapshot_max_age_seconds),
        max_spread_points=int(settings.max_spread_points),
    )
    if (
        allowed
        and context.tick is not None
        and context.quote is not None
    ):
        extra = revalidate_candidate_market(
            candidate=candidate,
            setup=setup,
            tick=context.tick,
            quote=context.quote,
            max_spread_points=int(settings.max_spread_points),
            now=now,
        )
        if extra:
            reasons = list(dict.fromkeys([*reasons, *extra]))
            allowed = False
    return CandidateExecutionPrecheck(
        allowed=allowed,
        verdict=PrecheckVerdict.READY if allowed else PrecheckVerdict.BLOCKED,
        reasons=tuple(reasons),
        candidate_id=candidate.candidate_id,
        setup_id=candidate.setup_id,
    )


def _intent_store_for_path(path: Path, settings: Settings) -> SnapshotIntentStore:
    config = BacktestConfig.from_settings(settings)
    if path.is_file():
        try:
            snap = FilePaperStateStore(path).load()
        except Exception:
            snap = PaperSnapshot.initial(10_000.0)
    else:
        snap = PaperSnapshot.initial(10_000.0)
    paper = PaperExecutor(snap, config=config)

    def persist() -> None:
        FilePaperStateStore(path).save(paper.snapshot)

    return SnapshotIntentStore(paper, persist=persist)


def format_preview_diagnostics(
    *,
    bid: float | None,
    ask: float | None,
    current_spread_points: float | None,
    max_spread_points: int,
    entry_zone_low: float | None,
    entry_zone_high: float | None,
    executable_price_value: float | None,
    proposed_volume: float | None,
    estimated_risk_usd: float | None,
    risk_budget_usd: float | None,
    broker_executable: bool | None,
    risk_acceptable: bool | None,
    setup_state: str | None,
    block_reasons: tuple[str, ...] | list[str],
    raw_spread_points: float | None = None,
    normalized_spread_points: float | None = None,
) -> list[str]:
    """
    Pure PREVIEW diagnostics formatter — does not mutate eligibility / gates.

    Side-effect free: returns lines only.
    """

    def _fmt(value: object) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, bool):
            return "YES" if value else "NO"
        if isinstance(value, float):
            return f"{value:.5g}"
        return str(value)

    def _fmt_spread(value: object) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, float):
            return repr(value)
        return str(value)

    reasons = list(block_reasons) if block_reasons else []
    return [
        "--- PREVIEW DIAGNOSTICS ---",
        f"BID: {_fmt(bid)}",
        f"ASK: {_fmt(ask)}",
        f"RAW_SPREAD_POINTS: {_fmt_spread(raw_spread_points)}",
        f"NORMALIZED_SPREAD_POINTS: {_fmt_spread(normalized_spread_points)}",
        f"CURRENT_SPREAD_POINTS: {_fmt(current_spread_points)}",
        f"MAX_SPREAD_POINTS: {max_spread_points}",
        f"ENTRY_ZONE_LOW: {_fmt(entry_zone_low)}",
        f"ENTRY_ZONE_HIGH: {_fmt(entry_zone_high)}",
        f"EXECUTABLE_PRICE: {_fmt(executable_price_value)}",
        f"PROPOSED_VOLUME: {_fmt(proposed_volume)}",
        f"ESTIMATED_RISK_USD: {_fmt(estimated_risk_usd)}",
        f"RISK_BUDGET_USD: {_fmt(risk_budget_usd)}",
        f"BROKER_EXECUTABLE: {_fmt(broker_executable)}",
        f"RISK_ACCEPTABLE: {_fmt(risk_acceptable)}",
        f"SETUP_STATE: {_fmt(setup_state)}",
        f"BLOCK_REASONS: {', '.join(reasons) if reasons else '—'}",
        "---------------------------",
    ]


def build_preview_diagnostics_lines(
    *,
    market: DemoMarketSnapshot,
    setup: CanonicalTradeSetup | None,
    candidate: ExecutionCandidate | None,
    setup_state: str | None,
    block_reasons: tuple[str, ...] | list[str],
    max_spread_points: int,
    risk_per_trade_pct: float,
    equity: float | None,
) -> list[str]:
    """Assemble diagnostics from read-only snapshots — no gate evaluation."""
    bid = float(market.symbol.bid)
    ask = float(market.symbol.ask)
    point = float(market.symbol.point) if market.symbol.point > 0 else 0.0
    raw_spread: float | None
    normalized: float | None
    if point > 0:
        raw_spread = compute_raw_spread_points(bid=bid, ask=ask, point=point)
        normalized = normalize_spread_points(raw_spread)
    else:
        raw_spread = float(market.spread_points)
        normalized = normalize_spread_points(raw_spread)

    no_trade_geometry = candidate is None and setup is None
    side = (
        candidate.side
        if candidate is not None
        else (setup.direction if setup is not None else "LONG")
    )
    exec_px = (
        None
        if no_trade_geometry or market.tick is None
        else executable_price(side=side, tick=market.tick)
    )

    risk_budget: float | None = None
    if setup is not None and "risk_budget_usd" in setup.risk_snapshot:
        raw = setup.risk_snapshot.get("risk_budget_usd")
        risk_budget = float(raw) if isinstance(raw, (int, float)) else None
    if risk_budget is None and equity is not None and risk_per_trade_pct > 0:
        risk_budget = float(equity) * float(risk_per_trade_pct) / 100.0
    if no_trade_geometry:
        risk_budget = None

    return format_preview_diagnostics(
        bid=bid,
        ask=ask,
        raw_spread_points=raw_spread,
        normalized_spread_points=normalized,
        current_spread_points=normalized,
        max_spread_points=max_spread_points,
        entry_zone_low=None if setup is None else setup.entry_zone_low,
        entry_zone_high=None if setup is None else setup.entry_zone_high,
        executable_price_value=exec_px,
        proposed_volume=None if candidate is None else candidate.proposed_volume,
        estimated_risk_usd=None if candidate is None else candidate.estimated_risk_usd,
        risk_budget_usd=risk_budget,
        broker_executable=None if candidate is None else candidate.broker_executable,
        risk_acceptable=None if candidate is None else candidate.risk_acceptable,
        setup_state=setup_state
        if setup_state is not None
        else (None if setup is None else setup.state.value),
        block_reasons=block_reasons,
    )


def _print_preview_diagnostics_block(
    *,
    market: DemoMarketSnapshot,
    setup: CanonicalTradeSetup | None,
    candidate: ExecutionCandidate | None,
    setup_state: str | None,
    block_reasons: tuple[str, ...] | list[str],
    max_spread_points: int,
    risk_per_trade_pct: float,
    equity: float | None,
) -> None:
    lines = build_preview_diagnostics_lines(
        market=market,
        setup=setup,
        candidate=candidate,
        setup_state=setup_state,
        block_reasons=block_reasons,
        max_spread_points=max_spread_points,
        risk_per_trade_pct=risk_per_trade_pct,
        equity=equity,
    )
    print("\n".join(["", *lines, ""]))


def _print_preview(
    *,
    identity: DemoIdentitySnapshot,
    market: DemoMarketSnapshot,
    broker_symbol: str,
    candidate: ExecutionCandidate,
    setup: CanonicalTradeSetup,
    precheck: CandidateExecutionPrecheck,
    enablement: DemoEnablementResult,
    max_spread_points: int,
    risk_per_trade_pct: float,
) -> None:
    block_reasons = tuple(precheck.reasons) if precheck.reasons else ()
    if not block_reasons and not candidate.eligibility.eligible:
        block_reasons = tuple(candidate.eligibility.blocking) or tuple(
            candidate.eligibility.reasons
        )
    diag = build_preview_diagnostics_lines(
        market=market,
        setup=setup,
        candidate=candidate,
        setup_state=setup.state.value,
        block_reasons=block_reasons,
        max_spread_points=max_spread_points,
        risk_per_trade_pct=risk_per_trade_pct,
        equity=float(identity.account.equity),
    )
    print(
        "\n".join(
            [
                "",
                "==================================================",
                "MODE:",
                "CONTROLLED DEMO PREVIEW",
                "",
                f"Strategy: {MTF_STRATEGY_ID}",
                f"Final signal / side: {candidate.side}",
                f"Setup: {setup.state.value}",
                f"Candidate: {'ELIGIBLE' if candidate.eligibility.eligible else 'BLOCKED'}",
                f"Precheck: {precheck.verdict.value}",
                f"Reasons: {', '.join(precheck.reasons) if precheck.reasons else '—'}",
                "",
                *diag,
                "",
                "Risk:",
                f"  estimated_risk_usd: {candidate.estimated_risk_usd}",
                f"  estimated_risk_pct: {candidate.estimated_risk_pct}",
                f"  proposed_volume: {candidate.proposed_volume}",
                f"  brokerExecutable: {candidate.broker_executable}",
                f"  riskAcceptable: {candidate.risk_acceptable}",
                "",
                "Market:",
                f"  bid={market.symbol.bid} ask={market.symbol.ask}",
                f"  spread_points={market.spread_points} quote_age={market.age_seconds}s",
                "",
                "Broker:",
                f"  server={identity.server} trade_mode={identity.trade_mode}",
                f"  login={mask_login(identity.login)}",
                f"  symbol={candidate.symbol} → {broker_symbol}",
                f"  volume min/step/max="
                f"{market.symbol.volume_min}/{market.symbol.volume_step}/"
                f"{market.symbol.volume_max}",
                "",
                "Execution gates:",
                f"  kill_switch={enablement.kill_switch_enabled}",
                f"  demo_approval={enablement.approval_active}",
                f"  enablement={'PASS' if enablement.allowed else 'BLOCKED'}",
                "",
                f"TP POLICY: {EXECUTED_TP_POLICY}",
                "REAL order_send: NO",
                "ORDER_SEND / transport send count: 0",
                "REAL broker submission: False",
                "",
                AGENT_PROHIBITION,
                "==================================================",
                "",
            ]
        )
    )


def _print_execute_banner(
    *,
    identity: DemoIdentitySnapshot,
    market: DemoMarketSnapshot,
    broker_symbol: str,
    candidate: ExecutionCandidate,
) -> None:
    tp1 = candidate.take_profits[0].price if candidate.take_profits else None
    print(
        "\n".join(
            [
                "",
                "==================================================",
                "CONTROLLED DEMO EXECUTION",
                "",
                f"ACCOUNT: {mask_login(identity.login)}",
                f"SERVER: {identity.server}",
                f"SYMBOL: {candidate.symbol} → {broker_symbol}",
                f"SIDE: {candidate.side}",
                f"VOLUME: {candidate.proposed_volume}",
                f"ENTRY REFERENCE: bid={market.symbol.bid} ask={market.symbol.ask}",
                f"SL: {candidate.stop_loss}",
                f"TP POLICY: {EXECUTED_TP_POLICY}",
                f"TP: {tp1}",
                "MAX SEND COUNT: 1",
                "==================================================",
                "",
            ]
        )
    )
