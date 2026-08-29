"""Read-only trading data provider models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from exness_bot.domain.models import AccountInfo, ClosedTrade, Position


class DataSourceMode(StrEnum):
    """Runtime data source for live dashboard endpoints."""

    MOCK = "mock"
    BACKTEST = "backtest"
    MT5 = "mt5"


class ProviderConnectionStatus(StrEnum):
    """Connection status exposed through API."""

    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ProviderSnapshot:
    """Read-only snapshot from a data provider."""

    connection_status: ProviderConnectionStatus
    data_source: DataSourceMode
    account: AccountInfo | None
    positions: tuple[Position, ...]
    updated_at: datetime
    broker_server: str | None = None
    message: str | None = None
    stale: bool = False


@dataclass(frozen=True)
class TradeHistoryQuery:
    """Query parameters for closed trade history."""

    page: int = 1
    page_size: int = 50
    symbol: str | None = None
    direction: str | None = None
    strategy: str | None = None
    result: str | None = None
    start: datetime | None = None
    end: datetime | None = None


@dataclass(frozen=True)
class TradeHistoryResult:
    """Paginated closed trades."""

    trades: tuple[ClosedTrade, ...]
    total: int
    updated_at: datetime
