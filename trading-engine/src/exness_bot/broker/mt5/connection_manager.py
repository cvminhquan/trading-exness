"""Lazy MT5 connection lifecycle for read-only data access."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from enum import StrEnum

import structlog

from exness_bot.broker.mt5.exceptions import (
    MT5AuthenticationError,
    MT5ConnectionError,
    MT5UnavailableError,
)
from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient
from exness_bot.config.settings import Settings
from exness_bot.util.masking import mask_login

logger = structlog.get_logger(__name__)


class ConnectionState(StrEnum):
    """Stable MT5 connection states exposed to API layer."""

    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class MT5ConnectionStatus:
    """Result of a connection attempt or health check."""

    state: ConnectionState
    message: str | None = None
    server: str | None = None
    login: int | None = None


class MT5ConnectionManager:
    """Thread-safe lazy MT5 read-only connection manager."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: MT5ReadOnlyClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or MT5ReadOnlyClient(settings)
        self._lock = threading.RLock()
        self._status = MT5ConnectionStatus(
            state=ConnectionState.DISCONNECTED,
            message="Chưa kết nối MT5.",
        )

    @property
    def status(self) -> MT5ConnectionStatus:
        with self._lock:
            return self._status

    @property
    def client(self) -> MT5ReadOnlyClient:
        return self._client

    def connect(self) -> MT5ConnectionStatus:
        """Lazy connect — safe to call from concurrent API requests."""
        with self._lock:
            if self._status.state == ConnectionState.CONNECTED:
                # Xác nhận phiên còn sống; nếu chết thì reconnect bên dưới.
                terminal = self._client.terminal_info()
                account = self._client.account_info()
                if terminal is not None and account is not None:
                    return self._status
                self._safe_shutdown()
                self._status = MT5ConnectionStatus(
                    state=ConnectionState.DISCONNECTED,
                    message="Mất kết nối MT5 — đang kết nối lại.",
                )

            if sys.platform != "win32":
                self._status = MT5ConnectionStatus(
                    state=ConnectionState.UNAVAILABLE,
                    message="MT5 chỉ khả dụng trên Windows.",
                )
                return self._status

            if not self._settings.mt5_enabled:
                self._status = MT5ConnectionStatus(
                    state=ConnectionState.UNAVAILABLE,
                    message="MT5 chưa được bật (MT5_ENABLED=false).",
                )
                return self._status

            try:
                # Luôn shutdown trước khi initialize lại để tránh IPC -6 / stale session.
                self._safe_shutdown()
                self._client.initialize()
                if self._client.has_login_credentials():
                    self._client.login()
                else:
                    # Không có password trong .env: gắn phiên terminal MT5 đang mở.
                    attached = self._client.account_info()
                    if attached is None:
                        raise MT5AuthenticationError(
                            "MT5 đã initialize nhưng chưa có phiên đăng nhập. "
                            "Mở MetaTrader 5 và đăng nhập, hoặc điền MT5_PASSWORD trong .env."
                        )
                account = self._client.account_info()
                if account is None:
                    raise MT5ConnectionError("Không đọc được account_info sau khi kết nối MT5.")
                server = str(getattr(account, "server", self._settings.mt5_server))
                login = int(getattr(account, "login", 0)) or self._settings.mt5_login
                self._status = MT5ConnectionStatus(
                    state=ConnectionState.CONNECTED,
                    server=server,
                    login=login,
                )
                logger.info(
                    "mt5_connection_manager_connected",
                    server=server,
                    login_masked=mask_login(int(login)) if login else None,
                )
                return self._status
            except MT5UnavailableError as exc:
                self._status = MT5ConnectionStatus(
                    state=ConnectionState.UNAVAILABLE,
                    message=str(exc),
                )
            except (MT5ConnectionError, MT5AuthenticationError) as exc:
                self._safe_shutdown()
                self._status = MT5ConnectionStatus(
                    state=ConnectionState.ERROR,
                    message=str(exc),
                )
            except Exception as exc:
                self._safe_shutdown()
                logger.warning("mt5_connection_unexpected_error", error=str(exc))
                self._status = MT5ConnectionStatus(
                    state=ConnectionState.ERROR,
                    message="Không thể kết nối MT5.",
                )
            return self._status

    def health_check(self) -> MT5ConnectionStatus:
        """Verify terminal is still reachable without reconnecting every time."""
        with self._lock:
            if self._status.state != ConnectionState.CONNECTED:
                return self._status
            terminal = self._client.terminal_info()
            account = self._client.account_info()
            if terminal is None or account is None:
                self._safe_shutdown()
                self._status = MT5ConnectionStatus(
                    state=ConnectionState.DISCONNECTED,
                    message="Mất kết nối MT5.",
                )
            return self._status

    def disconnect(self) -> None:
        with self._lock:
            self._safe_shutdown()
            self._status = MT5ConnectionStatus(
                state=ConnectionState.DISCONNECTED,
                message="Đã ngắt kết nối MT5.",
            )

    def reconnect(self) -> MT5ConnectionStatus:
        """Force a fresh login, used when switching demo / live accounts."""
        self.disconnect()
        return self.connect()

    def _safe_shutdown(self) -> None:
        try:
            self._client.shutdown()
        except Exception as exc:
            logger.warning("mt5_shutdown_error", error=str(exc))
