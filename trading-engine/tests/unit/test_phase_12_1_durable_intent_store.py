"""Phase 12.1 — durable live intent store. No MT5 trading APIs."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.settings import Settings
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionIntent,
    IntentLifecycle,
)
from exness_bot.paper_execution.errors import (
    CorruptStateError,
    InvalidLifecycleTransition,
    UnsupportedSchemaError,
)
from exness_bot.paper_execution.fake_port import FakeExecutionPort
from exness_bot.paper_execution.intent_store import (
    ExecutionEvidence,
    SnapshotIntentStore,
    UnknownReason,
)
from exness_bot.paper_execution.models import ExecutionOutcome, PaperSnapshot
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.paper_execution.state import (
    CURRENT_SCHEMA_VERSION,
    FilePaperStateStore,
    InMemoryPaperStateStore,
    snapshot_from_dict,
    snapshot_to_dict,
)
from exness_bot.risk.manager import RiskManager
from exness_bot.signal_engine.models import SignalKind
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME
from tests.fixtures.risk_data import make_xauusd_symbol
from tests.unit.test_paper_validation import _result

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
PHASE_PACKAGES = (
    "candle_engine",
    "signal_engine",
    "risk",
    "paper_execution",
    "api/services",
)
SYMBOL = "XAUUSD"
TF = "M15"


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 29, hour, minute, tzinfo=UTC)


def _intent_dto(*, intent_id: str = "i-1", key: str = "k-1") -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=intent_id,
        idempotency_key=key,
        symbol=SYMBOL,
        timeframe=TF,
        strategy=STRATEGY_NAME,
        side=SignalDirection.LONG,
        requested_quantity=0.1,
        stop_loss=2340.0,
        take_profit=2370.0,
        created_at=_at(11, 15),
        source="test",
    )


def _store_pair() -> tuple[SnapshotIntentStore, InMemoryPaperStateStore, object]:
    from exness_bot.paper_execution.executor import PaperExecutor

    paper_store = InMemoryPaperStateStore()
    executor = PaperExecutor(paper_store.load(), config=BacktestConfig())
    intents = SnapshotIntentStore(executor, persist=lambda: paper_store.save(executor.snapshot))
    return intents, paper_store, executor


def _service(
    clock: FakeClock,
    *,
    store: InMemoryPaperStateStore | FilePaperStateStore | None = None,
    port: FakeExecutionPort | None = None,
) -> ExecutionService:
    settings = Settings(_env_file=None)
    return ExecutionService(
        risk_manager=RiskManager(settings),
        store=store or InMemoryPaperStateStore(),
        settings=settings,
        config=BacktestConfig.from_settings(settings),
        symbol_info=make_xauusd_symbol(),
        clock=clock,
        port=port,
    )


def _strip_docs(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:]
    return ast.unparse(tree)


class TestDurableStoreApi:
    def test_create_intent(self) -> None:
        intents, _, _ = _store_pair()
        result = intents.create_intent(_intent_dto(), now=_at(12, 0))
        assert result.created is True
        assert result.record.lifecycle == IntentLifecycle.INTENT_CREATED

    def test_duplicate_idempotency_key(self) -> None:
        intents, _, _ = _store_pair()
        first = intents.create_intent(_intent_dto(intent_id="a", key="same"), now=_at(12, 0))
        second = intents.create_intent(_intent_dto(intent_id="b", key="same"), now=_at(12, 1))
        assert first.created is True
        assert second.created is False
        assert second.record.intent_id == first.record.intent_id
        assert len(intents.list_blocking()) == 1

    def test_mark_in_flight(self) -> None:
        intents, _, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        row = intents.mark_in_flight("i-1", now=_at(12, 1))
        assert row.lifecycle == IntentLifecycle.IN_FLIGHT
        assert intents.list_in_flight()[0].intent_id == "i-1"

    def test_mark_filled(self) -> None:
        intents, _, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        intents.mark_in_flight("i-1", now=_at(12, 1))
        row = intents.mark_filled(
            "i-1",
            ExecutionEvidence(fill_price=2350.5, reason="ok"),
            now=_at(12, 2),
        )
        assert row.lifecycle == IntentLifecycle.FILLED
        assert row.fill_price == 2350.5

    def test_mark_rejected(self) -> None:
        intents, _, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        intents.mark_in_flight("i-1", now=_at(12, 1))
        row = intents.mark_rejected(
            "i-1",
            ExecutionEvidence(reason="no"),
            now=_at(12, 2),
        )
        assert row.lifecycle == IntentLifecycle.REJECTED
        assert row.fill_price is None

    def test_mark_unknown(self) -> None:
        intents, _, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        intents.mark_in_flight("i-1", now=_at(12, 1))
        row = intents.mark_unknown("i-1", UnknownReason.ACK_TIMEOUT, now=_at(12, 2))
        assert row.lifecycle == IntentLifecycle.UNKNOWN
        assert intents.list_unknown()[0].intent_id == "i-1"

    def test_invalid_lifecycle_transition(self) -> None:
        intents, _, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        intents.mark_in_flight("i-1", now=_at(12, 1))
        intents.mark_filled("i-1", ExecutionEvidence(fill_price=1.0), now=_at(12, 2))
        with pytest.raises(InvalidLifecycleTransition):
            intents.mark_in_flight("i-1", now=_at(12, 3))
        with pytest.raises(InvalidLifecycleTransition):
            intents.mark_filled("i-1", ExecutionEvidence(), now=_at(12, 3))
        with pytest.raises(InvalidLifecycleTransition):
            intents.mark_unknown("i-1", UnknownReason.OPERATOR, now=_at(12, 3))

    def test_unknown_cannot_mark_filled_without_reconcile(self) -> None:
        intents, _, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        intents.mark_in_flight("i-1", now=_at(12, 1))
        intents.mark_unknown("i-1", UnknownReason.ACK_UNKNOWN, now=_at(12, 2))
        with pytest.raises(InvalidLifecycleTransition):
            intents.mark_filled("i-1", ExecutionEvidence(fill_price=1.0), now=_at(12, 3))
        row = intents.reconcile_filled(
            "i-1",
            ExecutionEvidence(fill_price=2.0, reason="evidence"),
            now=_at(12, 3),
        )
        assert row.lifecycle == IntentLifecycle.FILLED

    def test_get_and_lists(self) -> None:
        intents, _, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        assert intents.get("i-1") is not None
        assert intents.get_by_key("k-1") is not None
        intents.mark_in_flight("i-1", now=_at(12, 1))
        assert len(intents.list_in_flight()) == 1
        intents.mark_unknown("i-1", UnknownReason.ACK_UNKNOWN, now=_at(12, 2))
        assert len(intents.list_unknown()) == 1


class TestPersistence:
    def test_restart_preserves_intent(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        clock = FakeClock(_at(12, 0))
        first = _service(clock, store=FilePaperStateStore(path))
        first.consume(_result(_at(11, 15), SignalKind.BUY))
        intent = first.intents()[-1]
        second = _service(clock, store=FilePaperStateStore(path))
        assert second.intents()[-1].intent_id == intent.intent_id
        assert second.intents()[-1].lifecycle == IntentLifecycle.FILLED

    def test_restart_preserves_idempotency(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        clock = FakeClock(_at(12, 0))
        _service(clock, store=FilePaperStateStore(path)).consume(
            _result(_at(11, 15), SignalKind.BUY)
        )
        replay = _service(clock, store=FilePaperStateStore(path)).consume(
            _result(_at(11, 15), SignalKind.BUY)
        )
        assert replay.status == ExecutionOutcome.DUPLICATE

    def test_atomic_replacement(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        store = FilePaperStateStore(path)
        snap = PaperSnapshot.initial(10_000.0)
        store.save(snap)
        assert path.is_file()
        assert not path.with_suffix(".json.tmp").exists()
        loaded = store.load()
        assert loaded.session_id == snap.session_id

    def test_corrupted_json_fails_closed(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        path.write_text("{not-json", encoding="utf-8")
        with pytest.raises(CorruptStateError):
            FilePaperStateStore(path).load()

    def test_empty_state_fails_closed(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        path.write_text("   \n", encoding="utf-8")
        with pytest.raises(CorruptStateError):
            FilePaperStateStore(path).load()

    def test_unsupported_schema_fails_closed(self) -> None:
        raw = snapshot_to_dict(PaperSnapshot.initial(10_000.0))
        raw["schemaVersion"] = 99
        with pytest.raises(UnsupportedSchemaError):
            snapshot_from_dict(raw)

    def test_missing_required_fields_fail_closed(self) -> None:
        raw = snapshot_to_dict(PaperSnapshot.initial(10_000.0))
        raw["intents"] = [
            {
                "intentId": "x",
                "idempotencyKey": "k",
                "lifecycle": "FILLED",
                # missing side/symbol/createdAt/updatedAt
            }
        ]
        with pytest.raises(CorruptStateError):
            snapshot_from_dict(raw)

    def test_duplicate_intent_ids_fail_closed(self) -> None:
        now = _at(12, 0).isoformat()
        raw = snapshot_to_dict(PaperSnapshot.initial(10_000.0))
        row = {
            "intentId": "dup",
            "idempotencyKey": "k1",
            "lifecycle": "FILLED",
            "createdAt": now,
            "updatedAt": now,
            "side": "LONG",
            "symbol": SYMBOL,
            "requestedQuantity": 0.1,
            "stopLoss": 1.0,
            "takeProfit": 2.0,
        }
        raw["intents"] = [row, {**row, "idempotencyKey": "k2"}]
        with pytest.raises(CorruptStateError):
            snapshot_from_dict(raw)

    def test_schema_version_current(self) -> None:
        assert CURRENT_SCHEMA_VERSION == 3
        raw = snapshot_to_dict(PaperSnapshot.initial(1.0))
        assert raw["schemaVersion"] == 3


class TestRecovery:
    def test_in_flight_to_unknown(self) -> None:
        intents, store, executor = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        intents.mark_in_flight("i-1", now=_at(12, 1))
        recovered = intents.recover_in_flight_to_unknown(now=_at(12, 2))
        assert len(recovered) == 1
        assert recovered[0].lifecycle == IntentLifecycle.UNKNOWN
        loaded = store.load()
        assert loaded.intents[0].lifecycle == IntentLifecycle.UNKNOWN
        del executor

    def test_unknown_is_not_auto_submitted(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        port = FakeExecutionPort(responses=AckStatus.UNKNOWN)
        paper = _service(clock, store=store, port=port)
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        calls = len(port.calls)
        port2 = FakeExecutionPort(responses=AckStatus.FILLED)
        _service(clock, store=store, port=port2)
        assert port2.calls == []
        assert len(port.calls) == calls

    def test_unknown_remains_without_evidence(self) -> None:
        intents, _, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        intents.mark_in_flight("i-1", now=_at(12, 1))
        intents.mark_unknown("i-1", UnknownReason.ACK_UNKNOWN, now=_at(12, 2))
        assert intents.get("i-1") is not None
        assert intents.get("i-1").lifecycle == IntentLifecycle.UNKNOWN  # type: ignore[union-attr]

    def test_restart_does_not_duplicate_intent(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        clock = FakeClock(_at(12, 0))
        first = _service(clock, store=FilePaperStateStore(path))
        first.consume(_result(_at(11, 15), SignalKind.BUY))
        second = _service(clock, store=FilePaperStateStore(path))
        assert len(second.intents()) == 1

    def test_final_filled_survives_restart(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        clock = FakeClock(_at(12, 0))
        _service(clock, store=FilePaperStateStore(path)).consume(
            _result(_at(11, 15), SignalKind.BUY)
        )
        again = _service(clock, store=FilePaperStateStore(path))
        assert again.intents()[-1].lifecycle == IntentLifecycle.FILLED

    def test_final_rejected_survives_restart(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        clock = FakeClock(_at(12, 0))
        port = FakeExecutionPort(responses=AckStatus.REJECTED)
        _service(clock, store=FilePaperStateStore(path), port=port).consume(
            _result(_at(11, 15), SignalKind.BUY)
        )
        again = _service(clock, store=FilePaperStateStore(path))
        assert again.intents()[-1].lifecycle == IntentLifecycle.REJECTED


class TestCrashWindows:
    def test_case_a_create_before_in_flight(self) -> None:
        intents, store, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        loaded = store.load()
        assert loaded.intents[0].lifecycle == IntentLifecycle.INTENT_CREATED
        from exness_bot.paper_execution.executor import PaperExecutor

        exe2 = PaperExecutor(loaded, config=BacktestConfig())
        intents2 = SnapshotIntentStore(exe2, persist=lambda: None)
        intents2.recover_in_flight_to_unknown(now=_at(12, 1))
        row = intents2.get("i-1")
        assert row is not None
        assert row.lifecycle == IntentLifecycle.INTENT_CREATED

    def test_case_b_in_flight_before_submit(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        seen: list[IntentLifecycle] = []

        class Tracking:
            def load(self) -> PaperSnapshot:
                return store.load()

            def save(self, snapshot: PaperSnapshot) -> None:
                if snapshot.intents:
                    seen.append(snapshot.intents[-1].lifecycle)
                store.save(snapshot)

        port = FakeExecutionPort(responses=AckStatus.FILLED)
        paper = _service(clock, store=Tracking(), port=port)  # type: ignore[arg-type]
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert IntentLifecycle.IN_FLIGHT in seen
        inflight_idx = seen.index(IntentLifecycle.IN_FLIGHT)
        assert seen.index(IntentLifecycle.FILLED) > inflight_idx

    def test_case_c_crash_before_final_persist_is_unknown(self) -> None:
        intents, store, _ = _store_pair()
        intents.create_intent(_intent_dto(), now=_at(12, 0))
        intents.mark_in_flight("i-1", now=_at(12, 1))
        assert store.load().intents[0].lifecycle == IntentLifecycle.IN_FLIGHT
        from exness_bot.paper_execution.executor import PaperExecutor

        exe2 = PaperExecutor(store.load(), config=BacktestConfig())
        intents2 = SnapshotIntentStore(exe2, persist=lambda: store.save(exe2.snapshot))
        intents2.recover_in_flight_to_unknown(now=_at(12, 2))
        row = intents2.get("i-1")
        assert row is not None
        assert row.lifecycle == IntentLifecycle.UNKNOWN

    def test_case_d_final_state_survives(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        clock = FakeClock(_at(12, 0))
        first = _service(clock, store=FilePaperStateStore(path))
        first.consume(_result(_at(11, 15), SignalKind.BUY))
        intent = first.intents()[-1]
        second = _service(clock, store=FilePaperStateStore(path))
        row = second.intents()[-1]
        assert row.lifecycle == intent.lifecycle
        assert row.intent_id == intent.intent_id
        assert row.idempotency_key == intent.idempotency_key

    def test_case_e_duplicate_create_after_restart(self, tmp_path: Path) -> None:
        path = tmp_path / "paper.json"
        clock = FakeClock(_at(12, 0))
        _service(clock, store=FilePaperStateStore(path)).consume(
            _result(_at(11, 15), SignalKind.BUY)
        )
        second = _service(clock, store=FilePaperStateStore(path))
        replay = second.consume(_result(_at(11, 15), SignalKind.BUY))
        assert replay.status == ExecutionOutcome.DUPLICATE
        assert len(second.intents()) == 1


class TestExecutionServiceDurability:
    def test_in_flight_persisted_before_submit(self) -> None:
        seen: list[IntentLifecycle] = []
        store = InMemoryPaperStateStore()

        class Tracking:
            def load(self) -> PaperSnapshot:
                return store.load()

            def save(self, snapshot: PaperSnapshot) -> None:
                if snapshot.intents:
                    seen.append(snapshot.intents[-1].lifecycle)
                store.save(snapshot)

        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        paper = _service(clock, store=Tracking(), port=port)  # type: ignore[arg-type]
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert IntentLifecycle.IN_FLIGHT in seen
        assert seen.index(IntentLifecycle.IN_FLIGHT) < seen.index(IntentLifecycle.FILLED)
        assert len(port.calls) == 1

    def test_submit_never_before_durable_in_flight(self) -> None:
        store = InMemoryPaperStateStore()
        submit_seen_lifecycle: list[IntentLifecycle | None] = []

        class SpyPort(FakeExecutionPort):
            def submit(self, intent, *, quote):  # type: ignore[no-untyped-def]
                snap = store.load()
                matching = [i for i in snap.intents if i.intent_id == intent.intent_id]
                submit_seen_lifecycle.append(
                    matching[-1].lifecycle if matching else None
                )
                return super().submit(intent, quote=quote)

        clock = FakeClock(_at(12, 0))
        paper = _service(clock, store=store, port=SpyPort(responses=AckStatus.FILLED))
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert submit_seen_lifecycle == [IntentLifecycle.IN_FLIGHT]

    def test_final_result_persisted(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert paper.intents()[-1].lifecycle == IntentLifecycle.FILLED

    def test_fake_failure_produces_unknown(self) -> None:
        clock = FakeClock(_at(12, 0))
        port = FakeExecutionPort(responses=AckStatus.TIMEOUT)
        paper = _service(clock, port=port)
        result = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert result.status == ExecutionOutcome.UNKNOWN
        assert paper.intents()[-1].lifecycle == IntentLifecycle.UNKNOWN

    def test_duplicate_signal_cannot_create_duplicate_intent(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert len(paper.intents()) == 1


class TestSafety:
    def test_live_mode_still_disabled(self) -> None:
        from exness_bot.config.live_enablement import assert_live_execution_not_operational

        live = Settings(_env_file=None, EXECUTION_MODE="live")
        with pytest.raises(RuntimeError):
            assert_live_execution_not_operational(live)

    def test_phase_packages_have_no_trading_api(self) -> None:
        for package in PHASE_PACKAGES:
            root = SRC / package
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                code = _strip_docs(path.read_text(encoding="utf-8"))
                assert "order_send" not in code, path
                assert "TRADE_ACTION_DEAL" not in code, path
                assert "class MT5Executor" not in code, path
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute) and node.attr == "order_send":
                        pytest.fail(f"order_send attribute in {path}")

    def test_fsync_used_in_file_store(self) -> None:
        source = (SRC / "paper_execution" / "state.py").read_text(encoding="utf-8")
        assert "os.fsync" in source
        assert "os.replace" in source


class TestMissingFileFresh:
    def test_missing_state_file_is_fresh_not_corrupt(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"
        snap = FilePaperStateStore(path).load()
        assert snap.intents == ()
        assert snap.initial_balance == 10_000.0
