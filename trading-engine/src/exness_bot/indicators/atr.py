"""Average True Range (ATR) calculations."""

import pandas as pd


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    range_hl = high - low
    range_hc = (high - prev_close).abs()
    range_lc = (low - prev_close).abs()
    return pd.concat([range_hl, range_hc, range_lc], axis=1).max(axis=1)


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
) -> pd.Series:
    """
    Calculate Average True Range using Wilder's smoothing.

    Args:
        high: High price series.
        low: Low price series.
        close: Close price series.
        period: ATR lookback period. Must be >= 1.

    Returns:
        Series of ATR values aligned with input index.
        Insufficient history yields NaN.
    """
    if period < 1:
        msg = f"ATR period must be >= 1, got {period}"
        raise ValueError(msg)

    if high.empty or low.empty or close.empty:
        return pd.Series(dtype=float, index=close.index)

    if not (len(high) == len(low) == len(close)):
        msg = "high, low, and close must have the same length"
        raise ValueError(msg)

    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
