"""Unit tests for calculate_ema."""

import pandas as pd
import pytest

from exness_bot.indicators.ema import calculate_ema
from tests.fixtures.ohlc_data import make_uptrend_ohlc


class TestCalculateEma:
    def test_invalid_period_raises(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 1"):
            calculate_ema(pd.Series([1.0, 2.0]), 0)

    def test_empty_series_returns_empty(self) -> None:
        result = calculate_ema(pd.Series(dtype=float), 20)
        assert result.empty

    def test_insufficient_data_returns_nan(self) -> None:
        data = pd.Series([100.0, 101.0, 102.0])
        result = calculate_ema(data, period=20)
        assert result.isna().all()

    def test_constant_price_ema_equals_price(self) -> None:
        data = pd.Series([100.0] * 30)
        result = calculate_ema(data, period=20)
        valid = result.dropna()
        assert len(valid) == 11  # bars 19..29
        assert (valid == 100.0).all()

    def test_uptrend_ema_lags_below_price(self) -> None:
        bars = make_uptrend_ohlc(length=50)
        ema = calculate_ema(bars["close"], period=20)
        last_close = bars["close"].iloc[-1]
        last_ema = ema.iloc[-1]
        assert last_ema < last_close

    def test_ema_length_matches_input(self) -> None:
        data = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = calculate_ema(data, period=3)
        assert len(result) == len(data)

    def test_first_valid_ema_at_min_periods(self) -> None:
        data = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = calculate_ema(data, period=3)
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])
        assert not pd.isna(result.iloc[2])

    def test_nan_in_input_propagates(self) -> None:
        data = pd.Series([100.0, float("nan"), 102.0, 103.0, 104.0] * 10)
        result = calculate_ema(data, period=5)
        # NaN input should produce NaN in output from that point
        assert pd.isna(result.iloc[1])
