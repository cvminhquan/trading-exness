"""Tests for broker domain models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from exness_bot.domain.enums import OrderType, SignalDirection, Timeframe
from exness_bot.domain.models import (
    AccountInfo,
    Candle,
    HealthStatus,
    PendingOrder,
    SymbolInfo,
    Tick,
)


class TestAccountInfo:
    def test_create_account(self) -> None:
        account = AccountInfo(
            login=12345,
            balance=10000.0,
            equity=10050.0,
            margin=100.0,
            free_margin=9950.0,
            leverage=500,
            name="Demo",
            server="Exness-MT5Trial",
            trade_mode="demo",
        )
        assert account.trade_mode == "demo"
        assert account.leverage == 500


class TestSymbolInfo:
    def test_create_symbol_info(self) -> None:
        info = SymbolInfo(
            symbol="XAUUSD",
            bid=2350.10,
            ask=2350.30,
            point=0.01,
            digits=2,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            spread=20,
            trade_mode=4,
            visible=True,
        )
        assert info.symbol == "XAUUSD"


class TestTick:
    def test_create_tick(self) -> None:
        tick = Tick(
            symbol="XAUUSD",
            bid=2350.10,
            ask=2350.30,
            last=2350.20,
            volume=100.0,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert tick.bid == 2350.10


class TestCandle:
    def test_create_candle(self) -> None:
        candle = Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            open=2350.0,
            high=2355.0,
            low=2348.0,
            close=2352.0,
            volume=500.0,
            spread=2,
        )
        assert candle.timeframe == Timeframe.M15

    def test_candle_is_frozen(self) -> None:
        candle = Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=1.0,
        )
        with pytest.raises(ValidationError):
            candle.close = 999.0  # type: ignore[misc]


class TestPendingOrder:
    def test_create_pending_order(self) -> None:
        order = PendingOrder(
            ticket=2001,
            symbol="XAUUSD",
            order_type=OrderType.LIMIT,
            direction=SignalDirection.LONG,
            volume=0.01,
            price=2340.0,
            setup_time=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert order.order_type == OrderType.LIMIT


class TestHealthStatus:
    def test_create_health_status(self) -> None:
        status = HealthStatus(
            connected=True,
            terminal_connected=True,
            trade_allowed=True,
            account_login=12345,
            server="Exness-MT5Trial",
            message="OK",
        )
        assert status.connected is True
