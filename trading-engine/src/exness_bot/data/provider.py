"""Read-only trading data provider protocol."""

from __future__ import annotations

from typing import Protocol

from exness_bot.data.models import (
    DataSourceMode,
    ProviderSnapshot,
    TradeHistoryQuery,
    TradeHistoryResult,
)
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, Tick


class TradingDataProvider(Protocol):
    """Domain-level read-only data access for Dashboard API."""

    @property
    def data_source(self) -> DataSourceMode:
        """Active data source mode."""
        ...

    def get_snapshot(self) -> ProviderSnapshot:
        """Return current account + positions snapshot."""
        ...

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        """Return latest tick for symbol, if available."""
        ...

    def get_trade_history(self, query: TradeHistoryQuery) -> TradeHistoryResult:
        """Return paginated closed trade history."""
        ...

    def requires_live_broker(self) -> bool:
        """True when provider expects MT5 connectivity."""
        ...

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[Candle] | None:
        """Return OHLCV bars oldest-first, or None when the broker is unavailable."""
        ...
