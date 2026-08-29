"""Unit tests for EmaRsiAtrStrategy."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalAction, SignalDirection, Timeframe
from exness_bot.domain.models import IndicatorSnapshot, Signal
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME, EmaRsiAtrStrategy
from tests.fixtures.ohlc_data import make_downtrend_ohlc, make_uptrend_ohlc


def _bars(close: float, *, timestamp: datetime | None = None) -> pd.DataFrame:
    ts = timestamp or datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return pd.DataFrame(
        {
            "open": [close - 0.5],
            "high": [close + 1.0],
            "low": [close - 1.0],
            "close": [close],
            "timestamp": [ts],
        }
    )


def _indicators(
    *,
    ema_20: float | None = 110.0,
    ema_50: float | None = 105.0,
    ema_200: float | None = 100.0,
    rsi_14: float | None = 60.0,
    atr_14: float | None = 2.0,
) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ema_20=ema_20,
        ema_50=ema_50,
        ema_200=ema_200,
        rsi_14=rsi_14,
        atr_14=atr_14,
    )


@pytest.fixture
def strategy() -> EmaRsiAtrStrategy:
    return EmaRsiAtrStrategy(Settings(SYMBOL="XAUUSD", TIMEFRAME="M15"))


class TestStrategyMetadata:
    def test_strategy_name(self, strategy: EmaRsiAtrStrategy) -> None:
        assert strategy.name == STRATEGY_NAME
        assert strategy.name == "ema_rsi_atr_v1"


class TestBuySignal:
    def test_buy_all_conditions_met(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(115.0), _indicators(rsi_14=60.0))
        assert signal.action == SignalAction.BUY
        assert signal.direction == SignalDirection.LONG
        assert signal.symbol == "XAUUSD"
        assert signal.timeframe == Timeframe.M15
        assert signal.entry_price == 115.0
        assert signal.strategy_name == STRATEGY_NAME
        assert "BUY" in signal.reason
        assert signal.indicators.rsi_14 == 60.0

    def test_buy_rsi_at_lower_bound_exclusive(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(115.0), _indicators(rsi_14=50.0))
        assert signal.action == SignalAction.HOLD
        assert "RSI14" in signal.reason

    def test_buy_rsi_just_above_lower_bound(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(115.0), _indicators(rsi_14=50.01))
        assert signal.action == SignalAction.BUY

    def test_buy_rsi_at_upper_bound_exclusive(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(115.0), _indicators(rsi_14=70.0))
        assert signal.action == SignalAction.HOLD
        assert "overbought" in signal.reason.lower()

    def test_buy_rsi_just_below_upper_bound(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(115.0), _indicators(rsi_14=69.99))
        assert signal.action == SignalAction.BUY

    def test_buy_close_not_above_ema20(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(110.0), _indicators(rsi_14=60.0))
        assert signal.action == SignalAction.HOLD
        assert "close <= EMA20" in signal.reason

    def test_buy_close_equal_ema20(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(110.0), _indicators(rsi_14=60.0))
        assert signal.action == SignalAction.HOLD

    def test_buy_invalid_ema_alignment(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(115.0),
            _indicators(ema_20=100.0, ema_50=105.0, ema_200=110.0, rsi_14=60.0),
        )
        assert signal.action == SignalAction.HOLD
        assert signal.reason.startswith("HOLD:")


class TestSellSignal:
    def test_sell_all_conditions_met(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(85.0),
            _indicators(ema_20=90.0, ema_50=95.0, ema_200=100.0, rsi_14=40.0),
        )
        assert signal.action == SignalAction.SELL
        assert signal.direction == SignalDirection.SHORT
        assert signal.entry_price == 85.0
        assert "SELL" in signal.reason

    def test_sell_rsi_at_lower_bound_exclusive(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(85.0),
            _indicators(ema_20=90.0, ema_50=95.0, ema_200=100.0, rsi_14=30.0),
        )
        assert signal.action == SignalAction.HOLD
        assert "oversold" in signal.reason.lower()

    def test_sell_rsi_just_above_lower_bound(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(85.0),
            _indicators(ema_20=90.0, ema_50=95.0, ema_200=100.0, rsi_14=30.01),
        )
        assert signal.action == SignalAction.SELL

    def test_sell_rsi_at_upper_bound_exclusive(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(85.0),
            _indicators(ema_20=90.0, ema_50=95.0, ema_200=100.0, rsi_14=50.0),
        )
        assert signal.action == SignalAction.HOLD

    def test_sell_rsi_just_below_upper_bound(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(85.0),
            _indicators(ema_20=90.0, ema_50=95.0, ema_200=100.0, rsi_14=49.99),
        )
        assert signal.action == SignalAction.SELL

    def test_sell_close_not_below_ema20(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(90.0),
            _indicators(ema_20=90.0, ema_50=95.0, ema_200=100.0, rsi_14=40.0),
        )
        assert signal.action == SignalAction.HOLD
        assert "close >= EMA20" in signal.reason

    def test_sell_invalid_ema_alignment(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(85.0),
            _indicators(ema_20=110.0, ema_50=105.0, ema_200=100.0, rsi_14=40.0),
        )
        assert signal.action == SignalAction.HOLD


class TestHoldSignal:
    def test_hold_mixed_ema(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(100.0),
            _indicators(ema_20=105.0, ema_50=100.0, ema_200=102.0, rsi_14=55.0),
        )
        assert signal.action == SignalAction.HOLD
        assert signal.direction == SignalDirection.FLAT
        assert "no EMA trend alignment" in signal.reason

    def test_hold_insufficient_ema_200(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(115.0), _indicators(ema_200=None))
        assert signal.action == SignalAction.HOLD
        assert "Insufficient indicator data" in signal.reason
        assert "ema_200" in signal.reason

    def test_hold_missing_rsi(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(115.0), _indicators(rsi_14=None))
        assert signal.action == SignalAction.HOLD
        assert "rsi_14" in signal.reason

    def test_hold_bullish_rsi_too_high(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(_bars(115.0), _indicators(rsi_14=75.0))
        assert signal.action == SignalAction.HOLD

    def test_hold_bearish_rsi_too_low(self, strategy: EmaRsiAtrStrategy) -> None:
        signal = strategy.evaluate(
            _bars(85.0),
            _indicators(ema_20=90.0, ema_50=95.0, ema_200=100.0, rsi_14=25.0),
        )
        assert signal.action == SignalAction.HOLD


class TestSignalStructure:
    def test_signal_create_factory(self) -> None:
        indicators = _indicators()
        signal = Signal.create(
            action=SignalAction.BUY,
            strategy_name=STRATEGY_NAME,
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            entry_price=115.0,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            indicators=indicators,
            reason="test",
        )
        assert signal.action == SignalAction.BUY
        assert signal.direction == SignalDirection.LONG

    def test_evaluate_empty_bars_raises(self, strategy: EmaRsiAtrStrategy) -> None:
        empty = pd.DataFrame(columns=["open", "high", "low", "close"])
        with pytest.raises(ValueError, match="empty"):
            strategy.evaluate(empty)


class TestIntegrationWithComputedIndicators:
    def test_uptrend_may_produce_buy_or_hold(self, strategy: EmaRsiAtrStrategy) -> None:
        bars = make_uptrend_ohlc(length=250)
        signal = strategy.evaluate(bars)
        assert signal.action in (SignalAction.BUY, SignalAction.HOLD)
        assert signal.strategy_name == STRATEGY_NAME
        assert signal.indicators.ema_200 is not None

    def test_downtrend_may_produce_sell_or_hold(self, strategy: EmaRsiAtrStrategy) -> None:
        bars = make_downtrend_ohlc(length=250)
        signal = strategy.evaluate(bars)
        assert signal.action in (SignalAction.SELL, SignalAction.HOLD)
        assert signal.indicators.ema_200 is not None

    def test_short_history_produces_hold(self, strategy: EmaRsiAtrStrategy) -> None:
        bars = make_uptrend_ohlc(length=10)
        signal = strategy.evaluate(bars)
        assert signal.action == SignalAction.HOLD
        assert "Insufficient indicator data" in signal.reason
