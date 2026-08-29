"""Relative Strength Index (RSI) calculations."""

import numpy as np
import pandas as pd


def calculate_rsi(data: pd.Series, period: int) -> pd.Series:
    """
    Calculate RSI using Wilder's smoothing method.

    Args:
        data: Price series (typically close prices).
        period: RSI lookback period. Must be >= 1.

    Returns:
        Series of RSI values (0-100) aligned with ``data`` index.
        Insufficient history yields NaN.
    """
    if period < 1:
        msg = f"RSI period must be >= 1, got {period}"
        raise ValueError(msg)

    if data.empty:
        return pd.Series(dtype=float, index=data.index)

    delta = data.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # avg_loss == 0: RSI is 100 when gains exist, NaN when flat
    zero_loss = avg_loss == 0
    rsi = rsi.where(~zero_loss, other=np.where(avg_gain > 0, 100.0, np.nan))

    # First bar has no delta
    rsi.iloc[0] = np.nan

    return rsi.astype(float)
