"""Broker interface extended with order execution."""

from typing import Protocol

from exness_bot.broker.base import BrokerPort
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import OrderRequest, OrderResult, Position


class ExecutableBroker(BrokerPort, Protocol):
    """Broker port with order execution capabilities."""

    def open_market_order(self, request: OrderRequest) -> OrderResult:
        """Submit a market order."""
        ...

    def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: float | None = None,
        *,
        direction: SignalDirection | None = None,
    ) -> OrderResult:
        """Close an open position."""
        ...

    def modify_stop_loss(self, ticket: int, symbol: str, stop_loss: float) -> OrderResult:
        """Modify stop loss on a position."""
        ...

    def modify_take_profit(self, ticket: int, symbol: str, take_profit: float) -> OrderResult:
        """Modify take profit on a position."""
        ...

    def get_open_positions(self, symbol: str | None = None) -> list[Position]:
        """Return open positions for reconciliation."""
        ...
