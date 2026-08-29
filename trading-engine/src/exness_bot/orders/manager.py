"""Order manager — the only module allowed to submit trading orders."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from exness_bot.broker.execution import ExecutableBroker
from exness_bot.config.safety import SafetyGuard
from exness_bot.config.settings import Settings
from exness_bot.domain.models import ApprovedOrderPlan, OrderRequest, OrderResult, Position
from exness_bot.orders.context import OrderExecutionContext
from exness_bot.orders.reconciliation import reconcile_new_position, reconcile_positions
from exness_bot.orders.validation import validate_order_submission

logger = structlog.get_logger(__name__)


class OrderManager:
    """Execute and manage orders with safety guards and reconciliation."""

    def __init__(
        self,
        broker: ExecutableBroker,
        settings: Settings,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        self._broker = broker
        self._settings = settings
        self._safety = safety_guard or SafetyGuard(settings)

    def execute(
        self,
        plan: ApprovedOrderPlan,
        context: OrderExecutionContext,
    ) -> OrderResult:
        """Execute an approved order plan (alias for open_market_order)."""
        return self.open_market_order(plan, context)

    def open_market_order(
        self,
        plan: ApprovedOrderPlan,
        context: OrderExecutionContext,
    ) -> OrderResult:
        """Open a market order from a risk-approved plan."""
        if (reason := validate_order_submission(plan, context, self._settings)) is not None:
            return self._failure(plan.order_request, reason)

        self._log_request("open_market_order", plan.order_request, plan.stop_loss, plan.take_profit)

        if self._settings.is_dry_run_mode:
            return self._dry_run_result(plan)

        safety = self._safety.check_order_submission(context.account)
        if not safety.allowed:
            return self._failure(plan.order_request, safety.message)

        broker_result = self._broker.open_market_order(plan.order_request)
        self._log_response("open_market_order", plan.order_request, broker_result)

        if not broker_result.success:
            return broker_result

        return self._reconcile_after_open(plan, broker_result)

    def close_position(
        self,
        ticket: int,
        symbol: str,
        context: OrderExecutionContext,
        volume: float | None = None,
    ) -> OrderResult:
        """Close an existing position."""
        if context.account.equity <= 0:
            return OrderResult(success=False, error_message="Account equity unavailable")

        logger.info(
            "order_request",
            operation="close_position",
            ticket=ticket,
            symbol=symbol,
            volume=volume,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )

        if self._settings.is_dry_run_mode:
            return OrderResult(
                success=True,
                dry_run=True,
                ticket=ticket,
                error_message="Dry-run: close position logged, not submitted",
                timestamp=datetime.now(tz=UTC),
            )

        safety = self._safety.check_order_submission(context.account)
        if not safety.allowed:
            return OrderResult(success=False, error_message=safety.message, ticket=ticket)

        result = self._broker.close_position(ticket, symbol, volume=volume)
        logger.info(
            "order_response",
            operation="close_position",
            symbol=symbol,
            success=result.success,
            ticket=result.ticket or ticket,
            execution_price=result.execution_price,
            volume=result.volume,
            error_code=result.error_code,
            error_message=result.error_message,
            timestamp=result.timestamp.isoformat() if result.timestamp else None,
        )
        return result

    def modify_stop_loss(
        self,
        ticket: int,
        symbol: str,
        stop_loss: float,
        context: OrderExecutionContext,
    ) -> OrderResult:
        """Modify stop loss on an open position."""
        if stop_loss <= 0:
            return OrderResult(success=False, error_message="Stop loss must be positive")

        if self._settings.is_dry_run_mode:
            logger.info("order_dry_run_modify_sl", ticket=ticket, stop_loss=stop_loss)
            return OrderResult(
                success=True,
                dry_run=True,
                ticket=ticket,
                stop_loss=stop_loss,
                error_message="Dry-run: modify SL logged, not submitted",
                timestamp=datetime.now(tz=UTC),
            )

        safety = self._safety.check_order_submission(context.account)
        if not safety.allowed:
            return OrderResult(success=False, error_message=safety.message, ticket=ticket)

        result = self._broker.modify_stop_loss(ticket, symbol, stop_loss)
        logger.info("order_modify_sl_response", ticket=ticket, success=result.success)
        return result

    def modify_take_profit(
        self,
        ticket: int,
        symbol: str,
        take_profit: float,
        context: OrderExecutionContext,
    ) -> OrderResult:
        """Modify take profit on an open position."""
        if take_profit <= 0:
            return OrderResult(success=False, error_message="Take profit must be positive")

        if self._settings.is_dry_run_mode:
            logger.info("order_dry_run_modify_tp", ticket=ticket, take_profit=take_profit)
            return OrderResult(
                success=True,
                dry_run=True,
                ticket=ticket,
                take_profit=take_profit,
                error_message="Dry-run: modify TP logged, not submitted",
                timestamp=datetime.now(tz=UTC),
            )

        safety = self._safety.check_order_submission(context.account)
        if not safety.allowed:
            return OrderResult(success=False, error_message=safety.message, ticket=ticket)

        result = self._broker.modify_take_profit(ticket, symbol, take_profit)
        logger.info("order_modify_tp_response", ticket=ticket, success=result.success)
        return result

    def reconcile_positions(
        self,
        expected: list[Position],
        *,
        symbol: str | None = None,
    ) -> list[tuple[int, bool, str]]:
        """Reconcile expected positions against broker state."""
        broker_positions = self._broker.get_open_positions(symbol)
        return reconcile_positions(broker_positions, expected)

    def _reconcile_after_open(
        self,
        plan: ApprovedOrderPlan,
        broker_result: OrderResult,
    ) -> OrderResult:
        positions = self._broker.get_open_positions(plan.order_request.symbol)
        matched, message, _ = reconcile_new_position(
            positions,
            symbol=plan.order_request.symbol,
            direction=plan.order_request.direction,
            expected_volume=plan.volume,
            ticket=broker_result.ticket,
        )

        reconciled_result = broker_result.model_copy(
            update={
                "reconciled": matched,
                "reconciliation_message": message,
                "volume": broker_result.volume or plan.volume,
                "stop_loss": plan.stop_loss,
                "take_profit": plan.take_profit,
            }
        )
        logger.info(
            "order_reconciled",
            ticket=reconciled_result.ticket,
            matched=matched,
            message=message,
        )
        if not matched:
            logger.warning("order_reconciliation_failed", message=message)
        return reconciled_result

    def _dry_run_result(self, plan: ApprovedOrderPlan) -> OrderResult:
        logger.info(
            "order_dry_run",
            symbol=plan.order_request.symbol,
            direction=plan.order_request.direction.value,
            volume=plan.volume,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            entry=plan.signal.entry_price,
        )
        return OrderResult(
            success=True,
            dry_run=True,
            volume=plan.volume,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            execution_price=plan.signal.entry_price,
            error_message="Dry-run: order logged, not submitted to MT5",
            timestamp=datetime.now(tz=UTC),
        )

    @staticmethod
    def _failure(request: OrderRequest, reason: str) -> OrderResult:
        logger.info(
            "order_rejected",
            symbol=request.symbol,
            direction=request.direction.value,
            reason=reason,
        )
        return OrderResult(success=False, error_message=reason)

    @staticmethod
    def _log_request(
        operation: str,
        request: OrderRequest,
        stop_loss: float | None,
        take_profit: float | None,
        *,
        ticket: int | None = None,
    ) -> None:
        logger.info(
            "order_request",
            operation=operation,
            symbol=request.symbol,
            direction=request.direction.value,
            volume=request.volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            ticket=ticket,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )

    @staticmethod
    def _log_response(
        operation: str,
        request: OrderRequest,
        result: OrderResult,
        *,
        ticket: int | None = None,
    ) -> None:
        logger.info(
            "order_response",
            operation=operation,
            symbol=request.symbol,
            success=result.success,
            ticket=result.ticket or ticket,
            execution_price=result.execution_price,
            volume=result.volume,
            stop_loss=result.stop_loss,
            take_profit=result.take_profit,
            error_code=result.error_code,
            error_message=result.error_message,
            timestamp=result.timestamp.isoformat() if result.timestamp else None,
        )
