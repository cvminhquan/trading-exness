"""Phase 11.4 paper validation — pipeline, session, disconnect, SELL exits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from exness_bot.api.app import create_app
from exness_bot.api.dependencies import get_read_service
from exness_bot.api.services.read_service import ReadService
from exness_bot.backtest.config import BacktestConfig
from exness_bot.candle_engine.events import ClosedCandleEvent
from exness_bot.config.settings import Settings
from exness_bot.data.mock_provider import MockTradingDataProvider
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.enums import SignalDirection, Timeframe
from exness_bot.domain.models import Candle, IndicatorSnapshot, Tick
from exness_bot.paper_execution.factory import refresh_execution_quote
from exness_bot.paper_execution.loop import process_closed_candles
from exness_bot.paper_execution.models import ExecutionOutcome, PaperExitReason, RejectionCode
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.paper_execution.state import FilePaperStateStore, InMemoryPaperStateStore
from exness_bot.risk.manager import RiskManager
from exness_bot.signal_engine.models import SignalEmission, SignalKind, SignalResult
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME
from tests.fixtures.risk_data import make_xauusd_symbol

SYMBOL = "XAUUSD"
TF = Timeframe.M15
STRATEGY = STRATEGY_NAME


def _at(hour: int, minute: int, day: int = 29) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


def _candle(
    stamp: datetime,
    *,
    close: float = 2350.0,
    high: float | None = None,
    low: float | None = None,
) -> Candle:
    high = close + 1.0 if high is None else high
    low = close - 1.0 if low is None else low
    return Candle(
        symbol=SYMBOL,
        timeframe=TF,
        timestamp=stamp,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        spread=20,
    )


def _result(
    stamp: datetime,
    kind: SignalKind,
    *,
    actionable: bool | None = None,
    atr: float | None = 2.0,
) -> SignalResult:
    if actionable is None:
        actionable = kind in {SignalKind.BUY, SignalKind.SELL}
    return SignalResult(
        symbol=SYMBOL,
        timeframe=TF.value,
        candle_timestamp=stamp,
        signal=kind,
        generated_at=stamp + timedelta(minutes=15),
        source="TEST",
        strategy=STRATEGY,
        indicators=IndicatorSnapshot(
            timestamp=stamp,
            ema_20=110.0,
            ema_50=105.0,
            ema_200=100.0,
            rsi_14=60.0,
            atr_14=atr,
        ),
        reason="test",
        conditions=(),
        idempotency_key=f"{SYMBOL}|{TF.value}|{stamp.isoformat()}|{STRATEGY}",
        emission=SignalEmission.SIGNAL_EMISSION,
        actionable=actionable,
        executable=actionable,
    )


def _service(
    clock: FakeClock,
    *,
    store: InMemoryPaperStateStore | FilePaperStateStore | None = None,
) -> ExecutionService:
    settings = Settings()
    return ExecutionService(
        risk_manager=RiskManager(settings),
        store=store or InMemoryPaperStateStore(),
        settings=settings,
        config=BacktestConfig.from_settings(settings),
        symbol_info=make_xauusd_symbol(),
        clock=clock,
    )


def _event(candle: Candle) -> ClosedCandleEvent:
    return ClosedCandleEvent(
        candle=candle,
        detected_at=candle.timestamp,
        source="TEST",
        idempotency_key=f"{candle.symbol}|{candle.timeframe.value}|{candle.timestamp.isoformat()}",
    )


class _StubSignals:
    def __init__(self, results: tuple[SignalResult, ...]) -> None:
        self._results = results

    def process_events(self, events: object) -> SimpleNamespace:
        del events
        return SimpleNamespace(results=self._results)


class TestClosedCandlePipeline:
    def test_closed_candle_signal_paper_fill(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        stamp = _at(11, 15)
        process_closed_candles(
            [_event(_candle(stamp))],
            _StubSignals((_result(stamp, SignalKind.BUY),)),
            service,
        )
        assert len(service.open_positions()) == 1
        session = service.session()
        assert session.execution_count == 1
        assert session.signal_count == 1
        assert session.candles_processed == 1
        assert session.session_id


class TestActionableAndDuplicates:
    def test_actionable_false_does_not_execute(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        outcome = service.consume(_result(_at(11, 15), SignalKind.BUY, actionable=False))
        assert outcome.status == ExecutionOutcome.IGNORED
        assert service.open_positions() == ()
        assert service.session().execution_count == 0

    def test_duplicate_signal_no_second_fill(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        first = service.consume(_result(_at(11, 15), SignalKind.BUY))
        second = service.consume(_result(_at(11, 15), SignalKind.BUY))
        assert first.status == ExecutionOutcome.FILLED
        assert second.status == ExecutionOutcome.DUPLICATE
        assert len(service.open_positions()) == 1

    def test_risk_rejection_does_not_open(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        later = service.consume(_result(_at(11, 30), SignalKind.BUY))
        assert later.status == ExecutionOutcome.REJECTED
        assert later.rejection_code == RejectionCode.MAX_OPEN_POSITIONS
        assert len(service.open_positions()) == 1
        assert service.session().rejected_count == 1


class TestExits:
    def test_buy_then_tp(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        closed = service.on_closed_candle(
            _candle(
                _at(11, 30),
                close=position.take_profit,
                high=position.take_profit + 0.5,
                low=position.entry_price,
            )
        )
        assert closed is not None
        assert closed.exit_reason == PaperExitReason.TP
        assert service.open_positions() == ()

    def test_sell_then_tp(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.SELL))
        position = service.open_positions()[0]
        assert position.side == SignalDirection.SHORT
        closed = service.on_closed_candle(
            _candle(
                _at(11, 30),
                close=position.take_profit,
                high=position.entry_price,
                low=position.take_profit - 0.5,
            )
        )
        assert closed is not None
        assert closed.exit_reason == PaperExitReason.TP

    def test_buy_then_sl(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        closed = service.on_closed_candle(
            _candle(
                _at(11, 30),
                close=position.stop_loss,
                high=position.entry_price,
                low=position.stop_loss - 0.5,
            )
        )
        assert closed is not None
        assert closed.exit_reason == PaperExitReason.SL

    def test_sell_then_sl(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.SELL))
        position = service.open_positions()[0]
        closed = service.on_closed_candle(
            _candle(
                _at(11, 30),
                close=position.stop_loss,
                high=position.stop_loss + 0.5,
                low=position.entry_price,
            )
        )
        assert closed is not None
        assert closed.exit_reason == PaperExitReason.SL

    def test_same_candle_sl_first(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        closed = service.on_closed_candle(
            _candle(
                _at(11, 30),
                close=position.entry_price,
                high=position.take_profit + 1,
                low=position.stop_loss - 1,
            )
        )
        assert closed is not None
        assert closed.exit_reason == PaperExitReason.SL


class TestPnlAndEquity:
    def test_unrealized_uses_bid_for_buy(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        service.mark_to_market(make_xauusd_symbol(bid=2351.0, ask=2351.4))
        position = service.open_positions()[0]
        assert position.current_price == 2351.0
        assert service.account_state().unrealized_pnl != 0.0

    def test_unrealized_uses_ask_for_sell(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.SELL))
        service.mark_to_market(make_xauusd_symbol(bid=2348.0, ask=2348.4))
        position = service.open_positions()[0]
        assert position.current_price == 2348.4
        assert service.account_state().unrealized_pnl != 0.0

    def test_realized_pnl_and_equity(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        service.on_closed_candle(
            _candle(
                _at(11, 30),
                close=position.take_profit,
                high=position.take_profit + 0.5,
                low=position.entry_price,
            )
        )
        account = service.account_state()
        assert account.unrealized_pnl == 0.0
        assert account.realized_pnl != 0.0
        assert account.equity == round(10_000.0 + account.realized_pnl, 2)

    def test_drawdown_after_sl(self) -> None:
        service = _service(FakeClock(_at(12, 0)))
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        service.on_closed_candle(
            _candle(
                _at(11, 30),
                close=position.stop_loss,
                high=position.entry_price,
                low=position.stop_loss - 0.5,
            )
        )
        assert service.account_state().drawdown_pct > 0


class TestPersistenceAndDisconnect:
    def test_restart_keeps_session_and_position(self, tmp_path: Path) -> None:
        clock = FakeClock(_at(12, 0))
        store = FilePaperStateStore(tmp_path / "paper.json")
        first = _service(clock, store=store)
        first.consume(_result(_at(11, 15), SignalKind.BUY))
        session_id = first.session().session_id
        pos_id = first.open_positions()[0].position_id
        second = _service(clock, store=store)
        assert second.session().session_id == session_id
        assert second.open_positions()[0].position_id == pos_id

    def test_restart_does_not_duplicate_execution(self, tmp_path: Path) -> None:
        clock = FakeClock(_at(12, 0))
        store = FilePaperStateStore(tmp_path / "paper.json")
        _service(clock, store=store).consume(_result(_at(11, 15), SignalKind.BUY))
        replay = _service(clock, store=store).consume(_result(_at(11, 15), SignalKind.BUY))
        assert replay.status == ExecutionOutcome.DUPLICATE

    def test_broker_disconnect_does_not_reset_paper_state(self, tmp_path: Path) -> None:
        clock = FakeClock(_at(12, 0))
        store = FilePaperStateStore(tmp_path / "paper.json")
        first = _service(clock, store=store)
        first.consume(_result(_at(11, 15), SignalKind.BUY))
        pos_id = first.open_positions()[0].position_id
        cash = first.account_state().balance
        recovered = _service(clock, store=store)

        class _DeadQuotes:
            def get_tick(self, symbol: str | None = None) -> Tick | None:
                del symbol
                return None

        refresh_execution_quote(recovered, Settings(), _DeadQuotes())  # type: ignore[arg-type]
        assert recovered.open_positions()[0].position_id == pos_id
        assert recovered.account_state().balance == cash
        assert recovered.session().session_id == first.session().session_id


class TestSafety:
    def test_phase_11_packages_have_no_trading_api(self) -> None:
        import ast

        root = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
        forbidden_names = {"order_send", "MT5Adapter", "TradingClient", "MT5TradingClient"}
        for package_name in ("paper_execution", "signal_engine", "candle_engine"):
            for path in (root / package_name).glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                        assert name not in forbidden_names, f"{package_name}/{path.name}"
                    if isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            assert alias.name not in forbidden_names, f"{package_name}/{path.name}"

    def test_api_lifespan_is_exclusive(self) -> None:
        source = (
            Path(__file__).resolve().parents[2] / "src" / "exness_bot" / "api" / "app.py"
        ).read_text(encoding="utf-8")
        paper_idx = source.index("if settings.paper_execution_enabled:")
        signal_idx = source.index("if settings.signal_engine_enabled:")
        candle_idx = source.index("if settings.candle_engine_enabled:")
        assert paper_idx < signal_idx < candle_idx
        assert "return" in source[paper_idx:signal_idx]
        assert "return" in source[signal_idx:candle_idx]


class TestPaperApiSession:
    def test_paper_payload_distinct_from_broker(self, tmp_path: Path) -> None:
        settings = Settings()
        clock = FakeClock(_at(12, 0))
        execution = _service(clock)
        execution.consume(_result(_at(11, 15), SignalKind.BUY))
        service = ReadService(
            settings,
            MockTradingDataProvider(settings),
            project_root=tmp_path,
            paper_execution=execution,
        )
        app = create_app()
        app.dependency_overrides[get_read_service] = lambda: service
        client = TestClient(app)
        status = client.get("/api/v1/status").json()["data"]
        assert "candleEngine" in status
        assert "signalEngine" in status
        assert "paperExecution" in status
        assert status["paperExecution"]["accountKind"] == "paper"
        paper = client.get("/api/v1/paper").json()["data"]
        assert paper["accountKind"] == "paper"
        assert paper["researchOnly"] is True
        assert paper["sessionId"]
        assert paper["lastSignal"] == "BUY"
        assert paper["executionCount"] == 1
        assert len(paper["positions"]) == 1
        broker = client.get("/api/v1/account").json()["data"]
        assert broker["balance"] != paper["balance"] or paper["openPositions"] >= 1
        client.close()
