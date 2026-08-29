"""Backtest report formatting."""

from __future__ import annotations

import json
from pathlib import Path

from exness_bot.backtest.models import BacktestReport


def render_summary(report: BacktestReport) -> str:
    """Return a human-readable backtest summary."""
    metrics = report.metrics
    pf = f"{metrics.profit_factor:.2f}" if metrics.profit_factor is not None else "N/A"
    rr = f"{metrics.risk_reward:.2f}" if metrics.risk_reward is not None else "N/A"
    dd_pct = metrics.maximum_drawdown_pct
    drawdown_line = (
        f"Maximum drawdown   : ${metrics.maximum_drawdown:,.2f} ({dd_pct:.2f}%)"
    )

    lines = [
        "=" * 60,
        "EXNESS BOT — BACKTEST SUMMARY",
        "=" * 60,
        f"Strategy     : {report.strategy_name}",
        f"Symbol       : {report.symbol}",
        f"Timeframe    : {report.timeframe}",
        f"Bars         : {report.bars_processed}",
        "",
        "--- Performance ---",
        f"Initial equity     : ${metrics.initial_equity:,.2f}",
        f"Final equity       : ${metrics.final_equity:,.2f}",
        f"Net profit         : ${metrics.net_profit:,.2f}",
        f"Return             : {metrics.return_pct:.2f}%",
        drawdown_line,
        "",
        "--- Trades ---",
        f"Total trades       : {metrics.total_trades}",
        f"Winning trades     : {metrics.winning_trades}",
        f"Losing trades      : {metrics.losing_trades}",
        f"Win rate           : {metrics.win_rate * 100:.2f}%",
        f"Gross profit       : ${metrics.gross_profit:,.2f}",
        f"Gross loss         : ${metrics.gross_loss:,.2f}",
        f"Profit factor      : {pf}",
        f"Expectancy         : ${metrics.expectancy:,.2f}",
        f"Average win        : ${metrics.average_win:,.2f}",
        f"Average loss       : ${metrics.average_loss:,.2f}",
        f"Risk/Reward        : {rr}",
        f"Max consecutive W  : {metrics.max_consecutive_wins}",
        f"Max consecutive L  : {metrics.max_consecutive_losses}",
        "",
        "--- Activity ---",
        f"Signals generated  : {report.signals_generated}",
        f"Orders approved    : {report.orders_approved}",
        f"Orders rejected    : {report.orders_rejected}",
        "",
        "--- Assumptions ---",
        f"Spread             : {report.config.spread_points} points (fixed)",
        f"Slippage           : {report.config.slippage_points} points",
        f"Commission/lot     : ${report.config.commission_per_lot:.2f} per side",
        f"Candle timing      : {report.assumptions.candle_timing}",
        f"Execution          : {report.assumptions.execution}",
        "=" * 60,
    ]
    return "\n".join(lines)


def write_json_report(report: BacktestReport, path: str | Path) -> None:
    """Write machine-readable JSON report."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
