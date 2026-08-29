"""MT5 broker-specific exceptions."""

from enum import StrEnum


class BrokerErrorCode(StrEnum):
    """Machine-readable broker error codes."""

    MT5_UNAVAILABLE = "mt5_unavailable"
    CONNECTION_FAILED = "connection_failed"
    AUTHENTICATION_FAILED = "authentication_failed"
    NOT_CONNECTED = "not_connected"
    INVALID_SYMBOL = "invalid_symbol"
    INSUFFICIENT_DATA = "insufficient_data"
    MARKET_CLOSED = "market_closed"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class BrokerError(Exception):
    """Base exception for broker operations."""

    def __init__(
        self,
        message: str,
        *,
        code: BrokerErrorCode = BrokerErrorCode.UNKNOWN,
        mt5_error: tuple[int, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.mt5_error = mt5_error


class MT5UnavailableError(BrokerError):
    """MetaTrader5 package or terminal is not available."""

    def __init__(self, message: str = "MetaTrader5 is not available on this system") -> None:
        super().__init__(message, code=BrokerErrorCode.MT5_UNAVAILABLE)


class MT5ConnectionError(BrokerError):
    """Failed to connect to the MT5 terminal."""

    def __init__(
        self,
        message: str,
        *,
        mt5_error: tuple[int, str] | None = None,
    ) -> None:
        super().__init__(message, code=BrokerErrorCode.CONNECTION_FAILED, mt5_error=mt5_error)


class MT5AuthenticationError(BrokerError):
    """Failed to authenticate with the broker server."""

    def __init__(
        self,
        message: str,
        *,
        mt5_error: tuple[int, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=BrokerErrorCode.AUTHENTICATION_FAILED,
            mt5_error=mt5_error,
        )


class MT5NotConnectedError(BrokerError):
    """Operation requires an active broker connection."""

    def __init__(self, message: str = "Broker is not connected") -> None:
        super().__init__(message, code=BrokerErrorCode.NOT_CONNECTED)


class MT5SymbolError(BrokerError):
    """Symbol is invalid or not available."""

    def __init__(
        self,
        message: str,
        *,
        symbol: str | None = None,
        mt5_error: tuple[int, str] | None = None,
    ) -> None:
        super().__init__(message, code=BrokerErrorCode.INVALID_SYMBOL, mt5_error=mt5_error)
        self.symbol = symbol


class MT5DataError(BrokerError):
    """Historical or market data could not be retrieved."""

    def __init__(
        self,
        message: str,
        *,
        mt5_error: tuple[int, str] | None = None,
    ) -> None:
        super().__init__(message, code=BrokerErrorCode.INSUFFICIENT_DATA, mt5_error=mt5_error)


class MT5MarketClosedError(BrokerError):
    """Market is closed for the requested symbol."""

    def __init__(
        self,
        message: str,
        *,
        symbol: str | None = None,
    ) -> None:
        super().__init__(message, code=BrokerErrorCode.MARKET_CLOSED)
        self.symbol = symbol


class MT5TimeoutError(BrokerError):
    """Broker operation timed out."""

    def __init__(self, message: str = "MT5 operation timed out") -> None:
        super().__init__(message, code=BrokerErrorCode.TIMEOUT)
