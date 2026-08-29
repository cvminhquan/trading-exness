"""Tests for backtest metrics."""

from datetime import UTC, datetime

from exness_bot.backtest.metrics import calculate_metrics
from exness_bot.backtest.models import EquityPoint, ExitReason, TradeRecord
from exness_bot.domain.enums import SignalDirection


def _trade(trade_id: int, net_pnl: float) -> TradeRecord:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    return TradeRecord(
        trade_id=trade_id,
        direction=SignalDirection.LONG,
        volume=0.01,
        entry_price=2350.0,
        exit_price=2360.0 if net_pnl > 0 else 2340.0,
        stop_loss=2338.0,
        take_profit=2374.0,
        entry_time=ts,
        exit_time=ts,
        exit_reason=ExitReason.TAKE_PROFIT if net_pnl > 0 else ExitReason.STOP_LOSS,
        gross_pnl=net_pnl,
        commission=0.0,
        net_pnl=net_pnl,
        bars_held=1,
        signal_reason="test",
    )


class TestBacktestMetrics:
    def test_calculates_core_metrics(self) -> None:
        trades = [_trade(1, 100.0), _trade(2, -50.0), _trade(3, 80.0)]
        equity_curve = [
            EquityPoint(timestamp=datetime(2026, 1, 1, tzinfo=UTC), equity=10_000.0, bar_index=0),
            EquityPoint(timestamp=datetime(2026, 1, 2, tzinfo=UTC), equity=10_130.0, bar_index=1),
        ]
        metrics = calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_equity=10_000.0,
        )
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.net_profit == 130.0
        assert metrics.profit_factor == 3.6
        assert metrics.max_consecutive_wins == 1
        assert metrics.max_consecutive_losses == 1

    def test_empty_trades(self) -> None:
        metrics = calculate_metrics(trades=[], equity_curve=[], initial_equity=10_000.0)
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.profit_factor is None
