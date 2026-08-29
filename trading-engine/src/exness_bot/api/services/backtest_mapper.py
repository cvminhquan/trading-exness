"""Map engine baseline artifacts to Dashboard BacktestReport DTOs."""

from __future__ import annotations

from datetime import UTC, datetime

from exness_bot.api.schemas.dashboard import (
    BacktestAssumptionsDTO,
    BacktestClassificationDTO,
    BacktestDatasetDTO,
    BacktestExecutionConfigDTO,
    BacktestPerformanceDTO,
    BacktestRAnalysisDTO,
    BacktestReportDTO,
    BacktestTradeRecordDTO,
    EquityPointDTO,
    MonthlyPerformanceDTO,
)
from exness_bot.backtest.baseline_analysis import BaselineAnalysis
from exness_bot.backtest.baseline_runner import BaselineResult, ExecutionConfigSnapshot
from exness_bot.backtest.config import BacktestAssumptions
from exness_bot.backtest.dataset_inspection import MIN_MEANINGFUL_CANDLES, RECOMMENDED_CANDLES
from exness_bot.backtest.models import BacktestReport, EquityPoint, TradeRecord
from exness_bot.domain.enums import SignalDirection


def to_iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quality_status(total_candles: int, is_meaningful: bool, is_valid_ohlc: bool) -> str:
    if not is_meaningful or total_candles < MIN_MEANINGFUL_CANDLES:
        return "INSUFFICIENT"
    if not is_valid_ohlc:
        return "WARNING"
    return "VALID"


def _derive_drawdown_curve(equity_curve: list[EquityPointDTO]) -> list[EquityPointDTO]:
    if not equity_curve:
        return []
    peak = equity_curve[0].equity
    result: list[EquityPointDTO] = []
    for point in equity_curve:
        peak = max(peak, point.equity)
        drawdown_pct = ((peak - point.equity) / peak * 100.0) if peak > 0 else 0.0
        result.append(
            EquityPointDTO(
                timestamp=point.timestamp,
                equity=round(drawdown_pct, 2),
            )
        )
    return result


def _r_multiple(trade: TradeRecord) -> float | None:
    risk = abs(trade.entry_price - trade.stop_loss)
    if risk <= 0:
        return None
    move = trade.exit_price - trade.entry_price
    if trade.direction == SignalDirection.SHORT:
        move = -move
    return round(move / risk, 4)


def _map_equity_curve(points: list[EquityPoint]) -> list[EquityPointDTO]:
    return [
        EquityPointDTO(timestamp=to_iso_utc(point.timestamp) or "", equity=round(point.equity, 2))
        for point in points
    ]


def _map_dataset(result: BaselineResult) -> BacktestDatasetDTO | None:
    dataset = result.dataset
    if dataset is None:
        return None
    return BacktestDatasetDTO(
        total_candles=dataset.total_candles,
        start_timestamp=to_iso_utc(dataset.start_timestamp),
        end_timestamp=to_iso_utc(dataset.end_timestamp),
        duration_days=dataset.duration_days,
        timezone=dataset.timezone,
        duplicate_timestamps=dataset.duplicate_timestamps,
        missing_periods=dataset.missing_periods,
        missing_bars_total=dataset.missing_bars_total,
        weekend_gaps=dataset.weekend_gaps,
        session_gaps=dataset.session_gaps,
        is_sorted=dataset.is_sorted,
        is_valid_ohlc=dataset.is_valid_ohlc,
        is_meaningful=dataset.is_meaningful,
        min_required_candles=MIN_MEANINGFUL_CANDLES,
        recommended_candles=RECOMMENDED_CANDLES,
        quality_status=_quality_status(
            dataset.total_candles,
            dataset.is_meaningful,
            dataset.is_valid_ohlc,
        ),
    )


def _map_execution(execution: ExecutionConfigSnapshot) -> BacktestExecutionConfigDTO:
    return BacktestExecutionConfigDTO(
        initial_balance=execution.initial_balance,
        risk_per_trade_pct=execution.risk_per_trade_pct,
        max_daily_loss_pct=execution.max_daily_loss_pct,
        max_drawdown_pct=execution.max_drawdown_pct,
        max_open_positions=execution.max_open_positions,
        max_position_lots=execution.max_position_lots,
        spread_points=execution.spread_points,
        slippage_points=execution.slippage_points,
        commission_per_lot=execution.commission_per_lot,
        swap_per_lot_per_day=execution.swap_per_lot_per_day,
        warmup_bars=execution.warmup_bars,
    )


def _map_assumptions(report: BacktestReport | None) -> BacktestAssumptionsDTO | None:
    assumptions = BacktestAssumptions() if report is None else report.assumptions
    return BacktestAssumptionsDTO(
        candle_timing=assumptions.candle_timing,
        execution=assumptions.execution,
        spread=assumptions.spread,
        slippage=assumptions.slippage,
        commission=assumptions.commission,
        swap=assumptions.swap,
        exit_costs=assumptions.exit_costs,
        position_limit=assumptions.position_limit,
        end_of_data=assumptions.end_of_data,
        position_sizing=(
            "Fixed risk per trade from configured risk_per_trade_pct and ATR-based stop distance."
        ),
        same_bar_exit_rule=(
            "SL/TP evaluated from the next bar; when both touched in the same bar, stop loss "
            "takes priority."
        ),
    )


