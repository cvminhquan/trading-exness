"""Quote / symbol validation primitives for future live execution. No order_send."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import SymbolInfo


class ValidationCode(StrEnum):
    OK = "OK"
    SYMBOL_UNAVAILABLE = "SYMBOL_UNAVAILABLE"
    INVALID_BID = "INVALID_BID"
    INVALID_ASK = "INVALID_ASK"
    INVALID_SPREAD = "INVALID_SPREAD"
    INVALID_VOLUME = "INVALID_VOLUME"
    VOLUME_METADATA_UNAVAILABLE = "VOLUME_METADATA_UNAVAILABLE"
    STOPS_LEVEL_UNAVAILABLE = "STOPS_LEVEL_UNAVAILABLE"
    FREEZE_LEVEL_UNAVAILABLE = "FREEZE_LEVEL_UNAVAILABLE"
    INVALID_SL_DISTANCE = "INVALID_SL_DISTANCE"
    INVALID_TP_DISTANCE = "INVALID_TP_DISTANCE"
    INVALID_POINT = "INVALID_POINT"
    INVALID_DIGITS = "INVALID_DIGITS"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    code: ValidationCode
    message: str = ""


def validate_quote(symbol: SymbolInfo | None) -> ValidationResult:
    if symbol is None or not symbol.symbol:
        return ValidationResult(
            False,
            ValidationCode.SYMBOL_UNAVAILABLE,
            "Symbol metadata unavailable.",
        )
    if symbol.bid <= 0:
        return ValidationResult(False, ValidationCode.INVALID_BID, "Bid must be positive.")
    if symbol.ask <= 0:
        return ValidationResult(False, ValidationCode.INVALID_ASK, "Ask must be positive.")
    if symbol.ask < symbol.bid:
        return ValidationResult(
            False,
            ValidationCode.INVALID_SPREAD,
            "Ask must be greater than or equal to bid.",
        )
    if symbol.point <= 0:
        return ValidationResult(False, ValidationCode.INVALID_POINT, "Point must be positive.")
    if symbol.digits < 0:
        return ValidationResult(False, ValidationCode.INVALID_DIGITS, "Digits must be >= 0.")
    return ValidationResult(True, ValidationCode.OK)


def validate_volume(volume: float, symbol: SymbolInfo) -> ValidationResult:
    if symbol.volume_min <= 0 or symbol.volume_step <= 0 or symbol.volume_max <= 0:
        return ValidationResult(
            False,
            ValidationCode.VOLUME_METADATA_UNAVAILABLE,
            "Volume min/max/step unavailable or invalid.",
        )
    if volume <= 0 or volume < symbol.volume_min:
        return ValidationResult(
            False,
            ValidationCode.INVALID_VOLUME,
            f"Volume {volume} below minimum {symbol.volume_min}.",
        )
    if volume > symbol.volume_max:
        return ValidationResult(
            False,
            ValidationCode.INVALID_VOLUME,
            f"Volume {volume} above maximum {symbol.volume_max}.",
        )
    steps = round(volume / symbol.volume_step)
    aligned = abs(steps * symbol.volume_step - volume) <= 1e-9 * max(1.0, volume)
    if not aligned:
        return ValidationResult(
            False,
            ValidationCode.INVALID_VOLUME,
            f"Volume {volume} not aligned to step {symbol.volume_step}.",
        )
    return ValidationResult(True, ValidationCode.OK)


def validate_stops_metadata(symbol: SymbolInfo) -> ValidationResult:
    """Fail closed when stops/freeze are unknown — do not assume zero."""
    if symbol.stops_level is None:
        return ValidationResult(
            False,
            ValidationCode.STOPS_LEVEL_UNAVAILABLE,
            "stops_level unavailable — refuse live submission.",
        )
    if symbol.freeze_level is None:
        return ValidationResult(
            False,
            ValidationCode.FREEZE_LEVEL_UNAVAILABLE,
            "freeze_level unavailable — refuse live submission.",
        )
    return ValidationResult(True, ValidationCode.OK)


def validate_sl_tp_distance(
    *,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    side: SignalDirection,
    symbol: SymbolInfo,
) -> ValidationResult:
    quote = validate_quote(symbol)
    if not quote.ok:
        return quote
    if symbol.stops_level is None:
        return ValidationResult(
            False,
            ValidationCode.STOPS_LEVEL_UNAVAILABLE,
            "Cannot validate SL/TP without stops_level.",
        )
    min_distance = symbol.stops_level * symbol.point
    sl_distance = abs(entry_price - stop_loss)
    tp_distance = abs(take_profit - entry_price)
    if side == SignalDirection.LONG:
        if stop_loss >= entry_price:
            return ValidationResult(
                False,
                ValidationCode.INVALID_SL_DISTANCE,
                "LONG stop_loss must be below entry.",
            )
        if take_profit <= entry_price:
            return ValidationResult(
                False,
                ValidationCode.INVALID_TP_DISTANCE,
                "LONG take_profit must be above entry.",
            )
    elif side == SignalDirection.SHORT:
        if stop_loss <= entry_price:
            return ValidationResult(
                False,
                ValidationCode.INVALID_SL_DISTANCE,
                "SHORT stop_loss must be above entry.",
            )
        if take_profit >= entry_price:
            return ValidationResult(
                False,
                ValidationCode.INVALID_TP_DISTANCE,
                "SHORT take_profit must be below entry.",
            )
    else:
        return ValidationResult(
            False,
            ValidationCode.INVALID_SL_DISTANCE,
            f"Unsupported side {side}.",
        )
    if sl_distance < min_distance:
        return ValidationResult(
            False,
            ValidationCode.INVALID_SL_DISTANCE,
            f"SL distance {sl_distance} below stops_level distance {min_distance}.",
        )
    if tp_distance < min_distance:
        return ValidationResult(
            False,
            ValidationCode.INVALID_TP_DISTANCE,
            f"TP distance {tp_distance} below stops_level distance {min_distance}.",
        )
    return ValidationResult(True, ValidationCode.OK)
