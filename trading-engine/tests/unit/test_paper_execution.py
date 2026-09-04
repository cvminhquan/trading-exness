"""Deterministic Paper Execution tests — no MT5 orders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.settings import Settings
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.enums import SignalDirection, Timeframe
from exness_bot.domain.models import Candle, IndicatorSnapshot
from exness_bot.paper_execution.models import (
    ExecutionOutcome,
    OrderStatus,
    PaperExitReason,
    PaperSnapshot,
    RejectionCode,
)
from exness_bot.paper_execution.port import ExecutionPort
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


def _snapshot(stamp: datetime, *, atr: float | None = 2.0) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        timestamp=stamp,
        ema_20=110.0,
        ema_50=105.0,
        ema_200=100.0,
        rsi_14=60.0,
        atr_14=atr,
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
        indicators=_snapshot(stamp, atr=atr),
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
    settings: Settings | None = None,
    config: BacktestConfig | None = None,
    symbol=None,
) -> ExecutionService:
    resolved_settings = settings or Settings()
    return ExecutionService(
        risk_manager=RiskManager(resolved_settings),
        store=store or InMemoryPaperStateStore(),
        settings=resolved_settings,
        config=config or BacktestConfig.from_settings(resolved_settings),
        symbol_info=symbol or make_xauusd_symbol(),
        clock=clock,
    )


class TestSignalConsumption:
    def test_buy_signal_opens_paper_position(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        outcome = service.consume(_result(_at(11, 15), SignalKind.BUY))
        assert outcome.status == ExecutionOutcome.FILLED
        assert len(service.open_positions()) == 1
        position = service.open_positions()[0]
        assert position.side == SignalDirection.LONG
        assert position.volume > 0
        assert position.volume != 0.01 or position.stop_loss is not None
        assert position.stop_loss < position.entry_price
        assert position.take_profit > position.entry_price

    def test_sell_signal_opens_paper_position(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        outcome = service.consume(_result(_at(11, 15), SignalKind.SELL))
        assert outcome.status == ExecutionOutcome.FILLED
        position = service.open_positions()[0]
        assert position.side == SignalDirection.SHORT
        assert position.stop_loss > position.entry_price
        assert position.take_profit < position.entry_price

    def test_no_signal_ignored(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        outcome = service.consume(_result(_at(11, 15), SignalKind.NO_SIGNAL))
        assert outcome.status == ExecutionOutcome.IGNORED
        assert service.open_positions() == ()

    def test_invalid_ignored(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        outcome = service.consume(_result(_at(11, 15), SignalKind.INVALID, actionable=False))
        assert outcome.status == ExecutionOutcome.IGNORED
        assert service.open_positions() == ()

    def test_duplicate_signal_ignored(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        first = service.consume(_result(_at(11, 15), SignalKind.BUY))
        second = service.consume(_result(_at(11, 15), SignalKind.BUY))
        assert first.status == ExecutionOutcome.FILLED
        assert second.status == ExecutionOutcome.DUPLICATE
        assert len(service.open_positions()) == 1


class TestRiskGates:
    def test_max_open_positions(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock, settings=Settings(MAX_OPEN_POSITIONS=1))
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        later = service.consume(_result(_at(11, 30), SignalKind.BUY))
        assert later.status == ExecutionOutcome.REJECTED
        assert later.rejection_code == RejectionCode.MAX_OPEN_POSITIONS
        assert len(service.open_positions()) == 1

    def test_max_daily_loss(self) -> None:
        clock = FakeClock(_at(12, 0))
        snapshot = PaperSnapshot.initial(10_000.0)
        snapshot = snapshot.with_balances(
            cash_balance=9_700.0,
            peak_equity=10_000.0,
            day_start_equity=10_000.0,
        )
        service = _service(clock, store=InMemoryPaperStateStore(snapshot))
        outcome = service.consume(_result(_at(11, 45), SignalKind.BUY))
        assert outcome.status == ExecutionOutcome.REJECTED
        assert outcome.rejection_code == RejectionCode.MAX_DAILY_LOSS
        assert service.open_positions() == ()

    def test_max_drawdown(self) -> None:
        clock = FakeClock(_at(12, 0))
        snapshot = PaperSnapshot.initial(10_000.0)
        snapshot = snapshot.with_balances(
            cash_balance=9_400.0,
            peak_equity=10_000.0,
            day_start_equity=9_400.0,
        )
        service = _service(clock, store=InMemoryPaperStateStore(snapshot))
        outcome = service.consume(_result(_at(11, 15), SignalKind.BUY))
        assert outcome.status == ExecutionOutcome.REJECTED
        assert outcome.rejection_code == RejectionCode.MAX_DRAWDOWN

    def test_max_lot_size(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(
            clock,
            settings=Settings(MAX_POSITION_LOTS=0.01, RISK_PER_TRADE_PCT=0.5),
            symbol=make_xauusd_symbol(),
        )
        # Tiny max lots with 10k equity / 0.5% / ATR 2 usually sizes above 0.01
        outcome = service.consume(_result(_at(11, 15), SignalKind.BUY, atr=0.2))
        if outcome.status == ExecutionOutcome.FILLED:
            assert service.open_positions()[0].volume <= 0.01
        else:
            assert outcome.rejection_code in {
                RejectionCode.POSITION_SIZE_LIMIT,
                RejectionCode.INVALID_RISK,
            }

    def test_invalid_sl(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        outcome = service.consume(_result(_at(11, 15), SignalKind.BUY, atr=None))
        assert outcome.status == ExecutionOutcome.REJECTED
        assert outcome.rejection_code == RejectionCode.INVALID_SL
        assert service.open_positions() == ()

    def test_position_sizing_depends_on_equity(self) -> None:
        clock = FakeClock(_at(12, 0))
        small = _service(clock)
        small.consume(_result(_at(11, 15), SignalKind.BUY))
        vol_small = small.open_positions()[0].volume
        rich = PaperSnapshot.initial(50_000.0)
        large = _service(clock, store=InMemoryPaperStateStore(rich))
        large.consume(_result(_at(11, 15), SignalKind.BUY))
        vol_large = large.open_positions()[0].volume
        assert vol_large > vol_small


class TestCostsAndExits:
    def test_spread_and_slippage_on_fill(self) -> None:
        clock = FakeClock(_at(12, 0))
        config = BacktestConfig(spread_points=20, slippage_points=1.0, point=0.01)
        symbol = make_xauusd_symbol(bid=2350.10, ask=2350.30, spread=20)
        service = _service(clock, config=config, symbol=symbol)
        outcome = service.consume(_result(_at(11, 15), SignalKind.BUY))
        order = outcome.order
        assert order is not None
        assert order.requested_price == 2350.20
        assert order.fill_price > order.requested_price
        assert abs(order.fill_price - (2350.30 + 0.01)) < 1e-9

    def test_commission_affects_net_pnl(self) -> None:
        clock = FakeClock(_at(12, 0))
        config = BacktestConfig(commission_per_lot=10.0, spread_points=20, slippage_points=1.0)
        service = _service(clock, config=config)
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        tp_candle = _candle(
            _at(11, 30),
            close=position.take_profit,
            high=position.take_profit + 1,
            low=position.entry_price,
        )
        closed = service.on_closed_candle(tp_candle)
        assert closed is not None
        assert closed.commission > 0
        assert closed.net_pnl == round(closed.gross_pnl - closed.commission - closed.swap, 2)

    def test_swap_on_calendar_day(self) -> None:
        clock = FakeClock(_at(12, 0))
        config = BacktestConfig(swap_per_lot_per_day=1.0, commission_per_lot=0.0)
        service = _service(clock, config=config)
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        next_day = _candle(
            _at(11, 30, day=30),
            close=position.take_profit,
            high=position.take_profit + 1,
            low=position.entry_price,
        )
        closed = service.on_closed_candle(next_day)
        assert closed is not None
        assert closed.swap > 0

    def test_sl_exit(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        sl_candle = _candle(
            _at(11, 30),
            close=position.stop_loss,
            high=position.entry_price,
            low=position.stop_loss - 0.5,
        )
        closed = service.on_closed_candle(sl_candle)
        assert closed is not None
        assert closed.exit_reason == PaperExitReason.SL
        assert service.open_positions() == ()

    def test_tp_exit(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        tp_candle = _candle(
            _at(11, 30),
            close=position.take_profit,
            high=position.take_profit + 0.5,
            low=position.entry_price,
        )
        closed = service.on_closed_candle(tp_candle)
        assert closed is not None
        assert closed.exit_reason == PaperExitReason.TP

    def test_same_candle_sl_and_tp_uses_sl_first(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        both = _candle(
            _at(11, 30),
            close=position.entry_price,
            high=position.take_profit + 1,
            low=position.stop_loss - 1,
        )
        closed = service.on_closed_candle(both)
        assert closed is not None
        assert closed.exit_reason == PaperExitReason.SL

    def test_unrealized_and_realized_pnl_and_equity(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        account = service.account_state()
        assert account.initial_balance == 10_000.0
        assert account.balance == 10_000.0
        service.mark_to_market(make_xauusd_symbol(bid=2351.0, ask=2351.2))
        marked = service.account_state()
        assert marked.unrealized_pnl != 0.0
        assert abs(marked.equity - (marked.balance + marked.unrealized_pnl)) < 1e-9
        position = service.open_positions()[0]
        tp_candle = _candle(
            _at(11, 30),
            close=position.take_profit,
            high=position.take_profit + 0.5,
            low=position.entry_price,
        )
        service.on_closed_candle(tp_candle)
        closed_acct = service.account_state()
        assert closed_acct.unrealized_pnl == 0.0
        assert closed_acct.realized_pnl != 0.0
        assert abs(closed_acct.equity - closed_acct.balance) < 1e-9
        assert closed_acct.balance == round(10_000.0 + closed_acct.realized_pnl, 2)

    def test_drawdown_tracks_peak(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        position = service.open_positions()[0]
        sl_candle = _candle(
            _at(11, 30),
            close=position.stop_loss,
            high=position.entry_price,
            low=position.stop_loss - 0.5,
        )
        service.on_closed_candle(sl_candle)
        account = service.account_state()
        assert account.drawdown_pct > 0
        assert account.peak_equity >= account.equity


class TestPersistenceAndCatchup:
    def test_restart_persistence(self, tmp_path: Path) -> None:
        clock = FakeClock(_at(12, 0))
        store = FilePaperStateStore(tmp_path / "paper.json")
        first = _service(clock, store=store)
        first.consume(_result(_at(11, 15), SignalKind.BUY))
        pos_id = first.open_positions()[0].position_id
        second = _service(clock, store=store)
        assert len(second.open_positions()) == 1
        assert second.open_positions()[0].position_id == pos_id

    def test_duplicate_after_restart(self, tmp_path: Path) -> None:
        clock = FakeClock(_at(12, 0))
        store = FilePaperStateStore(tmp_path / "paper.json")
        first = _service(clock, store=store)
        first.consume(_result(_at(11, 15), SignalKind.BUY))
        second = _service(clock, store=store)
        replay = second.consume(_result(_at(11, 15), SignalKind.BUY))
        assert replay.status == ExecutionOutcome.DUPLICATE
        assert len(second.open_positions()) == 1

    def test_catchup_does_not_create_burst(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        stale = (
            _result(_at(10, 30), SignalKind.BUY, actionable=False),
            _result(_at(10, 45), SignalKind.BUY, actionable=False),
            _result(_at(11, 0), SignalKind.BUY, actionable=True),
        )
        outcomes = [service.consume(item) for item in stale]
        filled = [item for item in outcomes if item.status == ExecutionOutcome.FILLED]
        assert len(filled) == 1
        assert len(service.open_positions()) == 1

    def test_chronological_processing(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        service.consume(_result(_at(11, 15), SignalKind.BUY))
        opened = service.open_positions()[0].opened_at
        position = service.open_positions()[0]
        later = _candle(
            _at(11, 45),
            close=position.take_profit,
            high=position.take_profit + 1,
            low=position.entry_price,
        )
        earlier = _candle(
            _at(11, 30),
            close=position.entry_price,
            high=position.entry_price + 0.1,
            low=position.entry_price - 0.1,
        )
        assert service.on_closed_candle(earlier) is None
        closed = service.on_closed_candle(later)
        assert closed is not None
        assert closed.exit_timestamp >= opened


class TestCriticalEndToEnd:
    def test_buy_then_tp_updates_journal_and_equity(self) -> None:
        clock = FakeClock(_at(12, 0))
        service = _service(clock)
        filled = service.consume(_result(_at(11, 15), SignalKind.BUY))
        assert filled.status == ExecutionOutcome.FILLED
        assert filled.order is not None
        assert filled.order.status == OrderStatus.FILLED
        assert len(service.open_positions()) == 1
        position = service.open_positions()[0]
        tp_candle = _candle(
            _at(11, 30),
            close=position.take_profit,
            high=position.take_profit + 0.5,
            low=position.entry_price,
        )
        exit_record = service.on_closed_candle(tp_candle)
        assert exit_record is not None
        assert exit_record.exit_reason == PaperExitReason.TP
        assert service.open_positions() == ()
        journal = service.journal()
        assert len(journal) == 1
        account = service.account_state()
        assert account.realized_pnl == journal[0].net_pnl
        assert account.equity == round(10_000.0 + journal[0].net_pnl, 2)


class TestSafetyAndDeterminism:
    def test_paper_executor_cannot_call_mt5_trading_apis(self) -> None:
        import ast

        package = Path(__file__).resolve().parents[2] / "src" / "exness_bot" / "paper_execution"
        forbidden_names = {
            "order_send",
            "MT5Adapter",
            "MT5TradingClient",
            "TradingClient",
        }
        forbidden_consts = {
            "TRADE_ACTION_DEAL",
            "TRADE_ACTION_PENDING",
            "TRADE_ACTION_SLTP",
            "TRADE_ACTION_REMOVE",
        }
        for path in package.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                    assert name not in forbidden_names, path.name
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    assert node.id not in forbidden_names, path.name
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    assert node.value not in forbidden_consts, path.name
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        assert alias.name not in forbidden_names, path.name

    def test_execution_interface_does_not_depend_on_mt5(self) -> None:
        import inspect

        from exness_bot.paper_execution import port as port_mod

        source = inspect.getsource(port_mod)
        assert "MetaTrader" not in source
        assert "import MetaTrader" not in source
        assert hasattr(ExecutionPort, "submit")
        assert not hasattr(ExecutionPort, "close_position")
        assert not hasattr(ExecutionPort, "get_open_positions")
        assert not hasattr(ExecutionPort, "get_account_state")
        assert "PaperAccount" not in str(ExecutionPort.submit.__annotations__)
        assert "VirtualPosition" not in str(ExecutionPort.submit.__annotations__)

    def test_signal_engine_remains_independent_of_execution(self) -> None:
        package = Path(__file__).resolve().parents[2] / "src" / "exness_bot" / "signal_engine"
        for path in package.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "paper_execution" not in source
            assert "PaperExecutor" not in source

    def test_deterministic_execution(self) -> None:
        clock = FakeClock(_at(12, 0))
        a = _service(clock)
        b = _service(clock)
        ra = a.consume(_result(_at(11, 15), SignalKind.BUY))
        rb = b.consume(_result(_at(11, 15), SignalKind.BUY))
        assert ra.order is not None and rb.order is not None
        assert ra.order.fill_price == rb.order.fill_price
        assert ra.order.volume == rb.order.volume
        assert a.open_positions()[0].stop_loss == b.open_positions()[0].stop_loss

    def test_unsupported_execution_mode_fails_closed(self) -> None:
        from pydantic import ValidationError

        from exness_bot.config.live_enablement import assert_live_execution_not_operational
        from exness_bot.config.settings import Settings

        live = Settings(_env_file=None, EXECUTION_MODE="live")
        try:
            assert_live_execution_not_operational(live)
        except RuntimeError:
            pass
        else:
            raise AssertionError("live must not be operational")
        try:
            Settings(_env_file=None, EXECUTION_MODE="mt5")
        except (ValidationError, ValueError):
            pass
        else:
            raise AssertionError("mt5 EXECUTION_MODE must fail closed")
