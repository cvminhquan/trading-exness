"""MACD 12/26/9 — reusable indicator (analysis only)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from exness_bot.indicators.ema import calculate_ema


@dataclass(frozen=True)
class MacdSnapshot:
    macd: float | None
    signal: float | None
    histogram: float | None
    momentum: str  # BULLISH | BEARISH | NEUTRAL | UNKNOWN


def calculate_macd(
    close: pd.Series,
    *,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram) series."""
    if fast < 1 or slow < 1 or signal_period < 1 or fast >= slow:
        msg = f"Invalid MACD periods fast={fast} slow={slow} signal={signal_period}"
        raise ValueError(msg)
    ema_fast = calculate_ema(close.astype(float), fast)
    ema_slow = calculate_ema(close.astype(float), slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line.dropna(), signal_period)
    # Align signal to full index
    signal_aligned = signal_line.reindex(macd_line.index)
    histogram = macd_line - signal_aligned
    return macd_line, signal_aligned, histogram


def macd_snapshot(
    close: pd.Series,
    *,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> MacdSnapshot:
    if close.empty or len(close) < slow + signal_period:
        return MacdSnapshot(None, None, None, "UNKNOWN")
    macd_line, signal_line, histogram = calculate_macd(
        close, fast=fast, slow=slow, signal_period=signal_period
    )
    m = macd_line.iloc[-1]
    s = signal_line.iloc[-1]
    h = histogram.iloc[-1]
    if pd.isna(m) or pd.isna(s) or pd.isna(h):
        return MacdSnapshot(None, None, None, "UNKNOWN")
    mf, sf, hf = float(m), float(s), float(h)
    if hf > 0 and mf > sf:
        momentum = "BULLISH"
    elif hf < 0 and mf < sf:
        momentum = "BEARISH"
    else:
        momentum = "NEUTRAL"
    return MacdSnapshot(mf, sf, hf, momentum)
