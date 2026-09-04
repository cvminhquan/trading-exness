"""Phase 12.6 — ExecutionOrchestrator hardening. Fake/Spy ports only — no MT5."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalDirection
from exness_bot.execution.eligibility import ExecutionEventKind
from exness_bot.execution.guard import StaticExecutionGuard, default_orchestration_guards
from exness_bot.execution.idempotency import build_execution_idempotency_key
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.plan import ExecutionPlan
from exness_bot.execution.result import OrchestrationOutcome
from exness_bot.execution.spy import SpyExecutionPort
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionIntent,
    IntentLifecycle,
)
from exness_bot.paper_execution.errors import InvalidLifecycleTransition
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import (
    CreateIntentResult,
    ExecutionEvidence,
    SnapshotIntentStore,
    UnknownReason,
    assert_transition_allowed,
)
from exness_bot.paper_execution.models import PaperSnapshot
from exness_bot.paper_execution.state import FilePaperStateStore
from tests.fixtures.risk_data import make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
ORCH_PKG = SRC / "execution"


def _at() -> datetime:
    return datetime(2026, 9, 4, 10, 0, tzinfo=UTC)


def _plan(
    *,
    signal_id: str = "sig-1",
    event_kind: ExecutionEventKind = ExecutionEventKind.LIVE,
    side: SignalDirection = SignalDirection.LONG,
    ts: datetime | None = None,
) -> ExecutionPlan:
    stamp = ts or _at()
    return ExecutionPlan(
        plan_id=f"plan-{signal_id}",
        signal_id=signal_id,
        strategy_id="ema_rsi_atr_v1",
        symbol="XAUUSD",
        timeframe="M15",
        side=side,
        requested_volume=0.01,
        stop_loss=2340.0,
        take_profit=2370.0,
        signal_timestamp=stamp,
        decision_timestamp=stamp,
        reason="test",
        event_kind=event_kind,
    )


def _store(tmp_path: Path | None = None) -> SnapshotIntentStore:
    paper = PaperExecutor(
        PaperSnapshot.initial(10_000.0),
        config=BacktestConfig.from_settings(Settings(_env_file=None)),
    )
    persist = (lambda: None) if tmp_path is None else (
        lambda: FilePaperStateStore(tmp_path / "state.json").save(paper.snapshot)
    )
    if tmp_path is not None:
        FilePaperStateStore(tmp_path / "state.json").save(paper.snapshot)
    return SnapshotIntentStore(paper, persist=persist)


class ControllableStore:
    """Wrap SnapshotIntentStore with injectable failures."""

    def __init__(self, inner: SnapshotIntentStore) -> None:
        self._inner = inner
        self.fail_create = False
        self.fail_in_flight = False
        self.fail_filled = False
        self.fail_unknown = False
        self.in_flight_before_submit: IntentLifecycle | None = None

    def create_intent(self, intent: ExecutionIntent, *, now: datetime) -> CreateIntentResult:
        if self.fail_create:
            raise RuntimeError("inject_create_failure")
        return self._inner.create_intent(intent, now=now)

    def mark_in_flight(self, intent_id: str, *, now: datetime) -> Any:
        if self.fail_in_flight:
            raise RuntimeError("inject_in_flight_failure")
        record = self._inner.mark_in_flight(intent_id, now=now)
        self.in_flight_before_submit = record.lifecycle
        return record

    def mark_filled(self, intent_id: str, evidence: ExecutionEvidence, *, now: datetime) -> Any:
        if self.fail_filled:
            raise RuntimeError("inject_filled_failure")
        return self._inner.mark_filled(intent_id, evidence, now=now)

    def mark_rejected(self, intent_id: str, evidence: ExecutionEvidence, *, now: datetime) -> Any:
        return self._inner.mark_rejected(intent_id, evidence, now=now)

    def mark_unknown(
        self,
        intent_id: str,
        reason: UnknownReason,
        *,
        now: datetime,
        detail: str | None = None,
    ) -> Any:
        if self.fail_unknown:
            raise RuntimeError("inject_unknown_failure")
        return self._inner.mark_unknown(intent_id, reason, now=now, detail=detail)

    def get(self, intent_id: str) -> Any:
        return self._inner.get(intent_id)

    def get_by_key(self, idempotency_key: str) -> Any:
        return self._inner.get_by_key(idempotency_key)

    def list_blocking(self) -> Any:
        return self._inner.list_blocking()

    def list_unknown(self) -> Any:
        return self._inner.list_unknown()

    def list_in_flight(self) -> Any:
        return self._inner.list_in_flight()

    def recover_in_flight_to_unknown(self, *, now: datetime) -> Any:
        return self._inner.recover_in_flight_to_unknown(now=now)

    def reconcile_filled(
        self, intent_id: str, evidence: ExecutionEvidence, *, now: datetime
    ) -> Any:
        return self._inner.reconcile_filled(intent_id, evidence, now=now)

    def reconcile_rejected(
        self, intent_id: str, evidence: ExecutionEvidence, *, now: datetime
    ) -> Any:
        return self._inner.reconcile_rejected(intent_id, evidence, now=now)


def _orch(
    store: Any,
    port: SpyExecutionPort,
    *,
    guard: Any = None,
) -> ExecutionOrchestrator:
    return ExecutionOrchestrator(
        store=store,
        port=port,
        clock=_at,
        guard=guard if guard is not None else default_orchestration_guards(store),
        intent_id_factory=lambda plan: f"intent-{plan.signal_id}",
    )


class TestOrchestratorHappyPath:
    def test_valid_plan_exactly_one_call(self) -> None:
        store = ControllableStore(_store())
        port = SpyExecutionPort(responses=AckStatus.FILLED)
        result = _orch(store, port).execute(_plan(), quote=make_xauusd_symbol())
        assert result.outcome == OrchestrationOutcome.FILLED
        assert len(port.calls) == 1
        assert result.lifecycle is IntentLifecycle.FILLED
        assert store.in_flight_before_submit is IntentLifecycle.IN_FLIGHT

    def test_duplicate_plan_zero_second_calls(self) -> None:
        store = ControllableStore(_store())
        port = SpyExecutionPort(responses=AckStatus.FILLED)
        orch = _orch(store, port)
        first = orch.execute(_plan(), quote=make_xauusd_symbol())
        second = orch.execute(_plan(), quote=make_xauusd_symbol())
        assert first.port_calls == 1
        assert second.port_calls == 0
        assert len(port.calls) == 1
        assert second.outcome == OrchestrationOutcome.DUPLICATE

    def test_rejected_persisted(self) -> None:
        store = ControllableStore(_store())
        port = SpyExecutionPort(responses=AckStatus.REJECTED)
        result = _orch(store, port).execute(_plan(), quote=make_xauusd_symbol())
        assert result.outcome == OrchestrationOutcome.REJECTED
        assert result.lifecycle is IntentLifecycle.REJECTED
        assert len(port.calls) == 1


class TestIdempotencyAndRestart:
    def test_deterministic_key(self) -> None:
        a = build_execution_idempotency_key(
            strategy_id="s",
            symbol="XAUUSD",
            timeframe="M15",
            closed_candle_timestamp=_at(),
            signal_id="sig",
            side=SignalDirection.LONG,
        )
        b = build_execution_idempotency_key(
            strategy_id="s",
            symbol="XAUUSD",
            timeframe="M15",
            closed_candle_timestamp=_at(),
            signal_id="sig",
            side=SignalDirection.LONG,
        )
        assert a == b

    def test_same_signal_after_restart_no_second_call(self, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(Settings(_env_file=None)),
        )
        store1 = SnapshotIntentStore(
            paper, persist=lambda: FilePaperStateStore(state).save(paper.snapshot)
        )
        port = SpyExecutionPort(responses=AckStatus.FILLED)
        _orch(store1, port).execute(_plan(), quote=make_xauusd_symbol())
        assert len(port.calls) == 1

        paper2 = PaperExecutor(
            FilePaperStateStore(state).load(),
            config=BacktestConfig.from_settings(Settings(_env_file=None)),
        )
        store2 = SnapshotIntentStore(
            paper2, persist=lambda: FilePaperStateStore(state).save(paper2.snapshot)
        )
        spy = SpyExecutionPort(responses=AckStatus.FILLED)
        result = _orch(store2, spy).execute(_plan(), quote=make_xauusd_symbol())
        assert spy.calls == []
        assert result.outcome == OrchestrationOutcome.DUPLICATE

    def test_lifecycles_survive_restart(self, tmp_path: Path) -> None:
        for status, lifecycle in (
            (AckStatus.FILLED, IntentLifecycle.FILLED),
            (AckStatus.REJECTED, IntentLifecycle.REJECTED),
            (AckStatus.UNKNOWN, IntentLifecycle.UNKNOWN),
        ):
            state = tmp_path / f"{lifecycle.value}.json"
            paper = PaperExecutor(
                PaperSnapshot.initial(10_000.0),
                config=BacktestConfig.from_settings(Settings(_env_file=None)),
            )
            store = SnapshotIntentStore(
                paper, persist=lambda p=paper, s=state: FilePaperStateStore(s).save(p.snapshot)
            )
            port = SpyExecutionPort(responses=status)
            plan = _plan(signal_id=f"sig-{lifecycle.value}")
            result = _orch(store, port).execute(plan, quote=make_xauusd_symbol())
            assert result.lifecycle is lifecycle
            reloaded = FilePaperStateStore(state).load()
            row = next(i for i in reloaded.intents if i.intent_id == result.intent.intent_id)  # type: ignore[union-attr]
            assert row.lifecycle is lifecycle
            assert row.idempotency_key == result.idempotency_key

    def test_in_flight_crash_recovers_to_unknown_no_resubmit(self, tmp_path: Path) -> None:
        state = tmp_path / "inflight.json"
        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(Settings(_env_file=None)),
        )
        store = SnapshotIntentStore(
            paper, persist=lambda: FilePaperStateStore(state).save(paper.snapshot)
        )
        intent = ExecutionIntent(
            intent_id="stuck",
            idempotency_key=build_execution_idempotency_key(
                strategy_id="ema_rsi_atr_v1",
                symbol="XAUUSD",
                timeframe="M15",
                closed_candle_timestamp=_at(),
                signal_id="sig-1",
                side=SignalDirection.LONG,
            ),
            symbol="XAUUSD",
            timeframe="M15",
            strategy="ema_rsi_atr_v1",
            side=SignalDirection.LONG,
            requested_quantity=0.01,
            stop_loss=1.0,
            take_profit=2.0,
            created_at=_at(),
            source="t",
        )
        store.create_intent(intent, now=_at())
        store.mark_in_flight(intent.intent_id, now=_at())

        paper2 = PaperExecutor(
            FilePaperStateStore(state).load(),
            config=BacktestConfig.from_settings(Settings(_env_file=None)),
        )
        store2 = SnapshotIntentStore(paper2, persist=lambda: None)
        recovered = store2.recover_in_flight_to_unknown(now=_at())
        assert len(recovered) == 1
        assert recovered[0].lifecycle is IntentLifecycle.UNKNOWN
        spy = SpyExecutionPort()
        result = _orch(store2, spy).execute(_plan(), quote=make_xauusd_symbol())
        assert spy.calls == []
        assert result.outcome in {
            OrchestrationOutcome.UNKNOWN,
            OrchestrationOutcome.BLOCKED,
        }


class TestCatchUpAndGuards:
    def test_catch_up_blocked(self) -> None:
        port = SpyExecutionPort()
        result = _orch(_store(), port).execute(
            _plan(event_kind=ExecutionEventKind.CATCH_UP),
            quote=make_xauusd_symbol(),
        )
        assert result.outcome == OrchestrationOutcome.BLOCKED
        assert port.calls == []

    def test_replay_blocked(self) -> None:
        port = SpyExecutionPort()
        result = _orch(_store(), port).execute(
            _plan(event_kind=ExecutionEventKind.REPLAY),
            quote=make_xauusd_symbol(),
        )
        assert result.outcome == OrchestrationOutcome.BLOCKED
        assert port.calls == []

    def test_kill_guard_blocked(self) -> None:
        port = SpyExecutionPort()
        result = _orch(
            _store(),
            port,
            guard=StaticExecutionGuard(allowed=False, reason="kill_switch"),
        ).execute(_plan(), quote=make_xauusd_symbol())
        assert result.outcome == OrchestrationOutcome.BLOCKED
        assert port.calls == []

    def test_existing_unknown_blocks_new_signal(self) -> None:
        store = ControllableStore(_store())
        port = SpyExecutionPort(responses=AckStatus.UNKNOWN)
        _orch(store, port).execute(_plan(signal_id="a"), quote=make_xauusd_symbol())
        assert len(port.calls) == 1
        spy = SpyExecutionPort()
        blocked = _orch(store, spy).execute(
            _plan(signal_id="b", ts=_at().replace(minute=15)),
            quote=make_xauusd_symbol(),
        )
        assert blocked.outcome == OrchestrationOutcome.BLOCKED
        assert spy.calls == []


class TestFailureInjection:
    def test_create_failure_no_call(self) -> None:
        store = ControllableStore(_store())
        store.fail_create = True
        port = SpyExecutionPort()
        result = _orch(store, port).execute(_plan(), quote=make_xauusd_symbol())
        assert result.outcome == OrchestrationOutcome.ERROR
        assert port.calls == []

    def test_in_flight_failure_no_call(self) -> None:
        store = ControllableStore(_store())
        store.fail_in_flight = True
        port = SpyExecutionPort()
        result = _orch(store, port).execute(_plan(), quote=make_xauusd_symbol())
        assert result.outcome == OrchestrationOutcome.ERROR
        assert port.calls == []
        row = store.get("intent-sig-1")
        assert row is not None
        assert row.lifecycle is IntentLifecycle.INTENT_CREATED

    def test_transport_exception_unknown_no_retry(self) -> None:
        store = ControllableStore(_store())
        port = SpyExecutionPort(exceptions=[RuntimeError("boom")])
        orch = _orch(store, port)
        first = orch.execute(_plan(), quote=make_xauusd_symbol())
        assert first.outcome == OrchestrationOutcome.UNKNOWN
        assert len(port.calls) == 1
        second = orch.execute(_plan(), quote=make_xauusd_symbol())
        assert len(port.calls) == 1
        assert second.port_calls == 0

    def test_finalize_failure_after_side_effect_no_resend(self) -> None:
        store = ControllableStore(_store())
        store.fail_filled = True
        port = SpyExecutionPort(responses=AckStatus.FILLED)
        orch = _orch(store, port)
        first = orch.execute(_plan(), quote=make_xauusd_symbol())
        assert first.outcome == OrchestrationOutcome.UNKNOWN
        assert len(port.calls) == 1
        second = orch.execute(_plan(), quote=make_xauusd_symbol())
        assert len(port.calls) == 1
        assert second.port_calls == 0


class TestLifecycleRules:
    def test_invalid_transition_rejected(self) -> None:
        with pytest.raises(InvalidLifecycleTransition):
            assert_transition_allowed(IntentLifecycle.FILLED, IntentLifecycle.IN_FLIGHT)
        with pytest.raises(InvalidLifecycleTransition):
            assert_transition_allowed(IntentLifecycle.REJECTED, IntentLifecycle.IN_FLIGHT)
        with pytest.raises(InvalidLifecycleTransition):
            assert_transition_allowed(IntentLifecycle.UNKNOWN, IntentLifecycle.IN_FLIGHT)
        with pytest.raises(InvalidLifecycleTransition):
            assert_transition_allowed(IntentLifecycle.FILLED, IntentLifecycle.INTENT_CREATED)


class TestStaticSafety:
    def test_orchestrator_has_no_mt5_imports(self) -> None:
        forbidden_modules = {"MetaTrader5", "MetaTrader"}
        core_files = (
            "plan.py",
            "orchestrator.py",
            "guard.py",
            "eligibility.py",
            "idempotency.py",
            "result.py",
            "spy.py",
            "planning.py",
            "__init__.py",
        )
        for name in core_files:
            path = ORCH_PKG / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] not in forbidden_modules
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "mt5" not in node.module.lower()
                    assert node.module.split(".")[0] not in forbidden_modules
            text = path.read_text(encoding="utf-8")
            for token in ("order_send", "TRADE_ACTION_DEAL", "LiveMT5ExecutionTransport"):
                assert token not in text, f"{path.name} contains {token}"

    def test_phase11_packages_still_clean(self) -> None:
        packages = ("candle_engine", "signal_engine", "risk", "paper_execution")
        needles = (
            "order_send",
            "TRADE_ACTION_DEAL",
            "LiveMT5ExecutionTransport",
            "MT5Executor",
        )
        for pkg in packages:
            for path in (SRC / pkg).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for needle in needles:
                    assert needle not in text, f"{path} contains {needle}"

    def test_factory_does_not_wire_mt5_executor(self) -> None:
        from exness_bot.paper_execution import factory as factory_mod

        source = inspect.getsource(factory_mod)
        assert "MT5Executor" not in source
        assert "LiveMT5ExecutionTransport" not in source

    def test_safe_defaults_unchanged(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.live_kill_switch is True
        assert settings.live_demo_approval is False
        assert settings.execution_mode.value == "paper"
        assert settings.allow_legacy_run is False
