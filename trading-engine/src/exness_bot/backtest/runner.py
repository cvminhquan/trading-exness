"""Backtest runner — entry point for CLI and scripts."""

from __future__ import annotations

import structlog

from exness_bot.backtest.config import BacktestConfig
from exness_bot.backtest.engine import BacktestEngine
from exness_bot.backtest.models import BacktestReport
from exness_bot.backtest.report import render_summary, write_json_report
from exness_bot.config.settings import Settings
from exness_bot.strategy.base import Strategy
from exness_bot.strategy.ema_rsi_atr import EmaRsiAtrStrategy

logger = structlog.get_logger(__name__)


class BacktestRunner:
    """Run strategy backtests on historical data without MT5."""

    def __init__(
        self,
        settings: Settings,
        strategy: Strategy | None = None,
        config: BacktestConfig | None = None,
    ) -> None:
        self._settings = settings
        self._strategy = strategy or EmaRsiAtrStrategy(settings)
        self._config = config
        self._engine = BacktestEngine(settings, self._strategy, config)

    def run(
        self,
        data_path: str,
        *,
        json_output: str | None = None,
    ) -> BacktestReport:
        """Execute backtest and optionally write JSON report."""
        report = self._engine.run(data_path)
        summary = render_summary(report)
        print(summary)

        if json_output:
            write_json_report(report, json_output)
            logger.info("backtest_json_written", path=json_output)

        return report
