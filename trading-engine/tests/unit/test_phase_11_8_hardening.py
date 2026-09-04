"""Phase 11.8 — pre-live execution boundary hardening. No live executor."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.settings import Settings
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.models import IndicatorSnapshot
from exness_bot.paper_execution.contract import (
    AckStatus,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.fake_port import FakeExecutionPort
from exness_bot.paper_execution.models import ExecutionOutcome, RejectionCode
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.paper_execution.state import InMemoryPaperStateStore
from exness_bot.risk.manager import RiskManager
from exness_bot.signal_engine.models import SignalEmission, SignalKind, SignalResult
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME
from tests.fixtures.risk_data import make_xauusd_symbol
from tests.unit.test_paper_validation import _result, _service

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
SYMBOL = "XAUUSD"
TF = "M15"


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 29, hour, minute, tzinfo=UTC)


def _sig(
    stamp: datetime,
    kind: SignalKind = SignalKind.BUY,
    *,
    actionable: bool = True,
    executable: bool = True,
    emission: SignalEmission = SignalEmission.SIGNAL_EMISSION,
) -> SignalResult:
    return SignalResult(
        symbol=SYMBOL,
        timeframe=TF,
        candle_timestamp=stamp,
        signal=kind,
        generated_at=stamp + timedelta(minutes=15),
        source="TEST",
        strategy=STRATEGY_NAME,
        indicators=IndicatorSnapshot(
            timestamp=stamp,
            ema_20=110.0,
            ema_50=105.0,
            ema_200=100.0,
            rsi_14=60.0,
            atr_14=2.0,
        ),
        reason="test",
        conditions=(),
        idempotency_key=f"{SYMBOL}|{TF}|{stamp.isoformat()}|{STRATEGY_NAME}",
        emission=emission,
        actionable=actionable,
        executable=executable,
    )


def _service_with_port(
    clock: FakeClock,
    port: FakeExecutionPort,
    *,
    store: InMemoryPaperStateStore | None = None,
    symbol=None,
) -> ExecutionService:
    settings = Settings(_env_file=None)
    resolved_store = store or InMemoryPaperStateStore()
    return ExecutionService(
        risk_manager=RiskManager(settings),
        store=resolved_store,
        settings=settings,
        config=BacktestConfig.from_settings(settings),
        symbol_info=symbol or make_xauusd_symbol(),
        clock=clock,
        port=port,
    )


class TestFakeExecutionPort:
    def test_fake_execution_port_returns_filled(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port)
        result = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert result.status == ExecutionOutcome.FILLED
        assert len(port.calls) == 1

    def test_fake_execution_port_returns_rejected(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.REJECTED)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port)
        result = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert result.status == ExecutionOutcome.REJECTED
        assert paper.intents()[-1].lifecycle == IntentLifecycle.REJECTED

    def test_fake_execution_port_returns_timeout(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.TIMEOUT)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port)
        result = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert result.status == ExecutionOutcome.UNKNOWN
        assert paper.intents()[-1].lifecycle == IntentLifecycle.UNKNOWN

    def test_fake_execution_port_returns_unknown(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.UNKNOWN)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port)
        result = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert result.status == ExecutionOutcome.UNKNOWN
        assert paper.intents()[-1].lifecycle == IntentLifecycle.UNKNOWN


class TestDurableLifecycle:
    def test_in_flight_is_persisted_before_submit(self) -> None:
        from exness_bot.paper_execution.models import PaperSnapshot

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
        paper = _service_with_port(clock, port, store=TrackingStore())  # type: ignore[arg-type]
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert IntentLifecycle.IN_FLIGHT in seen
        inflight_idx = seen.index(IntentLifecycle.IN_FLIGHT)
        # IN_FLIGHT must appear before FILLED in the persist stream
        assert IntentLifecycle.FILLED in seen[inflight_idx:]
        assert len(port.calls) == 1

    def test_filled_is_persisted_after_submit(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert paper.intents()[-1].lifecycle == IntentLifecycle.FILLED

    def test_rejected_is_persisted_after_submit(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.REJECTED)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port)
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert paper.intents()[-1].lifecycle == IntentLifecycle.REJECTED


class TestCrashRecovery:
    def test_in_flight_recovers_to_unknown(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        paper = _service(clock, store=store)
        now = clock.now_utc()
        paper._executor.upsert_intent(
            IntentRecord(
                intent_id="paper-intent-42",
                idempotency_key="key-crash",
                lifecycle=IntentLifecycle.IN_FLIGHT,
                created_at=now,
                updated_at=now,
                side="LONG",
                symbol=SYMBOL,
                requested_quantity=0.1,
                stop_loss=2340.0,
                take_profit=2370.0,
                strategy=STRATEGY_NAME,
                timeframe=TF,
                signal_timestamp=_at(11, 15),
                ack_status=AckStatus.IN_FLIGHT.value,
            )
        )
        paper._persist()
        restarted = _service(clock, store=store)
        record = restarted._intents.get("paper-intent-42")
        assert record is not None
        assert record.lifecycle == IntentLifecycle.UNKNOWN
        assert record.intent_id == "paper-intent-42"
        assert record.idempotency_key == "key-crash"

    def test_unknown_is_not_resubmitted(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        paper = _service_with_port(clock, port, store=store)
        now = clock.now_utc()
        paper._executor.upsert_intent(
            IntentRecord(
                intent_id="paper-intent-7",
                idempotency_key=_sig(_at(11, 15)).idempotency_key,
                lifecycle=IntentLifecycle.UNKNOWN,
                created_at=now,
                updated_at=now,
                side="LONG",
                symbol=SYMBOL,
                requested_quantity=0.1,
                stop_loss=2340.0,
                take_profit=2370.0,
            )
        )
        paper._persist()
        restarted = _service_with_port(clock, port, store=store)
        before = len(port.calls)
        outcome = restarted.consume(_sig(_at(11, 15)))
        assert outcome.status == ExecutionOutcome.UNKNOWN
        assert len(port.calls) == before

    def test_unknown_keeps_same_intent_id(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        paper = _service(clock, store=store)
        now = clock.now_utc()
        paper._executor.upsert_intent(
            IntentRecord(
                intent_id="stable-intent",
                idempotency_key="stable-key",
                lifecycle=IntentLifecycle.IN_FLIGHT,
                created_at=now,
                updated_at=now,
                side="LONG",
                symbol=SYMBOL,
                requested_quantity=0.1,
                stop_loss=1.0,
                take_profit=2.0,
            )
        )
        paper._persist()
        restarted = _service(clock, store=store)
        assert restarted._intents.get("stable-intent") is not None
        assert restarted._intents.get("stable-intent").lifecycle == IntentLifecycle.UNKNOWN

    def test_unknown_keeps_same_idempotency_key(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        paper = _service(clock, store=store)
        now = clock.now_utc()
        key = "symbol|M15|ts|strategy"
        paper._executor.upsert_intent(
            IntentRecord(
                intent_id="id-1",
                idempotency_key=key,
                lifecycle=IntentLifecycle.IN_FLIGHT,
                created_at=now,
                updated_at=now,
                side="LONG",
                symbol=SYMBOL,
                requested_quantity=0.1,
                stop_loss=1.0,
                take_profit=2.0,
            )
        )
        paper._persist()
        restarted = _service(clock, store=store)
        record = restarted._intents.get_by_key(key)
        assert record is not None
        assert record.idempotency_key == key
        assert record.lifecycle == IntentLifecycle.UNKNOWN


class TestIdempotency:
    def test_duplicate_intent_is_not_submitted(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port)
        paper.consume(_sig(_at(11, 15)))
        assert len(port.calls) == 1
        again = paper.consume(_sig(_at(11, 15)))
        assert again.status == ExecutionOutcome.DUPLICATE
        assert len(port.calls) == 1

    def test_restart_does_not_duplicate_unknown_intent(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.UNKNOWN)
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        paper = _service_with_port(clock, port, store=store)
        paper.consume(_sig(_at(11, 15)))
        assert len(port.calls) == 1
        intent_id = paper.intents()[-1].intent_id
        restarted = _service_with_port(clock, port, store=store)
        outcome = restarted.consume(_sig(_at(11, 15)))
        assert outcome.status in {ExecutionOutcome.DUPLICATE, ExecutionOutcome.UNKNOWN}
        assert len(port.calls) == 1
        assert restarted._intents.get(intent_id) is not None


class TestCatchupBoundary:
    def test_execution_boundary_allows_only_latest_signal(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        outcomes = paper.consume_results(
            [
                _sig(_at(11, 0)),
                _sig(_at(11, 15)),
                _sig(_at(11, 30)),
            ]
        )
        filled = [item for item in outcomes if item.status == ExecutionOutcome.FILLED]
        assert len(filled) == 1
        assert len(paper.open_positions()) == 1

    def test_catchup_cannot_create_multiple_intents(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        paper.consume_results(
            [
                _sig(_at(10, 0), executable=False, emission=SignalEmission.INDICATOR_CATCHUP),
                _sig(_at(10, 15), executable=False, emission=SignalEmission.INDICATOR_CATCHUP),
                _sig(_at(10, 30), executable=False, emission=SignalEmission.INDICATOR_CATCHUP),
                _sig(_at(11, 0)),
            ]
        )
        filled = [
            item
            for item in paper.intents()
            if item.lifecycle == IntentLifecycle.FILLED
        ]
        assert len(filled) == 1


class TestValidationGate:
    def test_invalid_quote_is_rejected_before_submit(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port, symbol=make_xauusd_symbol(bid=0.0))
        result = paper.consume(_sig(_at(11, 15)))
        assert result.status == ExecutionOutcome.REJECTED
        assert result.rejection_code == RejectionCode.INVALID_QUOTE
        assert len(port.calls) == 0
        assert not any(
            item.lifecycle == IntentLifecycle.IN_FLIGHT for item in paper.intents()
        )

    def test_invalid_volume_is_rejected_before_submit(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        symbol = make_xauusd_symbol().model_copy(
            update={"volume_min": 10.0, "volume_max": 100.0}
        )
        paper = _service_with_port(clock, port, symbol=symbol)
        result = paper.consume(_sig(_at(11, 15)))
        assert result.status == ExecutionOutcome.REJECTED
        assert len(port.calls) == 0
        assert not any(
            item.lifecycle == IntentLifecycle.IN_FLIGHT for item in paper.intents()
        )
    def test_missing_stops_metadata_fails_closed(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        # Bypass _ensure_paper_stops by clearing after init
        paper = _service_with_port(clock, port)
        paper._symbol = make_xauusd_symbol(stops_level=None, freeze_level=None)
        result = paper.consume(_sig(_at(11, 20)))
        assert result.status == ExecutionOutcome.REJECTED
        assert result.rejection_code == RejectionCode.INVALID_STOPS
        assert len(port.calls) == 0

    def test_invalid_sl_distance_is_rejected_before_submit(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        # Huge stops_level makes ATR-based SL fail distance check
        symbol = make_xauusd_symbol(stops_level=50000, freeze_level=0)
        paper = _service_with_port(clock, port, symbol=symbol)
        result = paper.consume(_sig(_at(11, 15)))
        assert result.status == ExecutionOutcome.REJECTED
        assert result.rejection_code in {RejectionCode.INVALID_SL, RejectionCode.INVALID_TP}
        assert len(port.calls) == 0

    def test_invalid_tp_distance_is_rejected_before_submit(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        symbol = make_xauusd_symbol(stops_level=50000, freeze_level=0)
        paper = _service_with_port(clock, port, symbol=symbol)
        result = paper.consume(_sig(_at(11, 15)))
        assert result.status == ExecutionOutcome.REJECTED
        assert len(port.calls) == 0

    def test_validation_failure_does_not_create_in_flight_side_effect(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port)
        paper._symbol = make_xauusd_symbol(bid=-1.0, ask=-1.0)
        paper.consume(_sig(_at(11, 25)))
        assert port.calls == []
        assert all(
            item.lifecycle != IntentLifecycle.IN_FLIGHT for item in paper.intents()
        )


class TestSafety:
    def test_phase_11_8_contains_no_live_executor(self) -> None:
        """Phase 11 packages remain free of MT5Executor (lives in broker/mt5 since 12.3)."""
        for package in (
            "candle_engine",
            "signal_engine",
            "paper_execution",
            "risk",
            "domain",
        ):
            for path in (SRC / package).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                assert "class MT5Executor" not in text
        assert (SRC / "broker" / "mt5" / "executor.py").is_file()

    def test_phase_11_8_contains_no_order_send(self) -> None:
        for package in (
            "candle_engine",
            "signal_engine",
            "paper_execution",
            "risk",
            "domain",
        ):
            for path in (SRC / package).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                        assert name != "order_send", path

    def test_phase_11_8_contains_no_trade_action(self) -> None:
        for package in ("candle_engine", "signal_engine", "paper_execution", "risk"):
            for path in (SRC / package).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and node.id.startswith("TRADE_ACTION"):
                        raise AssertionError(path)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        assert not node.value.startswith("TRADE_ACTION_"), path

    def test_execution_mode_live_remains_disabled(self) -> None:
        from exness_bot.config.live_enablement import assert_live_execution_not_operational

        live = Settings(_env_file=None, EXECUTION_MODE="live")
        with pytest.raises(RuntimeError):
            assert_live_execution_not_operational(live)
        with pytest.raises((ValidationError, ValueError)):
            Settings(_env_file=None, EXECUTION_MODE="mt5")
        with pytest.raises((ValidationError, ValueError)):
            Settings(_env_file=None, EXECUTION_MODE="broker")

    def test_unknown_cannot_trigger_submit(self) -> None:
        port = FakeExecutionPort(responses=AckStatus.FILLED)
        clock = FakeClock(_at(12, 0))
        paper = _service_with_port(clock, port)
        now = clock.now_utc()
        key = _sig(_at(11, 40)).idempotency_key
        paper._executor.upsert_intent(
            IntentRecord(
                intent_id="blocked",
                idempotency_key=key,
                lifecycle=IntentLifecycle.UNKNOWN,
                created_at=now,
                updated_at=now,
                side="LONG",
                symbol=SYMBOL,
                requested_quantity=0.1,
                stop_loss=1.0,
                take_profit=2.0,
            )
        )
        paper._persist()
        outcome = paper.consume(_sig(_at(11, 40)))
        assert outcome.status == ExecutionOutcome.UNKNOWN
        assert port.calls == []

    def test_fake_port_has_no_broker_tokens(self) -> None:
        source = (SRC / "paper_execution" / "fake_port.py").read_text(encoding="utf-8")
        for token in ("order_send", "TRADE_ACTION", "MT5Adapter", "TradingClient", "MetaTrader"):
            assert token not in source
