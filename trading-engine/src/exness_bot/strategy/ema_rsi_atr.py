"""EMA + RSI + ATR trend strategy for XAUUSD M15.

LEGACY / NON-EXECUTABLE-FOR-PHASE-17
------------------------------------
This strategy remains the signal source for current paper trading and
backtest paths only.

Phase 16.3 ExecutionCandidate MUST originate from Phase 16.2 MTF
(``mtf_technical_v1``) via ``market_analysis.contract``.

Do NOT wire this class into Phase 17 DEMO execution candidate generation.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalAction, Timeframe
from exness_bot.domain.models import IndicatorSnapshot, Signal
from exness_bot.indicators.calculator import IndicatorCalculator

STRATEGY_NAME = "ema_rsi_atr_v1"
LEGACY_NON_EXECUTABLE_FOR_PHASE_17 = True


class EmaRsiAtrStrategy:
    """
    Deterministic EMA trend strategy with RSI confirmation.

    Produces BUY, SELL, or HOLD signals. Never places orders.

    Legacy for Phase 17: paper/backtest only — see module docstring.
    """

    legacy_non_executable_for_phase_17 = True

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or Settings()
        self._symbol = settings.symbol
        self._timeframe = Timeframe(settings.timeframe)
        self._rsi_long_min = settings.rsi_long_min
        self._rsi_long_max = settings.rsi_long_max
        self._rsi_short_min = settings.rsi_short_min
        self._rsi_short_max = settings.rsi_short_max

    @property
    def name(self) -> str:
        return STRATEGY_NAME

    def evaluate(self, bars: pd.DataFrame, indicators: IndicatorSnapshot | None = None) -> Signal:
        """
        Evaluate the latest bar and return a structured signal.

        If ``indicators`` is omitted, they are computed from ``bars``.
        """
        IndicatorCalculator.validate_bars(bars)
        if bars.empty:
            msg = "Cannot evaluate strategy on empty DataFrame"
            raise ValueError(msg)

        close, timestamp = _extract_bar_context(bars)
        snapshot = indicators if indicators is not None else IndicatorCalculator.compute(bars)

        return self._decide(close=close, timestamp=timestamp, indicators=snapshot)

    def _decide(
        self,
        *,
        close: float,
        timestamp: datetime,
        indicators: IndicatorSnapshot,
    ) -> Signal:
        ema_20 = indicators.ema_20
        ema_50 = indicators.ema_50
        ema_200 = indicators.ema_200
        rsi_14 = indicators.rsi_14

        missing = _missing_indicators(indicators)
        if missing:
            return Signal.create(
                action=SignalAction.HOLD,
                strategy_name=self.name,
                symbol=self._symbol,
                timeframe=self._timeframe,
                entry_price=close,
                timestamp=timestamp,
                indicators=indicators,
                reason=f"Insufficient indicator data: {', '.join(missing)}",
            )

        assert ema_20 is not None and ema_50 is not None and ema_200 is not None
        assert rsi_14 is not None

        if _is_buy_signal(
            close=close,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
            rsi_14=rsi_14,
            rsi_min=self._rsi_long_min,
            rsi_max=self._rsi_long_max,
        ):
            return Signal.create(
                action=SignalAction.BUY,
                strategy_name=self.name,
                symbol=self._symbol,
                timeframe=self._timeframe,
                entry_price=close,
                timestamp=timestamp,
                indicators=indicators,
                reason=(
                    "BUY: EMA20 > EMA50 > EMA200, close > EMA20, "
                    f"RSI14 in ({self._rsi_long_min}, {self._rsi_long_max})"
                ),
            )

        if _is_sell_signal(
            close=close,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
            rsi_14=rsi_14,
            rsi_min=self._rsi_short_min,
            rsi_max=self._rsi_short_max,
        ):
            return Signal.create(
                action=SignalAction.SELL,
                strategy_name=self.name,
                symbol=self._symbol,
                timeframe=self._timeframe,
                entry_price=close,
                timestamp=timestamp,
                indicators=indicators,
                reason=(
                    "SELL: EMA20 < EMA50 < EMA200, close < EMA20, "
                    f"RSI14 in ({self._rsi_short_min}, {self._rsi_short_max})"
                ),
            )

        hold_reason = _hold_reason(
            close=close,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
            rsi_14=rsi_14,
            rsi_long_min=self._rsi_long_min,
            rsi_long_max=self._rsi_long_max,
            rsi_short_min=self._rsi_short_min,
            rsi_short_max=self._rsi_short_max,
        )
        return Signal.create(
            action=SignalAction.HOLD,
            strategy_name=self.name,
            symbol=self._symbol,
            timeframe=self._timeframe,
            entry_price=close,
            timestamp=timestamp,
            indicators=indicators,
            reason=hold_reason,
        )


def _is_buy_signal(
    *,
    close: float,
    ema_20: float,
    ema_50: float,
    ema_200: float,
    rsi_14: float,
    rsi_min: float,
    rsi_max: float,
) -> bool:
    return (
        ema_20 > ema_50
        and ema_50 > ema_200
        and close > ema_20
        and rsi_min < rsi_14 < rsi_max
    )


def _is_sell_signal(
    *,
    close: float,
    ema_20: float,
    ema_50: float,
    ema_200: float,
    rsi_14: float,
    rsi_min: float,
    rsi_max: float,
) -> bool:
    return (
        ema_20 < ema_50
        and ema_50 < ema_200
        and close < ema_20
        and rsi_min < rsi_14 < rsi_max
    )


def _missing_indicators(indicators: IndicatorSnapshot) -> list[str]:
    missing: list[str] = []
    if indicators.ema_20 is None:
        missing.append("ema_20")
    if indicators.ema_50 is None:
        missing.append("ema_50")
    if indicators.ema_200 is None:
        missing.append("ema_200")
    if indicators.rsi_14 is None:
        missing.append("rsi_14")
    return missing


def _hold_reason(
    *,
    close: float,
    ema_20: float,
    ema_50: float,
    ema_200: float,
    rsi_14: float,
    rsi_long_min: float,
    rsi_long_max: float,
    rsi_short_min: float,
    rsi_short_max: float,
) -> str:
    bullish_ema = ema_20 > ema_50 > ema_200
    bearish_ema = ema_20 < ema_50 < ema_200

    if bullish_ema:
        if close <= ema_20:
            return "HOLD: bullish EMA alignment but close <= EMA20"
        if rsi_14 >= rsi_long_max:
            return f"HOLD: bullish EMA but RSI14 >= {rsi_long_max} (overbought)"
        if rsi_14 <= rsi_long_min:
            return f"HOLD: bullish EMA but RSI14 <= {rsi_long_min}"

    if bearish_ema:
        if close >= ema_20:
            return "HOLD: bearish EMA alignment but close >= EMA20"
        if rsi_14 <= rsi_short_min:
            return f"HOLD: bearish EMA but RSI14 <= {rsi_short_min} (oversold)"
        if rsi_14 >= rsi_short_max:
            return f"HOLD: bearish EMA but RSI14 >= {rsi_short_max}"

    return "HOLD: no EMA trend alignment (mixed/compressed market)"


def _extract_bar_context(bars: pd.DataFrame) -> tuple[float, datetime]:
    latest = bars.iloc[-1]
    close = float(latest["close"])
    timestamp = latest.get("timestamp")
    if timestamp is None or (isinstance(timestamp, float) and pd.isna(timestamp)):
        timestamp = datetime.now(tz=UTC)
    elif isinstance(timestamp, pd.Timestamp):
        timestamp = timestamp.to_pydatetime()
    return close, timestamp
