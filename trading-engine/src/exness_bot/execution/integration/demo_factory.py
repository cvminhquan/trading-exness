"""Phase 17.2 controlled DEMO factory — GatedMT5 only for explicit CLI path.

Does NOT construct LiveMT5ExecutionTransport.
Caller must inject Fake (tests) or Live (human CLI) transport.
Never wired into default build_execution_service / strategy loop.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.broker.mt5.execution_transport import MT5ExecutionTransport
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.oneshot_transport import OneShotExecutionTransport
from exness_bot.execution.guard import default_orchestration_guards
from exness_bot.execution.integration.factory import (
    DurableSetupStoreUnavailableError,
    require_durable_setup_store,
)
from exness_bot.execution.integration.service import CandidateExecutionService
from exness_bot.execution.mt5.factory import build_gated_mt5_execution_port
from exness_bot.execution.mt5.gated_port import GatedMT5ExecutionPort
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.market_analysis.contract.store import (
    SetupLifecycleStore,
    SqliteSetupLifecycleStore,
)
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from exness_bot.paper_execution.models import PaperSnapshot
from exness_bot.paper_execution.state import FilePaperStateStore

ClockFn = Callable[[], datetime]
SnapshotProvider = Callable[[], GatedExecutionSnapshot]


def build_controlled_demo_candidate_execution_service(
    settings: Settings,
    *,
    transport: MT5ExecutionTransport,
    snapshot_provider: SnapshotProvider,
    setup_store: SetupLifecycleStore | None = None,
    state_path: Path | None = None,
    wrap_oneshot: bool = True,
    clock: ClockFn | None = None,
) -> tuple[
    CandidateExecutionService,
    GatedMT5ExecutionPort,
    SnapshotIntentStore,
    OneShotExecutionTransport | MT5ExecutionTransport,
]:
    """
    CandidateExecutionService + GatedMT5ExecutionPort for controlled DEMO.

    Safe defaults: caller supplies transport. This factory never imports LiveMT5.
    """
    if settings.allow_legacy_run:
        msg = "ALLOW_LEGACY_RUN=true — controlled DEMO candidate factory refuses."
        raise RuntimeError(msg)

    clock_fn = clock or (lambda: datetime.now(tz=UTC))
    durable = setup_store or require_durable_setup_store(settings)
    if not isinstance(durable, SqliteSetupLifecycleStore):
        raise DurableSetupStoreUnavailableError("DURABLE_SETUP_STORE_UNAVAILABLE")

    config = BacktestConfig.from_settings(settings)
    paper = PaperExecutor(
        _load_or_fresh_snapshot(state_path, config),
        config=config,
    )

    def persist() -> None:
        if state_path is not None:
            FilePaperStateStore(state_path).save(paper.snapshot)

    intent_store = SnapshotIntentStore(paper, persist=persist)

    oneshot: OneShotExecutionTransport | MT5ExecutionTransport
    if wrap_oneshot:
        oneshot = OneShotExecutionTransport(transport)
        gated = build_gated_mt5_execution_port(
            settings,
            transport=oneshot,
            snapshot_provider=snapshot_provider,
            wrap_oneshot=False,
        )
    else:
        oneshot = transport
        gated = build_gated_mt5_execution_port(
            settings,
            transport=transport,
            snapshot_provider=snapshot_provider,
            wrap_oneshot=False,
        )

    orch = ExecutionOrchestrator(
        store=intent_store,
        port=gated,
        clock=clock_fn,
        guard=default_orchestration_guards(intent_store),
    )
    service = CandidateExecutionService(
        settings,
        setup_store=durable,
        intent_store=intent_store,
        orchestrator=orch,
        port=gated,
        clock=clock_fn,
        transport_label="GATED_MT5_DEMO",
        require_demo_market_revalidate=True,
    )
    return service, gated, intent_store, oneshot


def _load_or_fresh_snapshot(
    path: Path | None, config: BacktestConfig
) -> PaperSnapshot:
    del config
    if path is None or not path.is_file():
        return PaperSnapshot.initial(10_000.0)
    try:
        return FilePaperStateStore(path).load()
    except Exception:
        return PaperSnapshot.initial(10_000.0)
