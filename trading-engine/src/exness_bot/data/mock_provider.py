"""Mock trading data provider for development."""

from __future__ import annotations

from datetime import UTC, datetime

from exness_bot.config.settings import Settings
from exness_bot.data.mock_data import mock_account, mock_closed_trades, mock_positions
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
    TradeHistoryQuery,
    TradeHistoryResult,
)
from exness_bot.domain.models import ClosedTrade, Tick


class MockTradingDataProvider:
    """In-memory mock data — no MT5 required."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def data_source(self) -> DataSourceMode:
        return DataSourceMode.MOCK

    def requires_live_broker(self) -> bool:
        return False

    def get_snapshot(self) -> ProviderSnapshot:
        account = mock_account()
        positions = tuple(mock_positions())
        return ProviderSnapshot(
            connection_status=ProviderConnectionStatus.CONNECTED,
            data_source=DataSourceMode.MOCK,
            account=account,
            positions=positions,
            updated_at=datetime.now(tz=UTC),
            broker_server=account.server,
            message="Dữ liệu mock cho development.",
        )

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        target = symbol or self._settings.symbol
        positions = mock_positions()
        price = positions[0].current_price if positions else 2350.0
        return Tick(
            symbol=target,
            bid=round(price - 0.1, 2),
            ask=round(price + 0.1, 2),
            last=price,
            volume=100.0,
            timestamp=datetime.now(tz=UTC),
        )

    def get_trade_history(self, query: TradeHistoryQuery) -> TradeHistoryResult:
        trades = self._filter_trades(mock_closed_trades(), query)
        total = len(trades)
        start = (query.page - 1) * query.page_size
        end = start + query.page_size
        page_items = trades[start:end]
        return TradeHistoryResult(
            trades=tuple(page_items),
            total=total,
            updated_at=datetime.now(tz=UTC),
        )

    @staticmethod
    def _filter_trades(trades: list[ClosedTrade], query: TradeHistoryQuery) -> list[ClosedTrade]:
        filtered = trades
        if query.symbol:
            filtered = [t for t in filtered if t.symbol == query.symbol]
        if query.direction:
            filtered = [t for t in filtered if t.direction.value == query.direction]
        if query.strategy:
            filtered = [t for t in filtered if t.strategy == query.strategy]
        if query.result == "WIN":
            filtered = [t for t in filtered if t.net_pnl > 0]
        elif query.result == "LOSS":
            filtered = [t for t in filtered if t.net_pnl < 0]
        if query.start:
            filtered = [t for t in filtered if t.closed_at >= query.start]
        if query.end:
            filtered = [t for t in filtered if t.closed_at <= query.end]
        return filtered
