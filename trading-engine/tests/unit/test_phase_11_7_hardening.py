"""Phase 11.7 pre-live hardening — contract, lifecycle, catch-up, validation. No order_send."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from exness_bot.config.settings import ExecutionMode, Settings
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.execution_validation import (
    ValidationCode,
    validate_quote,
    validate_sl_tp_distance,
    validate_stops_metadata,
    validate_volume,
)
from exness_bot.domain.models import IndicatorSnapshot, Position
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionIntent,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.models import ExecutionOutcome, PositionStatus, VirtualPosition
from exness_bot.paper_execution.port import ExecutionPort
from exness_bot.paper_execution.reconciliation import ReconcileStatus, reconcile_paper_vs_broker
from exness_bot.paper_execution.state import InMemoryPaperStateStore
from exness_bot.signal_engine.models import SignalEmission, SignalKind, SignalResult
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME
from tests.fixtures.risk_data import make_xauusd_symbol
from tests.unit.test_paper_validation import _result, _service

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
FORBIDDEN = (
    "order_send",
    "TRADE_ACTION_DEAL",
    "TRADE_ACTION_PENDING",
    "TRADE_ACTION_SLTP",
    "TRADE_ACTION_REMOVE",
    "MT5Adapter",
    "TradingClient",
)
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


class TestExecutionContract:
    def test_intent_does_not_contain_guaranteed_fill(self) -> None:
        fields = set(ExecutionIntent.__annotations__)
        assert "fill_price" not in fields
        assert "requested_quantity" in fields
        assert "idempotency_key" in fields

    def test_ack_distinguishes_statuses(self) -> None:
        assert AckStatus.ACCEPTED != AckStatus.FILLED
        assert AckStatus.IN_FLIGHT != AckStatus.REJECTED
        assert AckStatus.UNKNOWN != AckStatus.FILLED
        assert AckStatus.UNKNOWN != AckStatus.REJECTED

    def test_paper_executor_generates_fill(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        result = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert result.status == ExecutionOutcome.FILLED
        assert result.order is not None
        # BUY = ask + slippage (fixture ask 2350.30, slip 1 point @ 0.01)
        assert result.order.fill_price == pytest.approx(2350.31)
        intent = paper.intents()[-1]
        assert intent.lifecycle == IntentLifecycle.FILLED
        assert intent.fill_price == result.order.fill_price

    def test_execution_port_is_broker_agnostic(self) -> None:
        source = inspect.getsource(ExecutionPort)
        for token in FORBIDDEN:
            assert token not in source
        assert "submit" in source


class TestLifecyclePersistence:
    def test_intent_persisted_before_side_effect(self) -> None:
        from exness_bot.paper_execution.models import PaperSnapshot

        seen_inflight: list[IntentLifecycle] = []

        class TrackingStore:
            def __init__(self) -> None:
                self._inner = InMemoryPaperStateStore()

            def load(self) -> PaperSnapshot:
                return self._inner.load()

            def save(self, snapshot: PaperSnapshot) -> None:
                if snapshot.intents:
                    seen_inflight.append(snapshot.intents[-1].lifecycle)
                self._inner.save(snapshot)

        clock = FakeClock(_at(12, 0))
        paper = _service(clock, store=TrackingStore())  # type: ignore[arg-type]
        paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert IntentLifecycle.IN_FLIGHT in seen_inflight
        first_intent_idx = next(
            i for i, life in enumerate(seen_inflight) if life == IntentLifecycle.IN_FLIGHT
        )
        later = seen_inflight[first_intent_idx:]
        assert later[0] == IntentLifecycle.IN_FLIGHT
        assert IntentLifecycle.FILLED in later

    def test_in_flight_survives_restart(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        paper = _service(clock, store=store)
        now = clock.now_utc()
        paper._executor.upsert_intent(
            IntentRecord(
                intent_id="paper-intent-9",
                idempotency_key="key-inflight",
                lifecycle=IntentLifecycle.IN_FLIGHT,
                created_at=now,
                updated_at=now,
                side="LONG",
                symbol=SYMBOL,
                requested_quantity=0.1,
                stop_loss=1.0,
                take_profit=2.0,
                ack_status=AckStatus.IN_FLIGHT.value,
            )
        )
        paper._persist()
        restarted = _service(clock, store=store)
        assert restarted._executor.has_blocking_intent("key-inflight")
        blocking = restarted.consume(_force_key(_at(11, 15), "key-inflight"))
        assert blocking.status == ExecutionOutcome.UNKNOWN

    def test_unknown_survives_restart(self) -> None:
        clock = FakeClock(_at(12, 0))
        store = InMemoryPaperStateStore()
        paper = _service(clock, store=store)
        now = clock.now_utc()
        paper._executor.upsert_intent(
            IntentRecord(
                intent_id="paper-intent-8",
                idempotency_key="key-unknown",
                lifecycle=IntentLifecycle.UNKNOWN,
                created_at=now,
                updated_at=now,
                side="LONG",
                symbol=SYMBOL,
                requested_quantity=0.1,
                stop_loss=1.0,
                take_profit=2.0,
                ack_status=AckStatus.UNKNOWN.value,
            )
        )
        paper._persist()
        restarted = _service(clock, store=store)
        assert any(
            item.lifecycle == IntentLifecycle.UNKNOWN for item in restarted.intents()
        )

    def test_duplicate_intent_is_deterministic(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        first = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        second = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert first.status == ExecutionOutcome.FILLED
        assert second.status == ExecutionOutcome.DUPLICATE
        assert len(paper.open_positions()) == 1


def _force_key(stamp: datetime, key: str) -> SignalResult:
    base = _sig(stamp)
    return SignalResult(
        symbol=base.symbol,
        timeframe=base.timeframe,
        candle_timestamp=base.candle_timestamp,
        signal=base.signal,
        generated_at=base.generated_at,
        source=base.source,
        strategy=base.strategy,
        indicators=base.indicators,
        reason=base.reason,
        conditions=base.conditions,
        idempotency_key=key,
        emission=base.emission,
        actionable=True,
        executable=True,
    )


class TestCatchupGate:
    def test_historical_signals_cannot_create_execution_burst(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        historical = [
            _sig(_at(10, 15), executable=False, emission=SignalEmission.INDICATOR_CATCHUP),
            _sig(_at(10, 30), executable=False, emission=SignalEmission.INDICATOR_CATCHUP),
            _sig(_at(10, 45), executable=False, emission=SignalEmission.INDICATOR_CATCHUP),
        ]
        outcomes = paper.consume_results(historical)
        assert all(item.status == ExecutionOutcome.CATCHUP_IGNORED for item in outcomes)
        assert paper.open_positions() == ()

    def test_only_latest_actionable_signal_can_execute(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        batch = [
            _sig(_at(11, 0), executable=True),
            _sig(_at(11, 15), executable=True),
            _sig(_at(11, 30), executable=True),
        ]
        outcomes = paper.consume_results(batch)
        filled = [item for item in outcomes if item.status == ExecutionOutcome.FILLED]
        ignored = [item for item in outcomes if item.status == ExecutionOutcome.CATCHUP_IGNORED]
        assert len(filled) == 1
        assert len(ignored) == 2
        assert len(paper.open_positions()) == 1
        signal_id = paper.open_positions()[0].signal_id
        assert _at(11, 30).isoformat() in signal_id

    def test_duplicate_latest_signal_does_not_execute_twice(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        latest = _sig(_at(11, 45))
        paper.consume_results([latest])
        again = paper.consume_results([latest])
        assert again[0].status == ExecutionOutcome.DUPLICATE
        assert len(paper.open_positions()) == 1

    def test_mixed_historical_and_latest(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        outcomes = paper.consume_results(
            [
                _sig(_at(10, 0), executable=False, emission=SignalEmission.INDICATOR_CATCHUP),
                _sig(_at(10, 15), executable=False, emission=SignalEmission.INDICATOR_CATCHUP),
                _sig(_at(11, 0), executable=True),
            ]
        )
        assert outcomes[-1].status == ExecutionOutcome.FILLED
        assert sum(1 for item in outcomes if item.status == ExecutionOutcome.FILLED) == 1

    def test_non_actionable_signals(self) -> None:
        clock = FakeClock(_at(12, 0))
        paper = _service(clock)
        outcomes = paper.consume_results(
            [
                _sig(_at(11, 0), kind=SignalKind.NO_SIGNAL, actionable=False, executable=False),
                _sig(_at(11, 15), kind=SignalKind.INVALID, actionable=False, executable=False),
            ]
        )
        assert all(item.status == ExecutionOutcome.IGNORED for item in outcomes)


class TestReadOnlyBoundary:
    def test_phase11_packages_cannot_import_mt5_trading(self) -> None:
        for package in ("candle_engine", "signal_engine", "paper_execution"):
            for path in (SRC / package).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        assert "mt5.adapter" not in (node.module or "")
                        assert "trading_client" not in (node.module or "")
                        for alias in node.names:
                            assert alias.name not in {
                                "MT5Adapter",
                                "TradingClient",
                                "MT5TradingClient",
                            }
                    if isinstance(node, ast.Call):
                        func = node.func
                        name = getattr(func, "attr", None) or getattr(func, "id", None)
                        assert name != "order_send"
        risk = ast.parse((SRC / "risk" / "manager.py").read_text(encoding="utf-8"))
        for node in ast.walk(risk):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                assert name != "order_send"

    def test_readonly_client_has_no_trading_mutation_api(self) -> None:
        from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient

        source = inspect.getsource(MT5ReadOnlyClient)
        assert "def order_send" not in source
        assert "TRADE_ACTION" not in source

    def test_broker_gateway_does_not_use_mt5_adapter(self) -> None:
        source = (SRC / "api" / "services" / "broker_gateway.py").read_text(encoding="utf-8")
        # Imports / calls — comments mentioning the forbidden names are also disallowed.
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                for alias in node.names:
                    imported.add(alias.name)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                imported.add(node.id)
        assert "adapter" not in imported
        assert "MT5Adapter" not in imported
        assert "TradingClient" not in imported
        assert "MT5ConnectionManager" in source
        assert "def order_send" not in source

    def test_signals_and_paper_commands_do_not_construct_trading_stack(self) -> None:
        cli_path = SRC / "cli.py"
        tree = ast.parse(cli_path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name not in {"handle_signals", "handle_paper", "handle_candles"}:
                continue
            source = ast.get_source_segment(cli_path.read_text(encoding="utf-8"), node) or ""
            assert "MT5Adapter" not in source
            assert "OrderManager" not in source
            assert "TradingClient" not in source
            assert "create_trading_engine" not in source


class TestValidation:
    def test_valid_quote(self) -> None:
        assert validate_quote(make_xauusd_symbol()).ok

    def test_invalid_bid(self) -> None:
        symbol = make_xauusd_symbol(bid=0.0)
        result = validate_quote(symbol)
        assert not result.ok
        assert result.code == ValidationCode.INVALID_BID

    def test_invalid_ask(self) -> None:
        symbol = make_xauusd_symbol(ask=0.0)
        result = validate_quote(symbol)
        assert not result.ok
        assert result.code == ValidationCode.INVALID_ASK

    def test_invalid_spread(self) -> None:
        symbol = make_xauusd_symbol(bid=10.0, ask=9.0)
        result = validate_quote(symbol)
        assert result.code == ValidationCode.INVALID_SPREAD

    def test_unavailable_symbol_metadata(self) -> None:
        assert validate_quote(None).code == ValidationCode.SYMBOL_UNAVAILABLE

    def test_invalid_volume(self) -> None:
        symbol = make_xauusd_symbol()
        assert validate_volume(0.0, symbol).code == ValidationCode.INVALID_VOLUME
        assert validate_volume(0.015, symbol).code == ValidationCode.INVALID_VOLUME

    def test_stops_freeze_unavailable_fails_closed(self) -> None:
        symbol = make_xauusd_symbol(stops_level=None, freeze_level=None)
        assert symbol.stops_level is None
        assert symbol.freeze_level is None
        result = validate_stops_metadata(symbol)
        assert not result.ok
        assert result.code == ValidationCode.STOPS_LEVEL_UNAVAILABLE

    def test_invalid_sl_tp_distance(self) -> None:
        symbol = make_xauusd_symbol().model_copy(update={"stops_level": 50, "freeze_level": 0})
        entry = 2350.0
        bad_sl = validate_sl_tp_distance(
            entry_price=entry,
            stop_loss=2349.9,
            take_profit=2360.0,
            side=SignalDirection.LONG,
            symbol=symbol,
        )
        assert bad_sl.code == ValidationCode.INVALID_SL_DISTANCE
        ok = validate_sl_tp_distance(
            entry_price=entry,
            stop_loss=2340.0,
            take_profit=2370.0,
            side=SignalDirection.LONG,
            symbol=symbol,
        )
        assert ok.ok


class TestSafetyModes:
    def test_execution_mode_live_fails(self) -> None:
        from exness_bot.config.live_enablement import assert_live_execution_not_operational

        live = Settings(_env_file=None, EXECUTION_MODE="live")
        with pytest.raises(RuntimeError):
            assert_live_execution_not_operational(live)

    def test_execution_mode_mt5_fails(self) -> None:
        with pytest.raises((ValidationError, ValueError)):
            Settings(_env_file=None, EXECUTION_MODE="mt5")

    def test_unsupported_modes_fail(self) -> None:
        for mode in ("real", "production", "demo"):
            with pytest.raises((ValidationError, ValueError)):
                Settings(_env_file=None, EXECUTION_MODE=mode)

    def test_no_live_executor_exists(self) -> None:
        """Phase 11 packages must not define MT5Executor; Phase 12.3 owns broker/mt5/executor.py."""
        assert ExecutionMode.PAPER in ExecutionMode
        assert ExecutionMode.LIVE in ExecutionMode
        phase11 = ("candle_engine", "signal_engine", "paper_execution", "risk", "domain")
        for package in phase11:
            for path in (SRC / package).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                assert "class MT5Executor" not in text
        executor_path = SRC / "broker" / "mt5" / "executor.py"
        assert executor_path.is_file()
        assert "class MT5Executor" in executor_path.read_text(encoding="utf-8")

    def test_no_new_order_send_in_phase11(self) -> None:
        for package in ("candle_engine", "signal_engine", "paper_execution", "domain"):
            for path in (SRC / package).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                        assert name != "order_send", path
                    if isinstance(node, ast.FunctionDef):
                        assert node.name != "order_send", path


class TestApiSafety:
    def test_no_mutation_order_endpoints(self) -> None:
        routes = (SRC / "api" / "routes" / "v1.py").read_text(encoding="utf-8")
        for path in ('"/order"', '"/trade"', '"/execute"', '"/position"'):
            assert path not in routes
        assert "@router.post" in routes  # account switch only
        assert "/accounts/active" in routes


class TestReconciliation:
    def test_paper_and_broker_remain_independent(self) -> None:
        local = (
            VirtualPosition(
                position_id="paper-1",
                symbol=SYMBOL,
                side=SignalDirection.LONG,
                volume=0.1,
                entry_price=2350.0,
                stop_loss=2340.0,
                take_profit=2370.0,
                opened_at=_at(11, 0),
                signal_id="sig",
                status=PositionStatus.OPEN,
            ),
        )
        report = reconcile_paper_vs_broker(local, ())
        assert report.overall == ReconcileStatus.MISSING_BROKER
        broker_only = reconcile_paper_vs_broker(
            (),
            [
                Position(
                    ticket=1,
                    symbol=SYMBOL,
                    volume=0.2,
                    direction=SignalDirection.SHORT,
                    open_price=2350.0,
                    current_price=2350.0,
                    stop_loss=2360.0,
                    take_profit=2330.0,
                    open_time=_at(11, 0),
                )
            ],
        )
        assert broker_only.overall == ReconcileStatus.MISSING_LOCAL
        # Paper rows are not mutated into broker rows
        assert local[0].position_id == "paper-1"
