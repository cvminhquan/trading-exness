"""Domain enumerations."""

from enum import StrEnum


class Timeframe(StrEnum):
    """Supported chart timeframes."""

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


class SignalDirection(StrEnum):
    """Direction of a trading signal."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class SignalAction(StrEnum):
    """Discrete strategy output action."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderType(StrEnum):
    """Order type for broker submission."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class TradeAction(StrEnum):
    """Action taken by risk manager."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
