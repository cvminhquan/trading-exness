"""Extended baseline analytics from backtest reports."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from pydantic import BaseModel

from exness_bot.backtest.models import BacktestReport, EquityPoint, ExitReason, TradeRecord
from exness_bot.domain.enums import SignalDirection


class DirectionStats(BaseModel):
    """Performance stats for one trade direction."""

    trades: int
    win_rate: float
    profit_factor: float | None
    net_profit: float
    expectancy: float
    maximum_drawdown: float

    model_config = {"frozen": True}


class PeriodStats(BaseModel):
    """Aggregated stats for a calendar period."""

    period: str
    trades: int
    net_profit: float
    win_rate: float

    model_config = {"frozen": True}


class ExitDistribution(BaseModel):
    """Counts by exit reason."""

    stop_loss: int
    take_profit: int
    end_of_data: int

    model_config = {"frozen": True}


class DrawdownAnalysis(BaseModel):
    """Drawdown curve analytics."""

    peak_equity: float
    maximum_drawdown: float
    maximum_drawdown_pct: float
    average_drawdown: float
    average_drawdown_pct: float
    recovery_periods: int
    max_recovery_bars: int

    model_config = {"frozen": True}


class BaselineAnalysis(BaseModel):
    """Full baseline research report derived from a backtest."""

    # Trade statistics
    total_trades: int
    long_trades: int
    short_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    average_trade: float
    average_winning_trade: float
    average_losing_trade: float
    largest_winner: float
    largest_loser: float
    max_consecutive_wins: int
    max_consecutive_losses: int

    # Profitability (mirrors + extends metrics)
    initial_balance: float
    final_balance: float
    net_profit: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    expectancy: float
    return_pct: float

    # Risk
    maximum_drawdown: float
    maximum_drawdown_pct: float
    average_drawdown: float
    risk_per_trade_pct: float
    maximum_exposure_lots: float

    # Breakdowns
    by_year: list[PeriodStats]
    by_month: list[PeriodStats]
    by_day_of_week: list[PeriodStats]
    by_session: list[PeriodStats]
    long_stats: DirectionStats
    short_stats: DirectionStats

    # Distribution
    exit_distribution: ExitDistribution
    average_bars_held: float
    average_r_multiple: float | None
    r_multiples: list[float]

    # Equity
    drawdown: DrawdownAnalysis
    equity_curve: list[EquityPoint]

    model_config = {"frozen": True}


def analyze_baseline(
    report: BacktestReport,
    *,
    risk_per_trade_pct: float,
) -> BaselineAnalysis:
    """Build extended baseline analytics from a standard backtest report."""
    trades = report.trades
    metrics = report.metrics

    long_trades = [t for t in trades if t.direction == SignalDirection.LONG]
    short_trades = [t for t in trades if t.direction == SignalDirection.SHORT]

    largest_winner = max((t.net_pnl for t in trades), default=0.0)
    largest_loser = min((t.net_pnl for t in trades), default=0.0)
    average_trade = metrics.net_profit / metrics.total_trades if metrics.total_trades else 0.0

    return BaselineAnalysis(
        total_trades=metrics.total_trades,
        long_trades=len(long_trades),
        short_trades=len(short_trades),
        winning_trades=metrics.winning_trades,
        losing_trades=metrics.losing_trades,
        win_rate=metrics.win_rate,
        average_trade=round(average_trade, 2),
        average_winning_trade=metrics.average_win,
        average_losing_trade=metrics.average_loss,
        largest_winner=round(largest_winner, 2),
        largest_loser=round(largest_loser, 2),
        max_consecutive_wins=metrics.max_consecutive_wins,
        max_consecutive_losses=metrics.max_consecutive_losses,
        initial_balance=metrics.initial_equity,
        final_balance=metrics.final_equity,
        net_profit=metrics.net_profit,
        gross_profit=metrics.gross_profit,
        gross_loss=metrics.gross_loss,
        profit_factor=metrics.profit_factor,
        expectancy=metrics.expectancy,
        return_pct=metrics.return_pct,
        maximum_drawdown=metrics.maximum_drawdown,
        maximum_drawdown_pct=metrics.maximum_drawdown_pct,
        average_drawdown=_average_drawdown(report.equity_curve),
        risk_per_trade_pct=risk_per_trade_pct,
        maximum_exposure_lots=max((t.volume for t in trades), default=0.0),
        by_year=_period_breakdown(trades, "year"),
        by_month=_period_breakdown(trades, "month"),
        by_day_of_week=_day_of_week_breakdown(trades),
        by_session=_session_breakdown(trades),
        long_stats=_direction_stats(long_trades),
        short_stats=_direction_stats(short_trades),
        exit_distribution=_exit_distribution(trades),
        average_bars_held=round(mean([t.bars_held for t in trades]), 2) if trades else 0.0,
        average_r_multiple=_average_r_multiple(trades),
        r_multiples=[r for t in trades if (r := _r_multiple(t)) is not None],
        drawdown=_drawdown_analysis(report.equity_curve, metrics.initial_equity),
        equity_curve=report.equity_curve,
    )


def _direction_stats(trades: list[TradeRecord]) -> DirectionStats:
    if not trades:
        return DirectionStats(
            trades=0,
            win_rate=0.0,
            profit_factor=None,
            net_profit=0.0,
            expectancy=0.0,
            maximum_drawdown=0.0,
        )
    winners = [t for t in trades if t.net_pnl > 0]
    losers = [t for t in trades if t.net_pnl < 0]
    gross_profit = sum(t.gross_pnl for t in winners if t.gross_pnl > 0)
    gross_loss = abs(sum(t.gross_pnl for t in losers if t.gross_pnl < 0))
    net = sum(t.net_pnl for t in trades)
    pf = gross_profit / gross_loss if gross_loss > 0 else None
    return DirectionStats(
        trades=len(trades),
        win_rate=round(len(winners) / len(trades), 6),
        profit_factor=round(pf, 4) if pf is not None else None,
        net_profit=round(net, 2),
        expectancy=round(net / len(trades), 2),
        maximum_drawdown=0.0,
    )


def _period_breakdown(trades: list[TradeRecord], mode: str) -> list[PeriodStats]:
    buckets: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        key = (
            str(trade.exit_time.year)
            if mode == "year"
            else trade.exit_time.strftime("%Y-%m")
        )
        buckets[key].append(trade)

    stats: list[PeriodStats] = []
    for period in sorted(buckets):
        bucket = buckets[period]
        wins = sum(1 for t in bucket if t.net_pnl > 0)
        stats.append(
            PeriodStats(
                period=period,
                trades=len(bucket),
                net_profit=round(sum(t.net_pnl for t in bucket), 2),
                win_rate=round(wins / len(bucket), 6) if bucket else 0.0,
            )
        )
    return stats


def _day_of_week_breakdown(trades: list[TradeRecord]) -> list[PeriodStats]:
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    buckets: dict[str, list[TradeRecord]] = {name: [] for name in names}
    for trade in trades:
        buckets[names[trade.exit_time.weekday()]].append(trade)
    return [
        PeriodStats(
            period=name,
            trades=len(bucket),
            net_profit=round(sum(t.net_pnl for t in bucket), 2),
            win_rate=round(sum(1 for t in bucket if t.net_pnl > 0) / len(bucket), 6)
            if bucket
            else 0.0,
        )
        for name, bucket in buckets.items()
    ]


def _session_breakdown(trades: list[TradeRecord]) -> list[PeriodStats]:
    sessions = {
        "Asia (00-08 UTC)": range(0, 8),
        "London (08-16 UTC)": range(8, 16),
        "NewYork (13-22 UTC)": range(13, 23),
    }
    result: list[PeriodStats] = []
    for label, hours in sessions.items():
        bucket = [t for t in trades if t.entry_time.hour in hours]
        result.append(
            PeriodStats(
                period=label,
                trades=len(bucket),
                net_profit=round(sum(t.net_pnl for t in bucket), 2),
                win_rate=round(sum(1 for t in bucket if t.net_pnl > 0) / len(bucket), 6)
                if bucket
                else 0.0,
            )
        )
    return result


def _exit_distribution(trades: list[TradeRecord]) -> ExitDistribution:
    return ExitDistribution(
        stop_loss=sum(1 for t in trades if t.exit_reason == ExitReason.STOP_LOSS),
        take_profit=sum(1 for t in trades if t.exit_reason == ExitReason.TAKE_PROFIT),
        end_of_data=sum(1 for t in trades if t.exit_reason == ExitReason.END_OF_DATA),
    )


def _r_multiple(trade: TradeRecord) -> float | None:
    risk = abs(trade.entry_price - trade.stop_loss)
    if risk <= 0:
        return None
    move = trade.exit_price - trade.entry_price
    if trade.direction == SignalDirection.SHORT:
        move = -move
    return round(move / risk, 4)


def _average_r_multiple(trades: list[TradeRecord]) -> float | None:
    values = [r for t in trades if (r := _r_multiple(t)) is not None]
    if not values:
        return None
    return round(mean(values), 4)


def _average_drawdown(equity_curve: list[EquityPoint]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0].equity
    drawdowns: list[float] = []
    for point in equity_curve:
        peak = max(peak, point.equity)
        drawdowns.append(peak - point.equity)
    return round(mean(drawdowns), 2)


def _drawdown_analysis(
    equity_curve: list[EquityPoint],
    initial_equity: float,
) -> DrawdownAnalysis:
    if not equity_curve:
        return DrawdownAnalysis(
            peak_equity=initial_equity,
            maximum_drawdown=0.0,
            maximum_drawdown_pct=0.0,
            average_drawdown=0.0,
            average_drawdown_pct=0.0,
            recovery_periods=0,
            max_recovery_bars=0,
        )

    peak = initial_equity
    max_dd = 0.0
    max_dd_pct = 0.0
    dd_values: list[float] = []
    dd_pct_values: list[float] = []
    recoveries = 0
    max_recovery = 0
    in_drawdown = False
    recovery_bars = 0

    for point in equity_curve:
        peak = max(peak, point.equity)
        dd = peak - point.equity
        dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
        dd_values.append(dd)
        dd_pct_values.append(dd_pct)
        max_dd = max(max_dd, dd)
        max_dd_pct = max(max_dd_pct, dd_pct)

        if dd > 0:
            if not in_drawdown:
                in_drawdown = True
                recovery_bars = 0
            recovery_bars += 1
        elif in_drawdown:
            recoveries += 1
            max_recovery = max(max_recovery, recovery_bars)
            in_drawdown = False
            recovery_bars = 0

    return DrawdownAnalysis(
        peak_equity=round(peak, 2),
        maximum_drawdown=round(max_dd, 2),
        maximum_drawdown_pct=round(max_dd_pct, 4),
        average_drawdown=round(mean(dd_values), 2) if dd_values else 0.0,
        average_drawdown_pct=round(mean(dd_pct_values), 4) if dd_pct_values else 0.0,
        recovery_periods=recoveries,
        max_recovery_bars=max_recovery,
    )
