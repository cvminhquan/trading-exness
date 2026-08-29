"""Tests for MT5 mapper functions."""

from types import SimpleNamespace

import numpy as np
import pytest

from exness_bot.broker.mt5.mapper import (
    MT5_TRADE_MODE_DISABLED,
    MT5_TRADE_MODE_FULL,
    is_market_closed,
    map_account_info,
    map_pending_order,
    map_position,
    map_rates_to_candles,
    map_symbol_info,
    map_tick,
    timeframe_to_mt5,
)
from exness_bot.domain.enums import OrderType, SignalDirection, Timeframe
from exness_bot.domain.models import SymbolInfo, Tick


class TestTimeframeMapping:
    def test_m15_maps_to_mt5_constant(self) -> None:
        assert timeframe_to_mt5(Timeframe.M15) == 15

    def test_unsupported_timeframe_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            timeframe_to_mt5("INVALID")  # type: ignore[arg-type]


class TestAccountMapping:
    def test_map_account_info(self, mt5_account_raw: SimpleNamespace) -> None:
        account = map_account_info(mt5_account_raw)
        assert account.login == 12345678
        assert account.balance == 10000.0
        assert account.trade_mode == "demo"
        assert account.currency == "USD"


class TestSymbolMapping:
    def test_map_symbol_info(self, mt5_symbol_raw: SimpleNamespace) -> None:
        info = map_symbol_info(mt5_symbol_raw)
        assert info.symbol == "XAUUSD"
        assert info.digits == 2
        assert info.volume_step == 0.01


class TestTickMapping:
    def test_map_tick(self, mt5_tick_raw: SimpleNamespace) -> None:
        tick = map_tick("XAUUSD", mt5_tick_raw)
        assert tick.symbol == "XAUUSD"
        assert tick.bid == 2350.10
        assert tick.timestamp.tzinfo is not None


class TestCandleMapping:
    def test_map_rates_to_candles(self, mt5_rates_array: np.ndarray) -> None:
        candles = map_rates_to_candles(
            mt5_rates_array,
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
        )
        assert len(candles) == 2
        assert candles[0].symbol == "XAUUSD"
        assert candles[0].timeframe == Timeframe.M15
        assert candles[0].close == 2352.0
        assert candles[0].spread == 2

    def test_map_empty_rates_returns_empty_list(self) -> None:
        empty = np.array([], dtype=[("time", "i8"), ("open", "f8")])
        assert map_rates_to_candles(empty, symbol="XAUUSD", timeframe=Timeframe.M15) == []


class TestPositionMapping:
    def test_map_position(self, mt5_position_raw: SimpleNamespace) -> None:
        position = map_position(mt5_position_raw)
        assert position.ticket == 1001
        assert position.direction == SignalDirection.LONG
        assert position.stop_loss == 2338.0


class TestPendingOrderMapping:
    def test_map_pending_order(self, mt5_pending_order_raw: SimpleNamespace) -> None:
        order = map_pending_order(mt5_pending_order_raw)
        assert order.ticket == 2001
        assert order.order_type == OrderType.LIMIT
        assert order.direction == SignalDirection.LONG


class TestMarketClosedHeuristic:
    def test_disabled_trade_mode_is_closed(self) -> None:
        info = SymbolInfo(
            symbol="XAUUSD",
            bid=0.0,
            ask=0.0,
            point=0.01,
            digits=2,
            volume_min=0.01,
            volume_max=1.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            spread=0,
            trade_mode=MT5_TRADE_MODE_DISABLED,
            visible=True,
        )
        assert is_market_closed(info, None) is True

    def test_valid_tick_is_open(self, mt5_tick_raw: SimpleNamespace) -> None:
        info = SymbolInfo(
            symbol="XAUUSD",
            bid=2350.10,
            ask=2350.30,
            point=0.01,
            digits=2,
            volume_min=0.01,
            volume_max=1.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            spread=20,
            trade_mode=MT5_TRADE_MODE_FULL,
            visible=True,
        )
        tick = map_tick("XAUUSD", mt5_tick_raw)
        assert is_market_closed(info, tick) is False

    def test_zero_bid_is_closed(self) -> None:
        info = SymbolInfo(
            symbol="XAUUSD",
            bid=0.0,
            ask=0.0,
            point=0.01,
            digits=2,
            volume_min=0.01,
            volume_max=1.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            spread=0,
            trade_mode=MT5_TRADE_MODE_FULL,
            visible=True,
        )
        tick = Tick(
            symbol="XAUUSD",
            bid=0.0,
            ask=0.0,
            last=0.0,
            volume=0.0,
            timestamp=map_tick("XAUUSD", SimpleNamespace(
                bid=0.0, ask=0.0, last=0.0, volume=0.0, time=1_700_000_000
            )).timestamp,
        )
        assert is_market_closed(info, tick) is True
