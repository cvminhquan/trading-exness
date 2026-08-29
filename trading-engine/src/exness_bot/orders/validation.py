"""Pre-submission order validation."""

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import ApprovedOrderPlan, OrderRequest, Position
from exness_bot.orders.context import OrderExecutionContext
from exness_bot.risk.models import RiskState
from exness_bot.risk.position_sizer import normalize_lot_size
from exness_bot.risk.validators import (
    check_daily_loss,
    check_drawdown,
    check_margin,
    check_max_open_positions,
    check_minimum_lot,
    check_missing_account,
    check_missing_symbol,
    check_spread,
    check_trading_mode,
    estimate_required_margin,
)


def validate_order_submission(
    plan: ApprovedOrderPlan,
    context: OrderExecutionContext,
    settings: Settings,
) -> str | None:
    """
    Validate an approved plan before broker submission.

    Returns rejection reason or None if valid.
    """
    request = plan.order_request
    account = context.account
    symbol = context.symbol_info

    if (reason := check_missing_account(account)) is not None:
        return reason
    if (reason := check_missing_symbol(symbol)) is not None:
        return reason
    if (reason := check_trading_mode(settings, account)) is not None:
        return reason

    if request.symbol != plan.signal.symbol or request.symbol != symbol.symbol:
        return "Order symbol mismatch"

    if request.volume <= 0:
        return "Order volume must be positive"

    normalized = normalize_lot_size(
        request.volume,
        volume_min=symbol.volume_min,
        volume_max=symbol.volume_max,
        volume_step=symbol.volume_step,
    )
    if normalized != request.volume:
        return f"Order volume {request.volume} is not a valid lot step"

    if (reason := check_minimum_lot(request.volume, symbol.volume_min)) is not None:
        return reason

    if request.direction not in (SignalDirection.LONG, SignalDirection.SHORT):
        return f"Invalid order direction: {request.direction.value}"

    entry = context.entry_price or plan.signal.entry_price
    if entry <= 0:
        return "Entry price unavailable or invalid"

    if plan.stop_loss <= 0 or plan.take_profit <= 0:
        return "Stop loss and take profit must be positive"

    if request.direction == SignalDirection.LONG:
        if plan.stop_loss >= entry:
            return "Long stop loss must be below entry"
        if plan.take_profit <= entry:
            return "Long take profit must be above entry"
    else:
        if plan.stop_loss <= entry:
            return "Short stop loss must be above entry"
        if plan.take_profit >= entry:
            return "Short take profit must be below entry"

    if (reason := check_spread(symbol, settings.max_spread_points)) is not None:
        return reason

    state = context.risk_state or RiskState.from_equity(account.equity)
    if (reason := check_daily_loss(
        account.equity, state.day_start_equity, settings.max_daily_loss_pct
    )) is not None:
        return reason
    if (reason := check_drawdown(
        account.equity, state.peak_equity, settings.max_drawdown_pct
    )) is not None:
        return reason

    if (reason := check_max_open_positions(
        context.open_positions, request.symbol, settings.max_open_positions
    )) is not None:
        return reason

    if (reason := _check_duplicate_position(context.open_positions, request)) is not None:
        return reason

    required_margin = estimate_required_margin(
        volume=request.volume,
        entry_price=entry,
        symbol=symbol,
        leverage=account.leverage,
    )
    if (reason := check_margin(
        required_margin=required_margin,
        free_margin=account.free_margin,
        safety_factor=settings.margin_safety_factor,
    )) is not None:
        return reason

    return None


def _check_duplicate_position(
    open_positions: list[Position],
    request: OrderRequest,
) -> str | None:
    for position in open_positions:
        if position.symbol == request.symbol and position.direction == request.direction:
            return (
                f"Duplicate position: {request.direction.value} {request.symbol} "
                f"already open (ticket {position.ticket})"
            )
    return None
