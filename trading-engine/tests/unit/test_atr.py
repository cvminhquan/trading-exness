"""Unit tests for calculate_atr."""

import pandas as pd
import pytest

from exness_bot.indicators.atr import calculate_atr
from tests.fixtures.ohlc_data import make_constant_range_ohlc, make_uptrend_ohlc


class TestCalculateAtr:
    def test_invalid_period_raises(self) -> None:
        high = pd.Series([10.0, 11.0])
        low = pd.Series([9.0, 10.0])
        close = pd.Series([9.5, 10.5])
        with pytest.raises(ValueError, match="period must be >= 1"):
            calculate_atr(high, low, close, 0)

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            calculate_atr(
                pd.Series([10.0, 11.0]),
                pd.Series([9.0]),
                pd.Series([9.5, 10.5]),
                14,
            )

    def test_empty_series_returns_empty(self) -> None:
        empty = pd.Series(dtype=float)
        result = calculate_atr(empty, empty, empty, 14)
        assert result.empty

    def test_insufficient_data_returns_nan(self) -> None:
        bars = make_constant_range_ohlc(length=5)
        atr = calculate_atr(bars["high"], bars["low"], bars["close"], period=14)
        assert atr.isna().all()

    def test_constant_range_atr_converges(self) -> None:
        bars = make_constant_range_ohlc(length=50)
        atr = calculate_atr(bars["high"], bars["low"], bars["close"], period=14)
        last_atr = atr.iloc[-1]
        assert last_atr is not None and not pd.isna(last_atr)
        assert last_atr == pytest.approx(4.0, rel=0.01)

    def test_atr_positive_in_uptrend(self) -> None:
        bars = make_uptrend_ohlc(length=50)
        atr = calculate_atr(bars["high"], bars["low"], bars["close"], period=14)
        valid = atr.dropna()
        assert (valid > 0).all()

    def test_atr_length_matches_input(self) -> None:
        bars = make_uptrend_ohlc(length=30)
        atr = calculate_atr(bars["high"], bars["low"], bars["close"], period=14)
        assert len(atr) == len(bars)

    def test_nan_in_close_propagates(self) -> None:
        bars = make_uptrend_ohlc(length=30)
        close = bars["close"].copy()
        close.iloc[5] = float("nan")
        atr = calculate_atr(bars["high"], bars["low"], close, period=14)
        assert pd.isna(atr.iloc[5])
