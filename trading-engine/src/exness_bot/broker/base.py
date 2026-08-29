"""Broker abstraction — application code depends on this interface, not MetaTrader5."""

from typing import Protocol

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import (
    AccountInfo,
    Candle,
    HealthStatus,
    PendingOrder,
    Position,
    SymbolInfo,
    Tick,
)


class BrokerPort(Protocol):
    """Interface for broker connectivity and market data retrieval."""

    def connect(self) -> bool:
        """Establish connection to the broker."""
        ...

    def disconnect(self) -> None:
        """Close broker connection."""
        ...

    def is_connected(self) -> bool:
        """Return True if connected to broker."""
        ...

    def health_check(self) -> HealthStatus:
        """Verify terminal, account, and trading readiness."""
        ...

    def get_account_info(self) -> AccountInfo:
        """Retrieve current account information."""
        ...

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """Retrieve symbol specification and current quote."""
        ...

    def get_current_tick(self, symbol: str) -> Tick:
        """Retrieve the latest tick for a symbol."""
        ...

    def get_open_positions(self, symbol: str | None = None) -> list[Position]:
        """Return open positions, optionally filtered by symbol."""
        ...

    def get_pending_orders(self, symbol: str | None = None) -> list[PendingOrder]:
        """Return pending orders, optionally filtered by symbol."""
        ...

    def get_historical_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[Candle]:
        """Fetch historical OHLCV candles."""
        ...
