"""Indicator calculator — orchestrates EMA, RSI, ATR over OHLCV DataFrames."""

from datetime import UTC, datetime
from typing import ClassVar

import pandas as pd

from exness_bot.domain.models import IndicatorSnapshot
from exness_bot.indicators.atr import calculate_atr
from exness_bot.indicators.ema import calculate_ema
from exness_bot.indicators.rsi import calculate_rsi

EMA_PERIODS: tuple[int, ...] = (20, 50, 200)
RSI_PERIOD = 14
ATR_PERIOD = 14


class IndicatorCalculator:
    """Compute configured indicators from OHLCV bars and return latest snapshot."""

    REQUIRED_COLUMNS: ClassVar[set[str]] = {"open", "high", "low", "close"}

    @staticmethod
    def validate_bars(bars: pd.DataFrame) -> None:
        """Raise ValueError if bars DataFrame is missing required columns."""
        missing = IndicatorCalculator.REQUIRED_COLUMNS - set(bars.columns)
        if missing:
            msg = f"Missing required columns: {missing}"
            raise ValueError(msg)

    @staticmethod
    def compute_all(bars: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all configured indicators and attach as columns.

        Returns a copy of ``bars`` with added columns:
        ema_20, ema_50, ema_200, rsi_14, atr_14.
        """
        IndicatorCalculator.validate_bars(bars)

        if bars.empty:
            msg = "Cannot compute indicators on empty DataFrame"
            raise ValueError(msg)

        result = bars.copy()
        close = result["close"].astype(float)

        result["ema_20"] = calculate_ema(close, 20)
        result["ema_50"] = calculate_ema(close, 50)
        result["ema_200"] = calculate_ema(close, 200)
        result["rsi_14"] = calculate_rsi(close, RSI_PERIOD)
        result["atr_14"] = calculate_atr(
            result["high"].astype(float),
            result["low"].astype(float),
            close,
            ATR_PERIOD,
        )
        return result

    @staticmethod
    def compute(bars: pd.DataFrame) -> IndicatorSnapshot:
        """Compute indicators and return snapshot for the latest bar."""
        enriched = IndicatorCalculator.compute_all(bars)
        latest = enriched.iloc[-1]

        timestamp = latest.get("timestamp")
        if timestamp is None or (isinstance(timestamp, float) and pd.isna(timestamp)):
            timestamp = datetime.now(tz=UTC)
        elif isinstance(timestamp, pd.Timestamp):
            timestamp = timestamp.to_pydatetime()

        return IndicatorSnapshot(
            timestamp=timestamp,
            ema_20=_safe_float(latest.get("ema_20")),
            ema_50=_safe_float(latest.get("ema_50")),
            ema_200=_safe_float(latest.get("ema_200")),
            rsi_14=_safe_float(latest.get("rsi_14")),
            atr_14=_safe_float(latest.get("atr_14")),
        )


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        if pd.isna(value):
            return None
        return float(value)
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result
