"""Phase 11.6 architecture & safety — no live order_send, no MT5Executor."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from exness_bot.config.settings import ExecutionMode, Settings
from exness_bot.domain.clock import FakeClock
from exness_bot.paper_execution.contract import ExecutionIntent
from exness_bot.paper_execution.port import ExecutionPort
from exness_bot.signal_engine.models import SignalKind
from tests.unit.test_paper_validation import _event, _result, _service
from tests.unit.test_signal_engine import _buy_snapshot, _candle
from tests.unit.test_signal_engine import _engine as _signal_engine

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
FORBIDDEN = (
    "order_send",
    "TRADE_ACTION_DEAL",
    "TRADE_ACTION_PENDING",
    "TRADE_ACTION_SLTP",
    "TRADE_ACTION_REMOVE",
    "MT5Adapter",
    "TradingClient",
)


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 29, hour, minute, tzinfo=UTC)


def _package_sources(*names: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for name in names:
        for path in (SRC_ROOT / name).rglob("*.py"):
            rows.append((f"{name}/{path.name}", path.read_text(encoding="utf-8")))
    return rows


def _assert_no_trading_imports(label: str, source: str) -> None:
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "mt5.adapter" not in module, label
            assert "trading_client" not in module, label
            for alias in node.names:
                assert alias.name not in {
                    "MT5Adapter",
                    "TradingClient",
                    "MT5TradingClient",
                }, label
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            assert name != "order_send", label


class TestExecutionPortBrokerAgnostic:
    def test_execution_port_is_broker_agnostic(self) -> None:
        source = (SRC_ROOT / "paper_execution" / "port.py").read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in source
        assert hasattr(ExecutionPort, "submit")
        assert "fill_price" not in ExecutionIntent.__annotations__
        # Intent dataclass fields must not declare a guaranteed fill.
        assert all(
            name != "fill_price" for name in ExecutionIntent.__dataclass_fields__
        )


class TestDependencyDirection:
    def test_signal_engine_does_not_depend_on_execution(self) -> None:
        for label, source in _package_sources("signal_engine"):
            assert "paper_execution" not in source, label
            assert "PaperExecutor" not in source, label
            # Avoid matching the word in docstrings about the execution boundary.
            assert "from exness_bot.paper_execution" not in source, label
            _assert_no_trading_imports(label, source)

    def test_risk_manager_does_not_execute(self) -> None:
        manager = (SRC_ROOT / "risk" / "manager.py").read_text(encoding="utf-8")
        _assert_no_trading_imports("risk/manager.py", manager)
        assert "PaperExecutor" not in manager
        assert "def assess(" in manager

    def test_paper_executor_remains_broker_agnostic(self) -> None:
        for label, source in _package_sources("paper_execution"):
            _assert_no_trading_imports(label, source)


class TestCatchupAndSignals:
    def test_catchup_cannot_create_execution_burst(self) -> None:
        clock = FakeClock(_at(12, 0))
        signals = _signal_engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        history = [
            _candle(_at(10, 0), close=115.0),
            _candle(_at(10, 15), close=115.0),
            _candle(_at(10, 30), close=115.0),
            _candle(_at(10, 45), close=115.0),
            _candle(_at(11, 0), close=115.0),
        ]
        signals.warmup(history, now=clock.now_utc())
        missed = (
            _event(_candle(_at(11, 15), close=115.0)),
            _event(_candle(_at(11, 30), close=115.0)),
            _event(_candle(_at(11, 45), close=115.0)),
        )
        processed = signals.process_events(missed, now=clock.now_utc())
        paper = _service(clock)
        for item in processed.results:
            paper.consume(item)
        assert processed.catchup_count == 2
        assert len(processed.results) == 1
        assert len(paper.open_positions()) == 1
        assert paper.session().execution_count == 1

    def test_non_actionable_signal_cannot_execute(self) -> None:
        paper = _service(FakeClock(_at(12, 0)))
        hold = paper.consume(_result(_at(11, 15), SignalKind.NO_SIGNAL, actionable=False))
        invalid = paper.consume(
            _result(_at(11, 30), SignalKind.INVALID, actionable=False, atr=None)
        )
        assert hold.status.value == "IGNORED"
        assert invalid.status.value == "IGNORED"
        assert paper.open_positions() == ()

    def test_duplicate_signal_cannot_execute_twice(self) -> None:
        paper = _service(FakeClock(_at(12, 0)))
        first = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        second = paper.consume(_result(_at(11, 15), SignalKind.BUY))
        assert first.status.value == "FILLED"
        assert second.status.value == "DUPLICATE"
        assert len(paper.open_positions()) == 1


class TestExecutionModeFailClosed:
    def test_live_mode_is_not_enabled(self) -> None:
        from exness_bot.config.live_enablement import assert_live_execution_not_operational

        settings = Settings(_env_file=None, EXECUTION_MODE="paper")
        assert settings.execution_mode is ExecutionMode.PAPER
        live = Settings(_env_file=None, EXECUTION_MODE="live")
        assert live.execution_mode is ExecutionMode.LIVE
        with pytest.raises(RuntimeError):
            assert_live_execution_not_operational(live)

    def test_unsupported_execution_mode_fails_closed(self) -> None:
        from exness_bot.config.live_enablement import assert_live_execution_not_operational

        live = Settings(EXECUTION_MODE="live")
        with pytest.raises(RuntimeError):
            assert_live_execution_not_operational(live)
        with pytest.raises((ValidationError, ValueError)):
            Settings(EXECUTION_MODE="mt5")


class TestStaticSafety:
    def test_no_live_trading_api_in_phase_11_packages(self) -> None:
        for label, source in _package_sources("candle_engine", "signal_engine", "paper_execution"):
            _assert_no_trading_imports(label, source)
        risk = (SRC_ROOT / "risk" / "manager.py").read_text(encoding="utf-8")
        service = (SRC_ROOT / "paper_execution" / "service.py").read_text(encoding="utf-8")
        _assert_no_trading_imports("risk/manager.py", risk)
        _assert_no_trading_imports("paper_execution/service.py", service)


class TestPaperBrokerSeparation:
    def test_paper_and_broker_state_are_distinct(self, tmp_path: Path) -> None:
        from fastapi.testclient import TestClient

        from exness_bot.api.app import create_app
        from exness_bot.api.dependencies import get_read_service
        from exness_bot.api.services.read_service import ReadService
        from exness_bot.data.mock_provider import MockTradingDataProvider

        clock = FakeClock(_at(12, 0))
        execution = _service(clock)
        execution.consume(_result(_at(11, 15), SignalKind.BUY))
        settings = Settings()
        service = ReadService(
            settings,
            MockTradingDataProvider(settings),
            project_root=tmp_path,
            paper_execution=execution,
        )
        app = create_app()
        app.dependency_overrides[get_read_service] = lambda: service
        client = TestClient(app)
        paper = client.get("/api/v1/paper").json()["data"]
        broker = client.get("/api/v1/account").json()["data"]
        routes = (SRC_ROOT / "api" / "routes" / "v1.py").read_text(encoding="utf-8")
        client.close()
        assert paper["accountKind"] == "paper"
        assert paper["researchOnly"] is True
        assert paper["openPositions"] >= 1
        assert broker["balance"] != paper["balance"]
        assert '"/order"' not in routes
        assert '"/execute"' not in routes
