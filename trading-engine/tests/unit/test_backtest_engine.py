"""Tests for the backtest engine."""

import json
from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.backtest.engine import BacktestEngine
from exness_bot.backtest.report import render_summary
from exness_bot.backtest.runner import BacktestRunner
from exness_bot.config.settings import Settings
from tests.fixtures.backtest_csv import write_uptrend_csv


class TestBacktestEngine:
    def test_runs_without_mt5(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "uptrend.csv", bars=260)
        settings = Settings(TRADING_MODE="dry_run", DRY_RUN=True)
        config = BacktestConfig(warmup_bars=200, spread_points=20)
        engine = BacktestEngine(settings, config=config)
        report = engine.run(str(csv_path))

        assert report.bars_processed == 60
        assert report.strategy_name == "ema_rsi_atr_v1"
        assert report.metrics.initial_equity == 10_000.0
        assert len(report.equity_curve) == 60

    def test_runner_writes_json_report(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "uptrend.csv", bars=260)
        json_path = tmp_path / "report.json"
        runner = BacktestRunner(Settings(), config=BacktestConfig(warmup_bars=200))
        report = runner.run(str(csv_path), json_output=str(json_path))

        assert json_path.exists()
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["strategy_name"] == report.strategy_name
        assert "metrics" in payload
        assert "assumptions" in payload

    def test_human_summary_contains_key_sections(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "uptrend.csv", bars=260)
        engine = BacktestEngine(Settings(), config=BacktestConfig(warmup_bars=200))
        report = engine.run(str(csv_path))
        summary = render_summary(report)
        assert "BACKTEST SUMMARY" in summary
        assert "Performance" in summary
        assert "Assumptions" in summary

    def test_idempotent_bar_processing_count(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "uptrend.csv", bars=260)
        config = BacktestConfig(warmup_bars=200)
        report = BacktestEngine(Settings(), config=config).run(str(csv_path))
        assert report.signals_generated == report.bars_processed
