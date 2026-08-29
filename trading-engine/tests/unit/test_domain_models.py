"""Tests for domain models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from exness_bot.domain.enums import OrderType, SignalAction, SignalDirection, Timeframe
from exness_bot.domain.models import (
    AccountInfo,
    Bar,
    IndicatorSnapshot,
    OrderRequest,
    OrderResult,
    Signal,
)


class TestBar:
    def test_create_bar(self) -> None:
        bar = Bar(
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            open=2350.0,
            high=2355.0,
            low=2348.0,
            close=2352.0,
            volume=100.0,
        )
        assert bar.close == 2352.0

    def test_bar_is_frozen(self) -> None:
        bar = Bar(
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
        )
        with pytest.raises(ValidationError):
            bar.close = 999.0  # type: ignore[misc]


class TestSignal:
    def test_create_signal(self) -> None:
        indicators = IndicatorSnapshot(timestamp=datetime(2026, 1, 1, tzinfo=UTC))
        signal = Signal.create(
            action=SignalAction.BUY,
            strategy_name="ema_trend_rsi",
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            entry_price=2350.0,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            indicators=indicators,
            reason="test signal",
        )
        assert signal.action == SignalAction.BUY
        assert signal.direction == SignalDirection.LONG
        assert signal.symbol == "XAUUSD"


class TestOrderRequest:
    def test_create_market_order(self) -> None:
        request = OrderRequest(
            symbol="XAUUSD",
            volume=0.01,
            order_type=OrderType.MARKET,
            direction=SignalDirection.LONG,
            stop_loss=2338.0,
            take_profit=2374.0,
        )
        assert request.order_type == OrderType.MARKET


class TestOrderResult:
    def test_dry_run_result(self) -> None:
        result = OrderResult(success=True, dry_run=True, error_message="DRY_RUN enabled")
        assert result.dry_run is True
        assert result.ticket is None


class TestAccountInfo:
    def test_create_account(self) -> None:
        account = AccountInfo(
            login=12345,
            balance=10000.0,
            equity=10050.0,
            margin=100.0,
            free_margin=9950.0,
        )
        assert account.equity == 10050.0
