"""Factory for autonomous DEMO CandidateExecutionService (no one-shot wrap)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.broker.mt5.execution_transport import MT5ExecutionTransport
from exness_bot.config.settings import Settings
from exness_bot.execution.auto_demo.enablement import evaluate_auto_demo_enablement
from exness_bot.execution.auto_demo.hot_read import hot_read_safety_settings
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
SettingsProvider = Callable[[], Settings]


def build_auto_demo_candidate_execution_service(
    settings: Settings,
    *,
    transport: MT5ExecutionTransport,
    snapshot_provider: SnapshotProvider,
    setup_store: SetupLifecycleStore | None = None,
    state_path: Path | None = None,
    clock: ClockFn | None = None,
    settings_provider: SettingsProvider | None = None,
) -> tuple[CandidateExecutionService, GatedMT5ExecutionPort, SnapshotIntentStore]:
    """
    CandidateExecutionService + GatedMT5 for autonomous DEMO.

    - Never wraps OneShotExecutionTransport (multi-candle loop).
    - Uses evaluate_auto_demo_enablement (not one-shot enablement).
    - Does NOT construct LiveMT5ExecutionTransport (caller injects Fake or Live).
    """
    if settings.allow_legacy_run:
        msg = "ALLOW_LEGACY_RUN=true — auto-demo factory refuses."
        raise RuntimeError(msg)

    clock_fn = clock or (lambda: datetime.now(tz=UTC))
    sp = settings_provider or (lambda: hot_read_safety_settings(settings))

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

    gated = build_gated_mt5_execution_port(
        settings,
        transport=transport,
        snapshot_provider=snapshot_provider,
        wrap_oneshot=False,
        enablement_evaluator=evaluate_auto_demo_enablement,
        settings_provider=sp,
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
        transport_label="GATED_MT5_AUTO_DEMO",
        require_demo_market_revalidate=True,
    )
    return service, gated, intent_store


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
