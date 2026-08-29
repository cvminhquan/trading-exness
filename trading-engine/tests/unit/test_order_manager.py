"""Tests for order manager."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import OrderType, SignalDirection
from exness_bot.domain.models import ApprovedOrderPlan, OrderRequest, OrderResult
from exness_bot.orders.context import OrderExecutionContext
from exness_bot.orders.manager import OrderManager
from tests.fixtures.risk_data import make_account, make_buy_signal, make_xauusd_symbol


def _make_plan() -> ApprovedOrderPlan:
    signal = make_buy_signal(entry_price=2350.0)
    order_request = OrderRequest(
        symbol="XAUUSD",
        volume=0.01,
        order_type=OrderType.MARKET,
        direction=SignalDirection.LONG,
        stop_loss=2338.0,
        take_profit=2374.0,
    )
    return ApprovedOrderPlan(
        signal=signal,
        volume=0.01,
        stop_loss=2338.0,
        take_profit=2374.0,
        order_request=order_request,
    )


def _make_context() -> OrderExecutionContext:
    return OrderExecutionContext(
        account=make_account(trade_mode="real"),
        symbol_info=make_xauusd_symbol(),
    )


class TestOrderManager:
    def test_dry_run_does_not_call_broker(self) -> None:
        broker = MagicMock()
        settings = Settings(DRY_RUN=True)
        manager = OrderManager(broker=broker, settings=settings)
        context = OrderExecutionContext(
            account=make_account(),
            symbol_info=make_xauusd_symbol(),
        )
        result = manager.execute(_make_plan(), context)
        assert result.dry_run is True
        assert result.success is True
        broker.open_market_order.assert_not_called()

    def test_non_dry_run_live_calls_broker(self) -> None:
        broker = MagicMock()
        broker.open_market_order.return_value = OrderResult(
            success=True,
            ticket=123,
            execution_price=2350.0,
            volume=0.01,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        broker.get_open_positions.return_value = []
        settings = Settings(TRADING_MODE="live", DRY_RUN=False, ALLOW_LIVE_TRADING=True)
        manager = OrderManager(broker=broker, settings=settings)
        manager.execute(_make_plan(), _make_context())
        broker.open_market_order.assert_called_once()
