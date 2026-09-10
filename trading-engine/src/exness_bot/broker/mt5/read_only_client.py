"""Read-only MT5 client — no order_send or trading mutations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, cast

import structlog

from exness_bot.broker.mt5.exceptions import (
    MT5AuthenticationError,
    MT5ConnectionError,
    MT5SymbolError,
    MT5UnavailableError,
)
from exness_bot.config.settings import Settings
from exness_bot.util.masking import mask_login

logger = structlog.get_logger(__name__)


class MT5ReadOnlyModule(Protocol):
    """Subset of MetaTrader5 module API allowed for read-only operations."""

    def initialize(self, path: str | None = None, **kwargs: Any) -> bool: ...
    def shutdown(self) -> None: ...
    def login(self, login: int, password: str, server: str) -> bool: ...
    def last_error(self) -> tuple[int, str]: ...
    def account_info(self) -> Any: ...
    def terminal_info(self) -> Any: ...
    def symbol_info(self, symbol: str) -> Any: ...
    def symbol_info_tick(self, symbol: str) -> Any: ...
    def symbol_select(self, symbol: str, enable: bool) -> bool: ...
    def positions_get(self, symbol: str | None = None) -> Any: ...
    def orders_get(self, symbol: str | None = None) -> Any: ...
    def history_deals_get(
        self,
        date_from: datetime,
        date_to: datetime,
        group: str = "*",
    ) -> Any: ...
    def history_orders_get(
        self,
        date_from: datetime,
        date_to: datetime,
        group: str = "*",
    ) -> Any: ...
    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: int,
        start_pos: int,
        count: int,
    ) -> Any: ...
    def copy_rates_range(
        self,
        symbol: str,
        timeframe: int,
        date_from: datetime,
        date_to: datetime,
    ) -> Any: ...
    def copy_rates_from(
        self,
        symbol: str,
        timeframe: int,
        date_from: datetime,
        count: int,
    ) -> Any: ...
    def symbols_get(self, group: str = "*") -> Any: ...


def load_mt5_readonly_module() -> MT5ReadOnlyModule:
    """Import MetaTrader5 module for read-only use."""
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        msg = (
            "MetaTrader5 Python package is not installed. "
            "Install on Windows with: pip install MetaTrader5"
        )
        raise MT5UnavailableError(msg) from exc
    return cast(MT5ReadOnlyModule, mt5)


class MT5ReadOnlyClient:
    """Read-only MT5 wrapper — intentionally excludes order_send."""

    def __init__(
        self,
        settings: Settings,
        *,
        mt5_module: MT5ReadOnlyModule | None = None,
    ) -> None:
        self._settings = settings
        self._mt5 = mt5_module
        self._initialized = False
        self._logged_in = False
        self._login_override: tuple[int, str, str] | None = None

    @property
    def mt5(self) -> MT5ReadOnlyModule:
        if self._mt5 is None:
            self._mt5 = load_mt5_readonly_module()
        return self._mt5

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    def _last_error(self) -> tuple[int, str]:
        return self.mt5.last_error()

    def _resolve_credentials(self) -> tuple[int | None, str, str]:
        if self._login_override is not None:
            return self._login_override
        # Fallback: khi MT5_PASSWORD trống, dùng credential demo/live đã cấu hình.
        if self._settings.mt5_password:
            return (
                self._settings.mt5_login,
                self._settings.mt5_password,
                self._settings.mt5_server,
            )
        demo = self._settings.demo_credentials()
        if demo.configured:
            return demo.login, demo.password, demo.server
        return self._settings.mt5_login, self._settings.mt5_password, self._settings.mt5_server

    def has_login_credentials(self) -> bool:
        login, password, _server = self._resolve_credentials()
        return login is not None and bool(password)

    def initialize(self) -> None:
        """Attach to MT5. Pass login in the same initialize() call.

        Exness terminals often return IPC error -6 if initialize(path) runs
        without credentials and login() is a second step.
        """
        path = self._settings.mt5_path
        login, password, server = self._resolve_credentials()
        init_kwargs: dict[str, Any] = {"timeout": 60_000}
        if login is not None and password:
            init_kwargs["login"] = int(login)
            init_kwargs["password"] = password
            init_kwargs["server"] = server
        if not self.mt5.initialize(path, **init_kwargs):
            code, description = self._last_error()
            msg = f"MT5 initialize failed: [{code}] {description}"
            raise MT5ConnectionError(msg, mt5_error=(code, description))
        self._initialized = True
        if login is not None and password:
            self._logged_in = True
        logger.info("mt5_readonly_initialized", path=path)

    def set_credentials(self, login: int, password: str, server: str) -> None:
        """Override login used on the next connect. Does not persist secrets."""
        self._login_override = (login, password, server)
        self._logged_in = False

    def login(self) -> None:
        if self._logged_in:
            return
        login, password, server = self._resolve_credentials()
        if login is None or not password:
            msg = "MT5_LOGIN and MT5_PASSWORD must be configured"
            raise MT5AuthenticationError(msg)

        if not self.mt5.login(login, password=password, server=server):
            code, description = self._last_error()
            msg = f"MT5 login failed: [{code}] {description}"
            raise MT5AuthenticationError(msg, mt5_error=(code, description))

        self._logged_in = True
        logger.info(
            "mt5_readonly_logged_in",
            login_masked=mask_login(int(login)),
            server=server,
        )

    def shutdown(self) -> None:
        if self._initialized:
            self.mt5.shutdown()
            logger.info("mt5_readonly_shutdown")
        self._initialized = False
        self._logged_in = False

    def account_info(self) -> Any:
        return self.mt5.account_info()

    def terminal_info(self) -> Any:
        return self.mt5.terminal_info()

    def symbol_info(self, symbol: str) -> Any:
        return self.mt5.symbol_info(symbol)

    def symbol_info_tick(self, symbol: str) -> Any:
        return self.mt5.symbol_info_tick(symbol)

    def ensure_symbol_selected(self, symbol: str) -> None:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            code, description = self._last_error()
            msg = f"Symbol not found: {symbol} [{code}] {description}"
            raise MT5SymbolError(msg, symbol=symbol, mt5_error=(code, description))

        if not info.visible and not self.mt5.symbol_select(symbol, True):
            code, description = self._last_error()
            msg = f"Failed to select symbol {symbol}: [{code}] {description}"
            raise MT5ConnectionError(msg, mt5_error=(code, description))

    def positions_get(self, symbol: str | None = None) -> Any:
        if symbol:
            return self.mt5.positions_get(symbol=symbol)
        return self.mt5.positions_get()

    def orders_get(self, symbol: str | None = None) -> Any:
        if symbol:
            return self.mt5.orders_get(symbol=symbol)
        return self.mt5.orders_get()

    def history_deals_get(
        self,
        date_from: datetime,
        date_to: datetime,
        *,
        group: str = "*",
    ) -> Any:
        return self.mt5.history_deals_get(date_from, date_to, group=group)

    def history_orders_get(
        self,
        date_from: datetime,
        date_to: datetime,
        *,
        group: str = "*",
    ) -> Any:
        return self.mt5.history_orders_get(date_from, date_to, group=group)

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: int,
        start_pos: int,
        count: int,
    ) -> Any:
        return self.mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)

    def copy_rates_range(
        self,
        symbol: str,
        timeframe: int,
        date_from: datetime,
        date_to: datetime,
    ) -> Any:
        return self.mt5.copy_rates_range(symbol, timeframe, date_from, date_to)

    def copy_rates_from(
        self,
        symbol: str,
        timeframe: int,
        date_from: datetime,
        count: int,
    ) -> Any:
        return self.mt5.copy_rates_from(symbol, timeframe, date_from, count)

    def symbols_get(self, group: str = "*") -> Any:
        return self.mt5.symbols_get(group)

    def last_error(self) -> tuple[int, str]:
        return self._last_error()
