"""Backtest-mode data provider — live endpoints empty, backtests via separate loader."""

from __future__ import annotations

from datetime import UTC, datetime

from exness_bot.config.settings import Settings
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
    TradeHistoryQuery,
    TradeHistoryResult,
)
from exness_bot.domain.models import Tick


class BacktestTradingDataProvider:
    """Backtest research mode — no live broker data."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def data_source(self) -> DataSourceMode:
        return DataSourceMode.BACKTEST

    def requires_live_broker(self) -> bool:
        return False

    def get_snapshot(self) -> ProviderSnapshot:
        return ProviderSnapshot(
            connection_status=ProviderConnectionStatus.DISCONNECTED,
            data_source=DataSourceMode.BACKTEST,
            account=None,
            positions=(),
            updated_at=datetime.now(tz=UTC),
            message="Chế độ backtest — không có dữ liệu live.",
        )

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        return None

    def get_trade_history(self, query: TradeHistoryQuery) -> TradeHistoryResult:
        return TradeHistoryResult(
            trades=(),
            total=0,
            updated_at=datetime.now(tz=UTC),
        )
