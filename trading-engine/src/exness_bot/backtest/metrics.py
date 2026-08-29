"""Backtest performance metrics."""

from exness_bot.backtest.models import BacktestMetrics, EquityPoint, TradeRecord


def calculate_metrics(
    *,
    trades: list[TradeRecord],
    equity_curve: list[EquityPoint],
    initial_equity: float,
) -> BacktestMetrics:
    """Compute aggregate statistics from the trade journal and equity curve."""
    total_trades = len(trades)
    winners = [trade for trade in trades if trade.net_pnl > 0]
    losers = [trade for trade in trades if trade.net_pnl < 0]

    winning_trades = len(winners)
    losing_trades = len(losers)
    gross_profit = sum(trade.gross_pnl for trade in trades if trade.gross_pnl > 0)
    gross_loss = abs(sum(trade.gross_pnl for trade in trades if trade.gross_pnl < 0))
    net_profit = sum(trade.net_pnl for trade in trades)
    final_equity = equity_curve[-1].equity if equity_curve else initial_equity

    win_rate = winning_trades / total_trades if total_trades else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    expectancy = net_profit / total_trades if total_trades else 0.0
    average_win = gross_profit / winning_trades if winning_trades else 0.0
    average_loss = gross_loss / losing_trades if losing_trades else 0.0
    risk_reward = average_win / average_loss if average_loss > 0 else None

    max_dd, max_dd_pct = _maximum_drawdown(equity_curve, initial_equity)
    max_wins, max_losses = _consecutive_streaks(trades)

    return_pct = ((final_equity - initial_equity) / initial_equity) * 100.0

    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=round(win_rate, 6),
        gross_profit=round(gross_profit, 2),
        gross_loss=round(gross_loss, 2),
        net_profit=round(net_profit, 2),
        profit_factor=round(profit_factor, 4) if profit_factor is not None else None,
        expectancy=round(expectancy, 2),
        maximum_drawdown=round(max_dd, 2),
        maximum_drawdown_pct=round(max_dd_pct, 4),
        average_win=round(average_win, 2),
        average_loss=round(average_loss, 2),
        risk_reward=round(risk_reward, 4) if risk_reward is not None else None,
        max_consecutive_wins=max_wins,
        max_consecutive_losses=max_losses,
        initial_equity=round(initial_equity, 2),
        final_equity=round(final_equity, 2),
        return_pct=round(return_pct, 4),
    )


def _maximum_drawdown(
    equity_curve: list[EquityPoint],
    initial_equity: float,
) -> tuple[float, float]:
    if not equity_curve:
        return 0.0, 0.0

    peak = initial_equity
    max_dd = 0.0
    max_dd_pct = 0.0

    for point in equity_curve:
        peak = max(peak, point.equity)
        drawdown = peak - point.equity
        drawdown_pct = (drawdown / peak * 100.0) if peak > 0 else 0.0
        max_dd = max(max_dd, drawdown)
        max_dd_pct = max(max_dd_pct, drawdown_pct)

    return max_dd, max_dd_pct


def _consecutive_streaks(trades: list[TradeRecord]) -> tuple[int, int]:
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    for trade in trades:
        if trade.net_pnl > 0:
            current_wins += 1
            current_losses = 0
        elif trade.net_pnl < 0:
            current_losses += 1
            current_wins = 0
        else:
            current_wins = 0
            current_losses = 0

        max_wins = max(max_wins, current_wins)
        max_losses = max(max_losses, current_losses)

    return max_wins, max_losses
