"""Deterministic OHLC fixtures for indicator unit tests."""

import pandas as pd


def make_uptrend_ohlc(length: int = 250, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    """Monotonically rising close prices with realistic high/low."""
    closes = [start + i * step for i in range(length)]
    return pd.DataFrame(
        {
            "open": [c - 0.2 for c in closes],
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "close": closes,
        }
    )


def make_downtrend_ohlc(length: int = 250, start: float = 200.0, step: float = 0.5) -> pd.DataFrame:
    """Monotonically falling close prices."""
    closes = [start - i * step for i in range(length)]
    return pd.DataFrame(
        {
            "open": [c + 0.2 for c in closes],
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "close": closes,
        }
    )


def make_flat_ohlc(length: int = 50, price: float = 100.0) -> pd.DataFrame:
    """Constant OHLC — useful for EMA/ATR edge cases."""
    return pd.DataFrame(
        {
            "open": [price] * length,
            "high": [price + 2.0] * length,
            "low": [price - 2.0] * length,
            "close": [price] * length,
        }
    )


def make_constant_range_ohlc(length: int = 30) -> pd.DataFrame:
    """Fixed true range of 4.0 each bar (high-low=4, close unchanged)."""
    return pd.DataFrame(
        {
            "open": [100.0] * length,
            "high": [102.0] * length,
            "low": [98.0] * length,
            "close": [100.0] * length,
        }
    )


def make_ohlc_with_nan_gap(length: int = 30) -> pd.DataFrame:
    """OHLC with a NaN close in the middle."""
    df = make_uptrend_ohlc(length)
    df.loc[10, "close"] = float("nan")
    return df
