"""Unit tests for calculate_rsi."""

import pandas as pd
import pytest

from exness_bot.indicators.rsi import calculate_rsi
from tests.fixtures.ohlc_data import make_downtrend_ohlc, make_flat_ohlc, make_uptrend_ohlc


class TestCalculateRsi:
    def test_invalid_period_raises(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 1"):
            calculate_rsi(pd.Series([1.0, 2.0]), 0)

    def test_empty_series_returns_empty(self) -> None:
        result = calculate_rsi(pd.Series(dtype=float), 14)
        assert result.empty

    def test_insufficient_data_all_nan(self) -> None:
        data = pd.Series([100.0, 101.0, 102.0])
        result = calculate_rsi(data, period=14)
        assert result.isna().all()

    def test_first_bar_is_nan(self) -> None:
        data = pd.Series([100.0] * 30)
        result = calculate_rsi(data, period=14)
        assert pd.isna(result.iloc[0])

    def test_uptrend_rsi_high(self) -> None:
        bars = make_uptrend_ohlc(length=50)
        rsi = calculate_rsi(bars["close"], period=14)
        last_rsi = rsi.iloc[-1]
        assert last_rsi is not None and not pd.isna(last_rsi)
        assert last_rsi > 70.0

    def test_downtrend_rsi_low(self) -> None:
        bars = make_downtrend_ohlc(length=50)
        rsi = calculate_rsi(bars["close"], period=14)
        last_rsi = rsi.iloc[-1]
        assert last_rsi is not None and not pd.isna(last_rsi)
        assert last_rsi < 30.0

    def test_flat_rsi_is_nan(self) -> None:
        bars = make_flat_ohlc(length=30)
        rsi = calculate_rsi(bars["close"], period=14)
        # No gains/losses after warmup → undefined RSI
        assert pd.isna(rsi.iloc[-1])

    def test_rsi_bounded_0_100(self) -> None:
        bars = make_uptrend_ohlc(length=100)
        rsi = calculate_rsi(bars["close"], period=14).dropna()
        assert (rsi >= 0.0).all()
        assert (rsi <= 100.0).all()

    def test_rsi_length_matches_input(self) -> None:
        data = pd.Series(range(1, 51), dtype=float)
        result = calculate_rsi(data, period=14)
        assert len(result) == len(data)

    def test_nan_in_input_propagates(self) -> None:
        data = pd.Series([100.0, 101.0, float("nan"), 103.0, 104.0] * 10)
        result = calculate_rsi(data, period=14)
        assert pd.isna(result.iloc[2])
