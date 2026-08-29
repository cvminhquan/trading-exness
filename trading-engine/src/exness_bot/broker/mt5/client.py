"""Low-level MetaTrader5 API wrapper.

MT5ReadOnlyClient — read-only operations (Phase 10.6).
MT5TradingClient / MT5Client — includes order_send for trading engine.
"""

from exness_bot.broker.mt5.read_only_client import (
    MT5ReadOnlyClient,
    MT5ReadOnlyModule,
    load_mt5_readonly_module,
)
from exness_bot.broker.mt5.trading_client import MT5Client, MT5TradingClient, MT5TradingModule

__all__ = [
    "MT5Client",
    "MT5ReadOnlyClient",
    "MT5ReadOnlyModule",
    "MT5TradingClient",
    "MT5TradingModule",
    "load_mt5_readonly_module",
]