def _map_performance(
    report: BacktestReport,
    analysis: BaselineAnalysis | None,
) -> BacktestPerformanceDTO:
    metrics = report.metrics
    total_commission = sum(t.commission for t in report.trades)
    total_swap = 0.0
    average_trade = analysis.average_trade if analysis else None
    average_r = analysis.average_r_multiple if analysis else None
    largest_win = analysis.largest_winner if analysis else None
    largest_loss = analysis.largest_loser if analysis else None
    avg_duration = int(analysis.average_bars_held) if analysis else None
    max_dd_duration = (
        analysis.drawdown.max_recovery_bars if analysis and analysis.drawdown else None
    )
    current_dd_pct = None
    if analysis and analysis.equity_curve:
        peak = analysis.drawdown.peak_equity
        last_equity = analysis.equity_curve[-1].equity
        if peak > 0:
            current_dd_pct = round((peak - last_equity) / peak * 100.0, 4)

    return BacktestPerformanceDTO(
        total_trades=metrics.total_trades,
        winning_trades=metrics.winning_trades,
        losing_trades=metrics.losing_trades,
        win_rate=round(metrics.win_rate * 100.0, 4),
        gross_profit=metrics.gross_profit,
        gross_loss=metrics.gross_loss,
        net_profit=metrics.net_profit,
        total_commission=round(total_commission, 2),
        total_swap=total_swap,
        profit_factor=metrics.profit_factor,
        expectancy=metrics.expectancy,
        average_win=metrics.average_win,
        average_loss=metrics.average_loss,
        average_trade=average_trade,
        average_r=average_r,
        largest_win=largest_win,
        largest_loss=largest_loss,
        max_consecutive_wins=metrics.max_consecutive_wins,
        max_consecutive_losses=metrics.max_consecutive_losses,
        initial_balance=metrics.initial_equity,
        final_balance=metrics.final_equity,
        return_pct=metrics.return_pct,
        max_drawdown_pct=metrics.maximum_drawdown_pct,
        max_drawdown_usd=metrics.maximum_drawdown,
        max_drawdown_duration_bars=max_dd_duration,
        current_drawdown_pct=current_dd_pct,
        average_trade_duration_bars=avg_duration,
    )


def _map_trades(trades: list[TradeRecord]) -> list[BacktestTradeRecordDTO]:
    mapped: list[BacktestTradeRecordDTO] = []
    for trade in trades:
        mapped.append(
            BacktestTradeRecordDTO(
                trade_id=trade.trade_id,
                direction=trade.direction.value,
                volume=trade.volume,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                stop_loss=trade.stop_loss,
                take_profit=trade.take_profit,
                entry_time=to_iso_utc(trade.entry_time) or "",
                exit_time=to_iso_utc(trade.exit_time) or "",
                exit_reason=trade.exit_reason.value,
                gross_pnl=trade.gross_pnl,
                commission=trade.commission,
                swap=0.0,
                net_pnl=trade.net_pnl,
                bars_held=trade.bars_held,
                r_multiple=_r_multiple(trade),
                signal_reason=trade.signal_reason,
            )
        )
    return mapped


def _map_monthly(analysis: BaselineAnalysis | None) -> list[MonthlyPerformanceDTO]:
    if analysis is None:
        return []
    return [
        MonthlyPerformanceDTO(
            month=period.period,
            net_pnl=period.net_profit,
            return_pct=None,
            trades=period.trades,
            win_rate=round(period.win_rate * 100.0, 4),
        )
        for period in analysis.by_month
    ]


def _map_r_analysis(analysis: BaselineAnalysis | None) -> BacktestRAnalysisDTO | None:
    if analysis is None or not analysis.r_multiples:
        return BacktestRAnalysisDTO(
            average_r=analysis.average_r_multiple if analysis else None,
            winning_r_average=None,
            losing_r_average=None,
            best_r=None,
            worst_r=None,
            r_multiples=analysis.r_multiples if analysis else [],
        )
    winners = [r for r in analysis.r_multiples if r > 0]
    losers = [r for r in analysis.r_multiples if r < 0]
    return BacktestRAnalysisDTO(
        average_r=analysis.average_r_multiple,
        winning_r_average=round(sum(winners) / len(winners), 4) if winners else None,
        losing_r_average=round(sum(losers) / len(losers), 4) if losers else None,
        best_r=max(analysis.r_multiples),
        worst_r=min(analysis.r_multiples),
        r_multiples=analysis.r_multiples,
    )


def map_baseline_to_report(report_id: str, result: BaselineResult) -> BacktestReportDTO:
    """Convert BaselineResult to dashboard BacktestReport DTO."""
    dataset = result.dataset
    period_start = to_iso_utc(dataset.start_timestamp) if dataset else None
    period_end = to_iso_utc(dataset.end_timestamp) if dataset else None

    equity_curve: list[EquityPointDTO] = []
    if result.analysis is not None:
        equity_curve = _map_equity_curve(result.analysis.equity_curve)
    elif result.backtest is not None:
        equity_curve = _map_equity_curve(result.backtest.equity_curve)

    drawdown_curve = _derive_drawdown_curve(equity_curve)
    performance = (
        _map_performance(result.backtest, result.analysis)
        if result.backtest is not None
        else None
    )
    assumptions = _map_assumptions(result.backtest)
    classification = BacktestClassificationDTO(
        classification=result.classification.classification.value,
        rationale=list(result.classification.rationale),
    )
    trades = _map_trades(result.backtest.trades) if result.backtest else []

    return BacktestReportDTO(
        id=report_id,
        strategy=result.strategy,
        symbol=result.symbol,
        timeframe=result.timeframe,
        status=result.status,
        generated_at=to_iso_utc(result.generated_at) or "",
        message=result.message,
        period_start=period_start,
        period_end=period_end,
        dataset=_map_dataset(result),
        execution=_map_execution(result.execution),
        performance=performance,
        assumptions=assumptions,
        classification=classification,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        trades=trades,
        monthly_performance=_map_monthly(result.analysis),
        r_analysis=_map_r_analysis(result.analysis),
    )
