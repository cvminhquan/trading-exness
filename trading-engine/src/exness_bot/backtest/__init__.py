"""Backtesting module."""

from exness_bot.backtest.config import BacktestAssumptions, BacktestConfig
from exness_bot.backtest.engine import BacktestEngine
from exness_bot.backtest.loader import load_candles_from_csv
from exness_bot.backtest.models import BacktestMetrics, BacktestReport, TradeRecord
from exness_bot.backtest.report import render_summary, write_json_report
from exness_bot.backtest.runner import BacktestRunner

__all__ = [
    "BacktestAssumptions",
    "BacktestConfig",
    "BacktestEngine",
    "BacktestMetrics",
    "BacktestReport",
    "BacktestRunner",
    "TradeRecord",
    "load_candles_from_csv",
    "render_summary",
    "write_json_report",
]
