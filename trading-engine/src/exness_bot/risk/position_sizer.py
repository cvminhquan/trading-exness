"""Position size calculation from equity, risk budget, and symbol specifications."""

import math

from exness_bot.domain.models import SymbolInfo


def money_per_point_per_lot(symbol: SymbolInfo) -> float:
    """Return monetary value of one point move for one lot."""
    if symbol.point <= 0:
        msg = f"Invalid symbol point size: {symbol.point}"
        raise ValueError(msg)
    if symbol.trade_contract_size <= 0:
        msg = f"Invalid contract size: {symbol.trade_contract_size}"
        raise ValueError(msg)
    return symbol.trade_contract_size * symbol.point


def calculate_raw_volume(
    *,
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    symbol: SymbolInfo,
) -> float:
    """
    Calculate raw lot size before normalization.

    volume = risk_amount / (sl_points * value_per_point_per_lot)
    """
    if equity <= 0:
        msg = f"Equity must be positive, got {equity}"
        raise ValueError(msg)
    if risk_pct <= 0:
        msg = f"Risk percentage must be positive, got {risk_pct}"
        raise ValueError(msg)

    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        msg = "Stop loss distance must be positive"
        raise ValueError(msg)

    sl_points = sl_distance / symbol.point
    if sl_points <= 0:
        msg = "Stop loss must be at least one point away from entry"
        raise ValueError(msg)

    risk_amount = equity * (risk_pct / 100.0)
    point_value = money_per_point_per_lot(symbol)
    return risk_amount / (sl_points * point_value)


def normalize_lot_size(
    volume: float,
    *,
    volume_min: float,
    volume_max: float,
    volume_step: float,
) -> float:
    """Round volume down to broker step and clamp to min/max."""
    if volume_step <= 0:
        msg = f"Volume step must be positive, got {volume_step}"
        raise ValueError(msg)
    if volume_max <= 0 or volume_min <= 0:
        msg = "Volume min/max must be positive"
        raise ValueError(msg)

    steps = math.floor((volume / volume_step) + 1e-12)
    normalized = steps * volume_step
    decimals = _step_decimal_places(volume_step)
    normalized = round(normalized, decimals)

    if normalized < volume_min:
        return 0.0
    return min(normalized, volume_max)


def calculate_position_size(
    *,
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    symbol: SymbolInfo,
) -> float:
    """Calculate broker-compliant lot size for the requested risk."""
    raw = calculate_raw_volume(
        equity=equity,
        risk_pct=risk_pct,
        entry_price=entry_price,
        stop_loss=stop_loss,
        symbol=symbol,
    )
    return normalize_lot_size(
        raw,
        volume_min=symbol.volume_min,
        volume_max=symbol.volume_max,
        volume_step=symbol.volume_step,
    )


def _step_decimal_places(volume_step: float) -> int:
    step_str = f"{volume_step:.10f}".rstrip("0")
    if "." not in step_str:
        return 0
    return len(step_str.split(".")[1])
