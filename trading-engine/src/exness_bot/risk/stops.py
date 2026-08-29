"""ATR-based stop loss and reward:risk take profit calculations."""

from exness_bot.domain.enums import SignalAction, SignalDirection


def calculate_stop_distance(atr: float, multiplier: float) -> float:
    """Return stop loss distance in price units."""
    if atr <= 0:
        msg = f"ATR must be positive, got {atr}"
        raise ValueError(msg)
    if multiplier <= 0:
        msg = f"ATR multiplier must be positive, got {multiplier}"
        raise ValueError(msg)
    return atr * multiplier


def calculate_stop_loss(
    entry_price: float,
    direction: SignalDirection,
    atr: float,
    multiplier: float,
) -> float:
    """Calculate stop loss price from ATR distance."""
    distance = calculate_stop_distance(atr, multiplier)
    if direction == SignalDirection.LONG:
        return entry_price - distance
    if direction == SignalDirection.SHORT:
        return entry_price + distance
    msg = f"Cannot calculate stop loss for direction {direction}"
    raise ValueError(msg)


def calculate_take_profit(
    entry_price: float,
    stop_loss: float,
    direction: SignalDirection,
    reward_risk_ratio: float,
) -> float:
    """Calculate take profit using fixed reward:risk ratio."""
    if reward_risk_ratio <= 0:
        msg = f"Reward:risk ratio must be positive, got {reward_risk_ratio}"
        raise ValueError(msg)

    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        msg = "Stop loss distance must be positive"
        raise ValueError(msg)

    tp_distance = sl_distance * reward_risk_ratio
    if direction == SignalDirection.LONG:
        return entry_price + tp_distance
    if direction == SignalDirection.SHORT:
        return entry_price - tp_distance
    msg = f"Cannot calculate take profit for direction {direction}"
    raise ValueError(msg)


def action_to_direction(action: SignalAction) -> SignalDirection:
    """Map signal action to trade direction."""
    if action == SignalAction.BUY:
        return SignalDirection.LONG
    if action == SignalAction.SELL:
        return SignalDirection.SHORT
    msg = f"Action {action} has no trade direction"
    raise ValueError(msg)
