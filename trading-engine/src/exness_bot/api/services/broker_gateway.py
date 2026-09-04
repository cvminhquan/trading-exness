"""Broker read gateway with MT5-independent fallback — read-only only."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol

import structlog

from exness_bot.broker.mt5.mapper import map_account_info, map_position
from exness_bot.config.settings import Settings
from exness_bot.domain.models import AccountInfo, Position

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BrokerReadSnapshot:
    """Read-only broker state for API responses."""

    connected: bool
    account: AccountInfo | None
    positions: tuple[Position, ...]
    unavailable_reason: str | None = None


class BrokerReadGateway(Protocol):
    """Read-only broker access — no order mutations."""

    def get_snapshot(self) -> BrokerReadSnapshot:
        """Return current broker snapshot without side effects."""
        ...


class DisconnectedBrokerGateway:
    """Fallback when MT5 is unavailable (Linux dev, no terminal)."""

    def __init__(self, *, reason: str | None = None) -> None:
        self._reason = reason or "MetaTrader 5 không khả dụng trên môi trường hiện tại."

    def get_snapshot(self) -> BrokerReadSnapshot:
        return BrokerReadSnapshot(
            connected=False,
            account=None,
            positions=(),
            unavailable_reason=self._reason,
        )


class MT5BrokerReadGateway:
    """
    MT5-backed read gateway using the read-only connection manager only.

    Must never construct the legacy trading adapter or trading client.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: object | None = None
        self._init_error: str | None = None
        self._try_initialize()

    def _try_initialize(self) -> None:
        if sys.platform != "win32":
            self._init_error = "MT5 chỉ hỗ trợ trên Windows."
            return
        try:
            from exness_bot.broker.mt5.connection_manager import MT5ConnectionManager

            connection = MT5ConnectionManager(self._settings)
            if connection.connect():
                self._connection = connection
                return
            self._init_error = "Không thể kết nối MT5."
        except Exception as exc:
            logger.warning("mt5_read_gateway_init_failed", error=str(exc))
            self._init_error = "Không thể khởi tạo MT5 read-only."

    def get_snapshot(self) -> BrokerReadSnapshot:
        if self._connection is None:
            return BrokerReadSnapshot(
                connected=False,
                account=None,
                positions=(),
                unavailable_reason=self._init_error,
            )
        try:
            from exness_bot.broker.mt5.connection_manager import MT5ConnectionManager

            assert isinstance(self._connection, MT5ConnectionManager)
            client = self._connection.client
            raw_account = client.account_info()
            if raw_account is None:
                return BrokerReadSnapshot(
                    connected=False,
                    account=None,
                    positions=(),
                    unavailable_reason="Không đọc được account_info.",
                )
            account = map_account_info(raw_account)
            raw_positions = client.positions_get(symbol=self._settings.symbol)
            positions: list[Position] = []
            if raw_positions:
                positions = [map_position(item) for item in raw_positions]
            return BrokerReadSnapshot(
                connected=True,
                account=account,
                positions=tuple(positions),
            )
        except Exception as exc:
            logger.warning("mt5_read_snapshot_failed", error=str(exc))
            return BrokerReadSnapshot(
                connected=False,
                account=None,
                positions=(),
                unavailable_reason="Mất kết nối MT5.",
            )


def create_broker_gateway(settings: Settings, *, prefer_mt5: bool = False) -> BrokerReadGateway:
    """Create read gateway; defaults to disconnected unless prefer_mt5 on Windows."""
    if prefer_mt5:
        return MT5BrokerReadGateway(settings)
    return DisconnectedBrokerGateway()
