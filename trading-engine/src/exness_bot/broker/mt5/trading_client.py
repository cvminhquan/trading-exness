"""MT5 trading client — extends read-only client with order_send."""

from __future__ import annotations

from typing import Any

from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient, MT5ReadOnlyModule
from exness_bot.config.settings import Settings


class MT5TradingModule(MT5ReadOnlyModule):
    """MetaTrader5 module including trading mutations (used only by trading path)."""

    def order_send(self, request: dict[str, Any]) -> Any: ...


class MT5TradingClient(MT5ReadOnlyClient):
    """Full MT5 client for order execution — NOT used by read-only API."""

    def __init__(
        self,
        settings: Settings,
        *,
        mt5_module: MT5TradingModule | None = None,
    ) -> None:
        super().__init__(settings, mt5_module=mt5_module)

    @property
    def mt5(self) -> MT5TradingModule:
        return super().mt5  # type: ignore[return-value]

    def order_send(self, request: dict[str, Any]) -> Any:
        return self.mt5.order_send(request)


# Backward-compatible alias used by existing trading engine code.
MT5Client = MT5TradingClient
