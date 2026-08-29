"""Tests for order execution layer."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import OrderType, SignalDirection
from exness_bot.domain.models import (
    ApprovedOrderPlan,
    OrderRequest,
    OrderResult,
    Position,
)
from exness_bot.orders.context import OrderExecutionContext
from exness_bot.orders.manager import OrderManager
from tests.fixtures.risk_data import make_account, make_buy_signal, make_xauusd_symbol


def _make_plan(
    *,
    volume: float = 0.01,
    stop_loss: float = 2338.0,
    take_profit: float = 2374.0,
) -> ApprovedOrderPlan:
    signal = make_buy_signal(entry_price=2350.0)
    order_request = OrderRequest(
        symbol="XAUUSD",
        volume=volume,
        order_type=OrderType.MARKET,
        direction=SignalDirection.LONG,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    return ApprovedOrderPlan(
        signal=signal,
        volume=volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        order_request=order_request,
    )


def _make_context(
    *,
    open_positions: list[Position] | None = None,
    trade_mode: str = "demo",
) -> OrderExecutionContext:
    return OrderExecutionContext(
        account=make_account(trade_mode=trade_mode),
        symbol_info=make_xauusd_symbol(),
        open_positions=open_positions or [],
    )


def _make_position(
    *,
    ticket: int = 1001,
    volume: float = 0.01,
    direction: SignalDirection = SignalDirection.LONG,
) -> Position:
    return Position(
        ticket=ticket,
        symbol="XAUUSD",
        volume=volume,
        direction=direction,
        open_price=2350.0,
        current_price=2351.0,
        stop_loss=2338.0,
        take_profit=2374.0,
        profit=10.0,
        open_time=datetime(2026, 1, 1, tzinfo=UTC),
    )


class TestOpenMarketOrder:
    def test_dry_run_validates_and_logs_without_broker_call(self) -> None:
        broker = MagicMock()
        settings = Settings(TRADING_MODE="demo", DRY_RUN=True)
        manager = OrderManager(broker=broker, settings=settings)
        context = _make_context()

        result = manager.open_market_order(_make_plan(), context)

        assert result.success is True
        assert result.dry_run is True
        assert result.volume == 0.01
        assert result.execution_price == 2350.0
        broker.open_market_order.assert_not_called()

    def test_validation_rejects_duplicate_position(self) -> None:
        broker = MagicMock()
        settings = Settings(TRADING_MODE="demo", DRY_RUN=False, MAX_OPEN_POSITIONS=3)
        manager = OrderManager(broker=broker, settings=settings)
        context = _make_context(open_positions=[_make_position()])

        result = manager.open_market_order(_make_plan(), context)

        assert result.success is False
        assert result.error_message is not None
        assert "Duplicate position" in result.error_message
        broker.open_market_order.assert_not_called()

    def test_demo_mode_submits_and_reconciles_success(self) -> None:
        broker = MagicMock()
        broker.open_market_order.return_value = OrderResult(
            success=True,
            ticket=1001,
            execution_price=2350.25,
            volume=0.01,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        broker.get_open_positions.return_value = [_make_position(ticket=1001)]
        settings = Settings(TRADING_MODE="demo", DRY_RUN=False)
        manager = OrderManager(broker=broker, settings=settings)

        result = manager.open_market_order(_make_plan(), _make_context())

        assert result.success is True
        assert result.reconciled is True
        assert result.ticket == 1001
        broker.open_market_order.assert_called_once()

    def test_broker_rejection_returns_error(self) -> None:
        broker = MagicMock()
        broker.open_market_order.return_value = OrderResult(
            success=False,
            error_code=10019,
            error_message="Not enough money",
        )
        settings = Settings(TRADING_MODE="demo", DRY_RUN=False)
        manager = OrderManager(broker=broker, settings=settings)

        result = manager.open_market_order(_make_plan(), _make_context())

        assert result.success is False
        assert result.error_code == 10019
        assert result.error_message == "Not enough money"
        broker.get_open_positions.assert_not_called()

    def test_success_without_reconciliation_marks_failure(self) -> None:
        broker = MagicMock()
        broker.open_market_order.return_value = OrderResult(
            success=True,
            ticket=9999,
            execution_price=2350.25,
            volume=0.01,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        broker.get_open_positions.return_value = []
        settings = Settings(TRADING_MODE="demo", DRY_RUN=False)
        manager = OrderManager(broker=broker, settings=settings)

        result = manager.open_market_order(_make_plan(), _make_context())

        assert result.success is True
        assert result.reconciled is False
        assert "No open position found" in (result.reconciliation_message or "")

    def test_live_mode_requires_demo_account_block(self) -> None:
        broker = MagicMock()
        settings = Settings(TRADING_MODE="live", DRY_RUN=False, ALLOW_LIVE_TRADING=True)
        manager = OrderManager(broker=broker, settings=settings)
        context = _make_context(trade_mode="demo")

        result = manager.open_market_order(_make_plan(), context)

        assert result.success is False
        assert "demo account" in (result.error_message or "").lower()
        broker.open_market_order.assert_not_called()


class TestClosePosition:
    def test_dry_run_close_does_not_call_broker(self) -> None:
        broker = MagicMock()
        settings = Settings(TRADING_MODE="demo", DRY_RUN=True)
        manager = OrderManager(broker=broker, settings=settings)

        result = manager.close_position(1001, "XAUUSD", _make_context())

        assert result.success is True
        assert result.dry_run is True
        broker.close_position.assert_not_called()

    def test_demo_close_calls_broker(self) -> None:
        broker = MagicMock()
        broker.close_position.return_value = OrderResult(
            success=True,
            ticket=1001,
            execution_price=2351.0,
            volume=0.01,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        settings = Settings(TRADING_MODE="demo", DRY_RUN=False)
        manager = OrderManager(broker=broker, settings=settings)

        result = manager.close_position(1001, "XAUUSD", _make_context())

        assert result.success is True
        broker.close_position.assert_called_once_with(1001, "XAUUSD", volume=None)


class TestModifyStops:
    def test_modify_stop_loss_dry_run(self) -> None:
        broker = MagicMock()
        settings = Settings(TRADING_MODE="demo", DRY_RUN=True)
        manager = OrderManager(broker=broker, settings=settings)

        result = manager.modify_stop_loss(1001, "XAUUSD", 2340.0, _make_context())

        assert result.success is True
        assert result.dry_run is True
        broker.modify_stop_loss.assert_not_called()

    def test_modify_take_profit_demo(self) -> None:
        broker = MagicMock()
        broker.modify_take_profit.return_value = OrderResult(
            success=True,
            ticket=1001,
            take_profit=2380.0,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        settings = Settings(TRADING_MODE="demo", DRY_RUN=False)
        manager = OrderManager(broker=broker, settings=settings)

        result = manager.modify_take_profit(1001, "XAUUSD", 2380.0, _make_context())

        assert result.success is True
        broker.modify_take_profit.assert_called_once_with(1001, "XAUUSD", 2380.0)

    @pytest.mark.parametrize("stop_loss", [0.0, -1.0])
    def test_modify_stop_loss_rejects_invalid_value(self, stop_loss: float) -> None:
        broker = MagicMock()
        settings = Settings(TRADING_MODE="demo", DRY_RUN=False)
        manager = OrderManager(broker=broker, settings=settings)

        result = manager.modify_stop_loss(1001, "XAUUSD", stop_loss, _make_context())

        assert result.success is False
        broker.modify_stop_loss.assert_not_called()


class TestReconcilePositions:
    def test_reconcile_matching_positions(self) -> None:
        broker = MagicMock()
        broker.get_open_positions.return_value = [_make_position(ticket=1001, volume=0.01)]
        manager = OrderManager(broker=MagicMock(), settings=Settings())
        manager._broker = broker

        results = manager.reconcile_positions([_make_position(ticket=1001, volume=0.01)])

        assert len(results) == 1
        assert results[0][1] is True

    def test_reconcile_missing_position(self) -> None:
        broker = MagicMock()
        broker.get_open_positions.return_value = []
        manager = OrderManager(broker=MagicMock(), settings=Settings())
        manager._broker = broker

        results = manager.reconcile_positions([_make_position(ticket=1001)])

        assert results[0][1] is False
        assert "missing" in results[0][2].lower()
