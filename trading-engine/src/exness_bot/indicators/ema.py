"""Exponential Moving Average (EMA) calculations."""

import pandas as pd


def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average on a price series.

    Uses pandas EWM with ``adjust=False`` (standard trading convention).

    Args:
        data: Price series (typically close prices).
        period: EMA lookback period. Must be >= 1.

    Returns:
        Series of EMA values aligned with ``data`` index.
        First ``period - 1`` values are NaN when insufficient history.
    """
    if period < 1:
        msg = f"EMA period must be >= 1, got {period}"
        raise ValueError(msg)

    if data.empty:
        return pd.Series(dtype=float, index=data.index)

    return data.ewm(span=period, adjust=False, min_periods=period).mean()
