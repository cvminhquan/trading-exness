"""Unit tests for stop loss and take profit calculations."""

import pytest

from exness_bot.domain.enums import SignalAction, SignalDirection
from exness_bot.risk.stops import (
    action_to_direction,
    calculate_stop_distance,
    calculate_stop_loss,
    calculate_take_profit,
)


class TestStopDistance:
    def test_calculate_stop_distance(self) -> None:
        assert calculate_stop_distance(2.0, 1.5) == pytest.approx(3.0)

    def test_invalid_atr_raises(self) -> None:
        with pytest.raises(ValueError, match="ATR"):
            calculate_stop_distance(0.0, 1.5)


class TestStopLoss:
    def test_long_stop_loss(self) -> None:
        sl = calculate_stop_loss(2350.0, SignalDirection.LONG, atr=2.0, multiplier=1.5)
        assert sl == pytest.approx(2347.0)

    def test_short_stop_loss(self) -> None:
        sl = calculate_stop_loss(2350.0, SignalDirection.SHORT, atr=2.0, multiplier=1.5)
        assert sl == pytest.approx(2353.0)


class TestTakeProfit:
    def test_long_take_profit(self) -> None:
        tp = calculate_take_profit(
            entry_price=2350.0,
            stop_loss=2347.0,
            direction=SignalDirection.LONG,
            reward_risk_ratio=2.0,
        )
        assert tp == pytest.approx(2356.0)

    def test_short_take_profit(self) -> None:
        tp = calculate_take_profit(
            entry_price=2350.0,
            stop_loss=2353.0,
            direction=SignalDirection.SHORT,
            reward_risk_ratio=2.0,
        )
        assert tp == pytest.approx(2344.0)


class TestActionToDirection:
    def test_buy_maps_to_long(self) -> None:
        assert action_to_direction(SignalAction.BUY) == SignalDirection.LONG

    def test_sell_maps_to_short(self) -> None:
        assert action_to_direction(SignalAction.SELL) == SignalDirection.SHORT

    def test_hold_raises(self) -> None:
        with pytest.raises(ValueError):
            action_to_direction(SignalAction.HOLD)
