"""Phase 17.1 Fake-only factory — never constructs LiveMT5 / gated MT5 ports."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.settings import Settings
from exness_bot.execution.guard import default_orchestration_guards
from exness_bot.execution.integration.service import CandidateExecutionService
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.spy import SpyExecutionPort
from exness_bot.market_analysis.contract.store import (
    SetupLifecycleStore,
    SqliteSetupLifecycleStore,
)
from exness_bot.paper_execution.contract import AckStatus
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from exness_bot.paper_execution.models import PaperSnapshot
from exness_bot.paper_execution.state import FilePaperStateStore
from exness_bot.persistence.sqlite_repository import parse_sqlite_path

ClockFn = Callable[[], datetime]


class DurableSetupStoreUnavailableError(RuntimeError):
    """Raised when Phase 17.1 cannot open a durable setup lifecycle store."""


def require_durable_setup_store(settings: Settings) -> SqliteSetupLifecycleStore:
    """Fail closed — in-memory fallback is not allowed for execution consume."""
    url = str(settings.database_url)
    if not url.startswith("sqlite"):
        raise DurableSetupStoreUnavailableError(
            "DURABLE_SETUP_STORE_UNAVAILABLE: DATABASE_URL must be sqlite for Phase 17.1"
        )
    try:
        path = parse_sqlite_path(url)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return SqliteSetupLifecycleStore(url)
    except Exception as exc:
        raise DurableSetupStoreUnavailableError(
            f"DURABLE_SETUP_STORE_UNAVAILABLE: {exc}"
        ) from exc


def build_fake_candidate_execution_service(
    settings: Settings,
    *,
    setup_store: SetupLifecycleStore | None = None,
    state_dir: Path | None = None,
    ack: AckStatus = AckStatus.FILLED,
    fill_price: float | None = None,
    clock: ClockFn | None = None,
) -> tuple[CandidateExecutionService, SpyExecutionPort, SnapshotIntentStore]:
    """
    Wire CandidateExecutionService to SpyExecutionPort only.

    Explicitly does NOT call build_gated_mt5_execution_port or LiveMT5*.
    """
    clock_fn = clock or (lambda: datetime.now(tz=UTC))
    durable = setup_store or require_durable_setup_store(settings)
    if not isinstance(durable, SqliteSetupLifecycleStore):
        raise DurableSetupStoreUnavailableError("DURABLE_SETUP_STORE_UNAVAILABLE")

    config = BacktestConfig.from_settings(settings)
    paper = PaperExecutor(PaperSnapshot.initial(10_000.0), config=config)
    if state_dir is not None:
        state_dir.mkdir(parents=True, exist_ok=True)
        store_path = state_dir / "paper_state.json"

        def persist() -> None:
            FilePaperStateStore(store_path).save(paper.snapshot)

    else:

        def persist() -> None:
            return None

    intent_store = SnapshotIntentStore(paper, persist=persist)
    port = SpyExecutionPort(responses=ack, fill_price=fill_price)
    orch = ExecutionOrchestrator(
        store=intent_store,
        port=port,
        clock=clock_fn,
        guard=default_orchestration_guards(intent_store),
    )
    service = CandidateExecutionService(
        settings,
        setup_store=durable,
        intent_store=intent_store,
        orchestrator=orch,
        port=port,
        clock=clock_fn,
    )
    return service, port, intent_store
