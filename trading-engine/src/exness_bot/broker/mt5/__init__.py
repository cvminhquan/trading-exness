"""MetaTrader 5 broker integration."""

from exness_bot.broker.mt5.adapter import MT5Adapter
from exness_bot.broker.mt5.client import MT5Client
from exness_bot.broker.mt5.exceptions import (
    BrokerError,
    MT5AuthenticationError,
    MT5ConnectionError,
    MT5DataError,
    MT5MarketClosedError,
    MT5NotConnectedError,
    MT5SymbolError,
    MT5UnavailableError,
)

__all__ = [
    "BrokerError",
    "MT5Adapter",
    "MT5AuthenticationError",
    "MT5Client",
    "MT5ConnectionError",
    "MT5DataError",
    "MT5MarketClosedError",
    "MT5NotConnectedError",
    "MT5SymbolError",
    "MT5UnavailableError",
]
