"""Tests for Phase 7.2 baseline backtest pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from exness_bot.backtest.baseline_analysis import analyze_baseline
from exness_bot.backtest.baseline_runner import (
    baseline_paths,
    run_baseline,
    write_baseline_outputs,
)
from exness_bot.backtest.classification import EdgeClassification, classify_baseline_edge
from exness_bot.backtest.config import BacktestConfig
from exness_bot.backtest.dataset_inspection import inspect_csv_dataset
from exness_bot.backtest.engine import BacktestEngine
from exness_bot.config.settings import Settings
from tests.fixtures.backtest_csv import write_uptrend_csv


class TestDatasetInspection:
    def test_inspect_small_csv(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "small.csv", bars=260)
        profile = inspect_csv_dataset(csv_path)

        assert profile.total_candles == 260
        assert profile.duplicate_timestamps == 0
        assert profile.timezone == "UTC"
        assert profile.is_meaningful is False
        assert profile.start_timestamp is not None
        assert profile.end_timestamp is not None


class TestBaselineClassification:
    def test_insufficient_data_classification(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "small.csv", bars=100)
        profile = inspect_csv_dataset(csv_path)
        result = classify_baseline_edge(None, profile)

        assert result.classification == EdgeClassification.INSUFFICIENT_DATA
        assert any("5,000" in item or "5000" in item for item in result.rationale)


class TestBaselineRunner:
    def test_no_dataset_returns_insufficient_status(self, tmp_path: Path) -> None:
        result = run_baseline(Settings(), project_root=tmp_path)

        assert result.status == "insufficient_data"
        assert result.analysis is None
        assert result.classification.classification == EdgeClassification.INSUFFICIENT_DATA

    def test_small_dataset_not_meaningful(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "data" / "historical" / "xau.csv", bars=260)
        result = run_baseline(Settings(), data_path=str(csv_path), project_root=tmp_path)

        assert result.status == "insufficient_data"
        assert result.dataset is not None
        assert result.dataset.total_candles == 260

    def test_writes_json_and_markdown(self, tmp_path: Path) -> None:
        result = run_baseline(Settings(), project_root=tmp_path)
        paths = baseline_paths(tmp_path)
        write_baseline_outputs(result, paths)

        assert paths.json_path.exists()
        assert paths.markdown_path.exists()
        payload = json.loads(paths.json_path.read_text(encoding="utf-8"))
        assert payload["strategy"] == "ema_rsi_atr_v1"
        assert payload["status"] == "insufficient_data"
        markdown = paths.markdown_path.read_text(encoding="utf-8")
        assert "ema_rsi_atr_v1" in markdown
        assert "Execution assumptions" in markdown


class TestBaselineAnalysis:
    def test_analyze_from_backtest_report(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "uptrend.csv", bars=260)
        settings = Settings()
        report = BacktestEngine(
            settings,
            config=BacktestConfig(warmup_bars=200),
        ).run(str(csv_path))
        analysis = analyze_baseline(report, risk_per_trade_pct=settings.risk_per_trade_pct)

        assert analysis.total_trades == report.metrics.total_trades
        assert analysis.initial_balance == report.metrics.initial_equity
        assert len(analysis.equity_curve) == len(report.equity_curve)
        assert analysis.exit_distribution.stop_loss >= 0

    def test_reproducibility_on_same_csv(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "uptrend.csv", bars=260)
        config = BacktestConfig(warmup_bars=200)
        engine = BacktestEngine(Settings(), config=config)
        report1 = engine.run(str(csv_path))
        report2 = engine.run(str(csv_path))

        assert report1.model_dump() == report2.model_dump()
