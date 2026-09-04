"""Phase 11.9 — pre-live final safety & read-only UNKNOWN reconciliation."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest

from exness_bot.backtest.config import BacktestConfig
from exness_bot.cli import handle_run
from exness_bot.config.live_enablement import (
    assert_phase11_live_disabled,
    evaluate_future_live_gates,
)
from exness_bot.config.settings import Settings
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionEvidence,
    IntentReconcileStatus,
    StaticBrokerExecutionQuery,
    UnavailableBrokerExecutionQuery,
    match_intent_to_evidence,
)
from exness_bot.paper_execution.contract import (
    AckStatus,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.fake_port import FakeExecutionPort
from exness_bot.paper_execution.models import ExecutionOutcome, PaperSnapshot
from exness_bot.paper_execution.port import ExecutionPort
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.paper_execution.state import InMemoryPaperStateStore
from exness_bot.paper_execution.unknown_recovery import (
    apply_reconcile_to_intent,
    reconcile_unknown_intents,
)
from exness_bot.risk.manager import RiskManager
from exness_bot.signal_engine.models import SignalKind
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME
from tests.fixtures.risk_data import make_xauusd_symbol
from tests.unit.test_paper_validation import _result

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
PHASE11_PACKAGES = (
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


def _intent(
    *,
    lifecycle: IntentLifecycle = IntentLifecycle.UNKNOWN,
    intent_id: str = "intent-1",
    key: str = "key-1",
    side: str = "LONG",
    volume: float = 0.1,
    broker_order_id: str | None = None,
    correlation_id: str | None = None,
    stamp: datetime | None = None,
) -> IntentRecord:
    now = stamp or _at(11, 15)
    return IntentRecord(
        intent_id=intent_id,
        idempotency_key=key,
        lifecycle=lifecycle,
        created_at=now,
        updated_at=now,
        side=side,
        symbol=SYMBOL,
        requested_quantity=volume,
        stop_loss=2340.0,
        take_profit=2370.0,
        strategy=STRATEGY_NAME,
        timeframe=TF,
        signal_timestamp=now,
        correlation_id=correlation_id or intent_id,
        broker_order_id=broker_order_id,
    )


def _evidence(
    *,
    correlation_id: str | None = None,
    broker_order_id: str | None = None,
    side: SignalDirection = SignalDirection.LONG,
    volume: float = 0.1,
    stamp: datetime | None = None,
    rejected: bool = False,
    symbol: str = SYMBOL,
) -> BrokerExecutionEvidence:
    return BrokerExecutionEvidence(
        symbol=symbol,
        side=side,
        volume=volume,
        timestamp=stamp or _at(11, 16),
        broker_order_id=broker_order_id,
        broker_deal_id="deal-9",
        correlation_id=correlation_id,
        rejected=rejected,
        reject_reason="broker_rejected" if rejected else None,
        fill_price=2350.5,
    )


def _service(
    clock: FakeClock,
    *,
    store: InMemoryPaperStateStore | None = None,
    port: FakeExecutionPort | None = None,
    broker_query=None,
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
        broker_query=broker_query,
    )


class MemoryIntentStore:
    def __init__(self, records: list[IntentRecord] | None = None) -> None:
        self._rows = {item.intent_id: item for item in (records or [])}
        self.updates: list[IntentRecord] = []

    def create(self, record: IntentRecord) -> None:
        self._rows[record.intent_id] = record

    def update(self, record: IntentRecord) -> None:
        self._rows[record.intent_id] = record
        self.updates.append(record)

    def get(self, intent_id: str) -> IntentRecord | None:
        return self._rows.get(intent_id)

    def get_by_key(self, idempotency_key: str) -> IntentRecord | None:
        for item in self._rows.values():
            if item.idempotency_key == idempotency_key:
                return item
        return None

    def list_blocking(self) -> tuple[IntentRecord, ...]:
        return tuple(
            item
            for item in self._rows.values()
            if item.lifecycle in {IntentLifecycle.IN_FLIGHT, IntentLifecycle.UNKNOWN}
        )

    def recover_in_flight_to_unknown(self, *, now: datetime) -> tuple[IntentRecord, ...]:
        del now
        return ()


class TestBrokerReconciliation:
    def test_unknown_reconciles_to_confirmed_filled(self) -> None:
        intent = _intent()
        store = MemoryIntentStore([intent])
        query = StaticBrokerExecutionQuery(
            [_evidence(correlation_id=intent.intent_id)]
        )
        resolved = reconcile_unknown_intents(store, query, now=_at(12, 0))
        assert len(resolved) == 1
        assert resolved[0].lifecycle == IntentLifecycle.FILLED
        assert resolved[0].intent_id == intent.intent_id

    def test_unknown_reconciles_to_confirmed_rejected(self) -> None:
        intent = _intent()
        store = MemoryIntentStore([intent])
        query = StaticBrokerExecutionQuery(
            [_evidence(correlation_id=intent.intent_id, rejected=True)]
        )
        resolved = reconcile_unknown_intents(store, query, now=_at(12, 0))
        assert len(resolved) == 1
        assert resolved[0].lifecycle == IntentLifecycle.REJECTED

    def test_not_found_does_not_auto_retry(self) -> None:
        intent = _intent()
        store = MemoryIntentStore([intent])
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        query = StaticBrokerExecutionQuery(())
        result = query.find_execution(intent)
        assert result.status == IntentReconcileStatus.NOT_FOUND
        updated = apply_reconcile_to_intent(store, intent, result, now=_at(12, 0))
        assert updated.lifecycle == IntentLifecycle.UNKNOWN
        assert port.calls == []

    def test_ambiguous_result_stays_unknown(self) -> None:
        intent = _intent()
        store = MemoryIntentStore([intent])
        evidence = [
            _evidence(correlation_id=intent.intent_id, broker_order_id="a"),
            _evidence(correlation_id=intent.intent_id, broker_order_id="b"),
        ]
        result = match_intent_to_evidence(intent, evidence)
        assert result.status == IntentReconcileStatus.AMBIGUOUS
        updated = apply_reconcile_to_intent(store, intent, result, now=_at(12, 0))
        assert updated.lifecycle == IntentLifecycle.UNKNOWN

    def test_broker_query_unavailable_stays_unknown(self) -> None:
        intent = _intent()
        store = MemoryIntentStore([intent])
        query = UnavailableBrokerExecutionQuery()
        result = query.find_execution(intent)
        assert result.status == IntentReconcileStatus.UNAVAILABLE
        updated = apply_reconcile_to_intent(store, intent, result, now=_at(12, 0))
        assert updated.lifecycle == IntentLifecycle.UNKNOWN


class TestMatching:
    def test_reconciliation_prefers_strong_identifier(self) -> None:
        intent = _intent(correlation_id="corr-strong")
        weak_unrelated = _evidence(
            side=SignalDirection.LONG,
            volume=0.1,
            stamp=_at(11, 16),
            correlation_id=None,
        )
        strong = _evidence(correlation_id="corr-strong", volume=9.9)
        result = match_intent_to_evidence(intent, [weak_unrelated, strong])
        assert result.status == IntentReconcileStatus.CONFIRMED_FILLED
        assert result.matched_evidence[0].correlation_id == "corr-strong"

    def test_reconciliation_does_not_match_unrelated_position(self) -> None:
        intent = _intent(side="LONG", volume=0.1)
        unrelated = _evidence(side=SignalDirection.SHORT, volume=0.1)
        result = match_intent_to_evidence(intent, [unrelated])
        assert result.status == IntentReconcileStatus.NOT_FOUND

    def test_ambiguous_match_is_not_treated_as_filled(self) -> None:
        intent = _intent()
        twins = [
            _evidence(volume=0.1, stamp=_at(11, 16), broker_order_id="1"),
            _evidence(volume=0.1, stamp=_at(11, 17), broker_order_id="2"),
        ]
        result = match_intent_to_evidence(intent, twins)
        assert result.status == IntentReconcileStatus.AMBIGUOUS
        assert result.status != IntentReconcileStatus.CONFIRMED_FILLED


class TestIdempotency:
    def test_unknown_reconciliation_keeps_same_intent_id(self) -> None:
        intent = _intent(intent_id="keep-me")
        store = MemoryIntentStore([intent])
        query = StaticBrokerExecutionQuery([_evidence(correlation_id="keep-me")])
        resolved = reconcile_unknown_intents(store, query, now=_at(12, 0))
        assert resolved[0].intent_id == "keep-me"

    def test_unknown_reconciliation_keeps_same_idempotency_key(self) -> None:
        intent = _intent(key="idem-keep")
        store = MemoryIntentStore([intent])
        query = StaticBrokerExecutionQuery(
            [_evidence(correlation_id=intent.intent_id)]
        )
        resolved = reconcile_unknown_intents(store, query, now=_at(12, 0))
        assert resolved[0].idempotency_key == "idem-keep"

    def test_confirmed_fill_does_not_create_second_intent(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        port = FakeExecutionPort(responses=AckStatus.UNKNOWN)
        paper = _service(clock, store=store, port=port)
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert len(paper.intents()) == 1
        unknown = paper.intents()[0]
        assert unknown.lifecycle == IntentLifecycle.UNKNOWN

        query = StaticBrokerExecutionQuery(
            [_evidence(correlation_id=unknown.intent_id)]
        )
        paper2 = _service(clock, store=store, port=port, broker_query=query)
        assert len(paper2.intents()) == 1
        assert paper2.intents()[0].lifecycle == IntentLifecycle.FILLED
        assert paper2.intents()[0].intent_id == unknown.intent_id
        # Restart reconcile must not call submit again
        assert len(port.calls) == 1


def _strip_python_docs(source: str) -> str:
    """Remove module/class/function docstrings so audits ignore documentation mentions."""
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


class TestSafety:
    def test_reconciliation_is_read_only(self) -> None:
        paths = (
            SRC / "paper_execution" / "broker_query.py",
            SRC / "paper_execution" / "unknown_recovery.py",
            SRC / "broker" / "mt5" / "execution_query.py",
        )
        for path in paths:
            code = _strip_python_docs(path.read_text(encoding="utf-8"))
            assert "order_send" not in code
            assert "TRADE_ACTION" not in code

    def test_reconciliation_cannot_submit(self) -> None:
        recovery = Path(SRC / "paper_execution" / "unknown_recovery.py").read_text(
            encoding="utf-8"
        )
        code = _strip_python_docs(recovery)
        assert ".submit(" not in code
        assert "ExecutionPort" not in code

    def test_unknown_cannot_trigger_submit(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        port = FakeExecutionPort(responses=AckStatus.UNKNOWN)
        paper = _service(clock, store=store, port=port)
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        calls_before = len(port.calls)
        again = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert again.status in {ExecutionOutcome.UNKNOWN, ExecutionOutcome.DUPLICATE}
        assert len(port.calls) == calls_before

    def test_phase_11_has_no_mt5_executor(self) -> None:
        for package in PHASE11_PACKAGES:
            root = SRC / package
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                assert "class MT5Executor" not in text
                assert "MT5Executor(" not in text

    def test_phase_11_has_no_order_send(self) -> None:
        for package in PHASE11_PACKAGES:
            root = SRC / package
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute) and node.attr == "order_send":
                        pytest.fail(f"order_send in Phase 11 path: {path}")
                    if isinstance(node, ast.Name) and node.id == "order_send":
                        pytest.fail(f"order_send name in Phase 11 path: {path}")
                code = _strip_python_docs(path.read_text(encoding="utf-8"))
                assert "order_send" not in code, f"order_send in {path}"
                assert "TRADE_ACTION_DEAL" not in code, f"TRADE_ACTION_DEAL in {path}"
                assert "class MT5Executor" not in code


class TestLegacyIsolation:
    def test_paper_mode_cannot_route_to_legacy_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "exness_bot.cli.get_settings",
            lambda: Settings(_env_file=None, ALLOW_LEGACY_RUN=False),
        )
        code = handle_run(dry_run=True, once=True)
        assert code == 1

    def test_phase_11_does_not_construct_order_manager(self) -> None:
        for name in ("service.py", "executor.py", "factory.py", "loop.py", "runtime.py"):
            path = SRC / "paper_execution" / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            assert "OrderManager" not in text
            assert "MT5Adapter" not in text


class TestLiveGates:
    def test_live_mode_remains_disabled(self) -> None:
        from exness_bot.config.live_enablement import assert_live_execution_not_operational

        live = Settings(_env_file=None, EXECUTION_MODE="live")
        with pytest.raises(RuntimeError):
            assert_live_execution_not_operational(live)

    def test_missing_live_gate_fails_closed(self) -> None:
        settings = Settings(_env_file=None)
        assessment = evaluate_future_live_gates(settings)
        assert assessment.allowed is False
        assert "execution_mode" in assessment.missing_gates
        assert_phase11_live_disabled(settings)

    def test_partial_live_configuration_fails_closed(self) -> None:
        settings = Settings(
            _env_file=None,
            ALLOW_LIVE_TRADING=True,
            LIVE_EXECUTION_ENABLED=True,
            DRY_RUN=False,
            TRADING_MODE="live",
        )
        assessment = evaluate_future_live_gates(settings)
        assert assessment.allowed is False
        assert len(assessment.missing_gates) >= 1


class TestDurability:
    def test_in_flight_exists_before_submit(self) -> None:
        seen: list[IntentLifecycle] = []

        class TrackingStore:
            def __init__(self) -> None:
                self._inner = InMemoryPaperStateStore()

            def load(self) -> PaperSnapshot:
                return self._inner.load()

            def save(self, snapshot: PaperSnapshot) -> None:
                if snapshot.intents:
                    seen.append(snapshot.intents[-1].lifecycle)
                self._inner.save(snapshot)

        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        paper = _service(clock, store=TrackingStore(), port=port)  # type: ignore[arg-type]
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert IntentLifecycle.IN_FLIGHT in seen
        assert seen.index(IntentLifecycle.IN_FLIGHT) < seen.index(IntentLifecycle.FILLED)

    def test_restart_recovers_in_flight(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        paper = _service(clock, store=store)
        paper._executor.upsert_intent(
            _intent(lifecycle=IntentLifecycle.IN_FLIGHT, intent_id="crash-1", key="k-crash")
        )
        paper._persist()
        recovered = _service(clock, store=store)
        row = recovered.intents()[0]
        assert row.lifecycle == IntentLifecycle.UNKNOWN
        assert row.intent_id == "crash-1"

    def test_recovery_does_not_duplicate_submit(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        port = FakeExecutionPort(responses=AckStatus.UNKNOWN)
        paper = _service(clock, store=store, port=port)
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert len(port.calls) == 1
        port2 = FakeExecutionPort(responses=AckStatus.FILLED)
        _service(clock, store=store, port=port2)
        assert port2.calls == []


class TestPureContract:
    def test_execution_port_has_no_paper_types(self) -> None:
        port_source = (SRC / "paper_execution" / "port.py").read_text(encoding="utf-8")
        code = _strip_python_docs(port_source)
        assert "PaperAccount" not in code
        assert "VirtualPosition" not in code
        assert "PaperOpenRequest" not in code
        assert "submit" in inspect.getsource(ExecutionPort)
        assert "PaperAccount" not in str(ExecutionPort.submit.__annotations__)
        assert "VirtualPosition" not in str(ExecutionPort.submit.__annotations__)

    def test_accepted_is_not_filled(self) -> None:
        assert AckStatus.ACCEPTED != AckStatus.FILLED
        clock = FakeClock(_at(12, 0))
        port = FakeExecutionPort(responses=AckStatus.ACCEPTED)
        paper = _service(clock, port=port)
        result = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert result.status == ExecutionOutcome.UNKNOWN
        assert paper.intents()[-1].lifecycle == IntentLifecycle.UNKNOWN


class TestStaticAuditExtras:
    def test_execution_query_uses_readonly_client_only(self) -> None:
        text = (SRC / "broker" / "mt5" / "execution_query.py").read_text(encoding="utf-8")
        code = _strip_python_docs(text)
        assert "MT5ReadOnlyClient" in code
        assert "order_send" not in code
        assert "MT5Adapter" not in code
