"""Tests for virtual order execution."""

from datetime import UTC, datetime

from exness_bot.backtest.config import BacktestConfig
from exness_bot.backtest.models import ExitReason
from exness_bot.backtest.simulator import VirtualExecutor
from exness_bot.domain.enums import OrderType, SignalAction, SignalDirection, Timeframe
from exness_bot.domain.models import (
    ApprovedOrderPlan,
    Candle,
    IndicatorSnapshot,
    OrderRequest,
    Signal,
)


def _candle(
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _plan(*, direction: SignalDirection = SignalDirection.LONG) -> ApprovedOrderPlan:
    signal = Signal.create(
        action=SignalAction.BUY if direction == SignalDirection.LONG else SignalAction.SELL,
        strategy_name="test",
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        entry_price=2350.0,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        indicators=IndicatorSnapshot(
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            atr_14=2.0,
        ),
        reason="test",
    )
    return ApprovedOrderPlan(
        signal=signal,
        volume=0.01,
        stop_loss=2338.0 if direction == SignalDirection.LONG else 2362.0,
        take_profit=2374.0 if direction == SignalDirection.LONG else 2338.0,
        order_request=OrderRequest(
            symbol="XAUUSD",
            volume=0.01,
            order_type=OrderType.MARKET,
            direction=direction,
            stop_loss=2338.0,
            take_profit=2374.0,
        ),
    )


def _entry_candle() -> Candle:
    return _candle(open_price=2350.0, high=2352.0, low=2348.0, close=2350.0)


class TestVirtualExecutor:
    def test_long_entry_includes_half_spread(self) -> None:
        config = BacktestConfig(spread_points=20, slippage_points=0.0)
        executor = VirtualExecutor(config)
        position = executor.fill_entry(_plan(), _entry_candle())
        assert position.entry_price == 2350.10

    def test_long_stop_loss_hit(self) -> None:
        executor = VirtualExecutor(BacktestConfig())
        position = executor.fill_entry(_plan(), _entry_candle())
        position = executor.with_bar_index(position, 1)
        exit_event = executor.check_exit(
            position,
            _candle(open_price=2340.0, high=2341.0, low=2337.0, close=2339.0),
            bar_index=2,
        )
        assert exit_event is not None
        assert exit_event.exit_reason == ExitReason.STOP_LOSS

    def test_long_take_profit_hit(self) -> None:
        executor = VirtualExecutor(BacktestConfig())
        position = executor.with_bar_index(
            executor.fill_entry(_plan(), _entry_candle()),
            1,
        )
        exit_event = executor.check_exit(
            position,
            _candle(open_price=2370.0, high=2375.0, low=2369.0, close=2374.0),
            bar_index=2,
        )
        assert exit_event is not None
        assert exit_event.exit_reason == ExitReason.TAKE_PROFIT

    def test_same_bar_sl_tp_prefers_stop_loss(self) -> None:
        executor = VirtualExecutor(BacktestConfig())
        position = executor.fill_entry(_plan(), _entry_candle())
        exit_event = executor.check_exit(
            position,
            _candle(open_price=2350.0, high=2380.0, low=2330.0, close=2350.0),
            bar_index=2,
        )
        assert exit_event is not None
        assert exit_event.exit_reason == ExitReason.STOP_LOSS

    def test_trade_pnl_for_winning_long(self) -> None:
        executor = VirtualExecutor(BacktestConfig(commission_per_lot=0.0))
        position = executor.with_bar_index(
            executor.fill_entry(_plan(), _entry_candle()),
            1,
        )
        exit_event = executor.check_exit(
            position,
            _candle(open_price=2370.0, high=2375.0, low=2369.0, close=2374.0),
            bar_index=2,
        )
        assert exit_event is not None
        trade = executor.build_trade(
            trade_id=1,
            position=position,
            exit_event=exit_event,
            exit_bar_index=2,
            signal_reason="test",
        )
        assert trade.net_pnl > 0
