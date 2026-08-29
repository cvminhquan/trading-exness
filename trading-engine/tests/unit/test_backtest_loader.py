"""Tests for backtest CSV loader."""

from pathlib import Path

import pytest

from exness_bot.backtest.loader import load_candles_from_csv
from exness_bot.domain.enums import Timeframe
from tests.fixtures.backtest_csv import write_uptrend_csv


class TestLoadCandlesFromCsv:
    def test_loads_sorted_candles(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "data.csv", bars=10)
        candles = load_candles_from_csv(csv_path, symbol="XAUUSD", timeframe=Timeframe.M15)
        assert len(candles) == 10
        assert candles[0].timestamp < candles[-1].timestamp
        assert candles[0].symbol == "XAUUSD"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_candles_from_csv(
                tmp_path / "missing.csv",
                symbol="XAUUSD",
                timeframe=Timeframe.M15,
            )

    def test_missing_columns_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.csv"
        bad.write_text("timestamp,open\n2026-01-01,1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="required columns"):
            load_candles_from_csv(bad, symbol="XAUUSD", timeframe=Timeframe.M15)
