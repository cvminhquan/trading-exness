"""Tests for IndicatorCalculator orchestration."""

import pandas as pd
import pytest

from exness_bot.indicators.calculator import IndicatorCalculator
from tests.fixtures.ohlc_data import (
    make_flat_ohlc,
    make_ohlc_with_nan_gap,
    make_uptrend_ohlc,
)


class TestIndicatorCalculator:
    def test_validate_bars_missing_columns(self) -> None:
        bars = pd.DataFrame({"close": [1.0, 2.0]})
        with pytest.raises(ValueError, match="Missing required columns"):
            IndicatorCalculator.validate_bars(bars)

    def test_compute_empty_dataframe_raises(self) -> None:
        bars = pd.DataFrame(columns=["open", "high", "low", "close"])
        with pytest.raises(ValueError, match="empty"):
            IndicatorCalculator.compute(bars)

    def test_compute_all_adds_indicator_columns(self) -> None:
        bars = make_uptrend_ohlc(length=250)
        result = IndicatorCalculator.compute_all(bars)
        for col in ("ema_20", "ema_50", "ema_200", "rsi_14", "atr_14"):
            assert col in result.columns

    def test_compute_snapshot_with_sufficient_data(self) -> None:
        bars = make_uptrend_ohlc(length=250)
        snapshot = IndicatorCalculator.compute(bars)
        assert snapshot.ema_20 is not None
        assert snapshot.ema_50 is not None
        assert snapshot.ema_200 is not None
        assert snapshot.rsi_14 is not None
        assert snapshot.atr_14 is not None
        assert snapshot.ema_20 > snapshot.ema_50 > snapshot.ema_200

    def test_compute_snapshot_insufficient_data_returns_none(self) -> None:
        bars = make_uptrend_ohlc(length=10)
        snapshot = IndicatorCalculator.compute(bars)
        assert snapshot.ema_20 is None
        assert snapshot.ema_200 is None

    def test_compute_preserves_timestamp(self) -> None:
        bars = make_uptrend_ohlc(length=250)
        bars["timestamp"] = pd.date_range("2026-01-01", periods=len(bars), freq="15min")
        snapshot = IndicatorCalculator.compute(bars)
        assert snapshot.timestamp.year == 2026

    def test_compute_flat_market(self) -> None:
        bars = make_flat_ohlc(length=250)
        snapshot = IndicatorCalculator.compute(bars)
        assert snapshot.ema_20 == pytest.approx(100.0)
        assert snapshot.ema_200 == pytest.approx(100.0)
        assert snapshot.rsi_14 is None  # flat → undefined RSI
        assert snapshot.atr_14 == pytest.approx(4.0, rel=0.01)

    def test_compute_with_nan_in_data(self) -> None:
        bars = make_ohlc_with_nan_gap(length=250)
        snapshot = IndicatorCalculator.compute(bars)
        # Should not raise; latest bar may have partial indicators
        assert snapshot.timestamp is not None
