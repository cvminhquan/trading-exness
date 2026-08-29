"""MT5 read-only trading data provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from exness_bot.broker.mt5.connection_manager import ConnectionState, MT5ConnectionManager
from exness_bot.broker.mt5.mapper import (
    map_account_info,
    map_closed_trades_from_deals,
    map_position,
    map_tick,
)
from exness_bot.broker.mt5.symbol_resolver import resolve_broker_symbol
from exness_bot.config.settings import Settings
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
    TradeHistoryQuery,
    TradeHistoryResult,
)
from exness_bot.domain.models import ClosedTrade, Position, Tick

logger = structlog.get_logger(__name__)

_CONNECTION_TO_PROVIDER: dict[ConnectionState, ProviderConnectionStatus] = {
    ConnectionState.CONNECTED: ProviderConnectionStatus.CONNECTED,
    ConnectionState.DISCONNECTED: ProviderConnectionStatus.DISCONNECTED,
    ConnectionState.UNAVAILABLE: ProviderConnectionStatus.UNAVAILABLE,
    ConnectionState.ERROR: ProviderConnectionStatus.ERROR,
}


class MT5TradingDataProvider:
    """Live read-only data from MetaTrader 5."""

    def __init__(
        self,
        settings: Settings,
        *,
        connection_manager: MT5ConnectionManager | None = None,
    ) -> None:
        self._settings = settings
        self._connection = connection_manager or MT5ConnectionManager(settings)
        self._canonical_symbol = settings.resolved_symbol
        self._broker_symbol: str | None = None
        self._last_snapshot_at: datetime | None = None

    @property
    def data_source(self) -> DataSourceMode:
        return DataSourceMode.MT5

    def requires_live_broker(self) -> bool:
        return True

    def _provider_status(self) -> ProviderConnectionStatus:
        return _CONNECTION_TO_PROVIDER[self._connection.status.state]

    def _ensure_broker_symbol(self) -> str | None:
        status = self._connection.connect()
        if status.state != ConnectionState.CONNECTED:
            return None
        if self._broker_symbol is not None:
            return self._broker_symbol
        try:
            requested = self._settings.mt5_symbol or self._canonical_symbol
            self._broker_symbol = resolve_broker_symbol(self._connection.client, requested)
            return self._broker_symbol
        except Exception as exc:
            logger.warning("mt5_symbol_resolution_failed", error=str(exc))
            return None

    def get_snapshot(self) -> ProviderSnapshot:
        status = self._connection.connect()
        now = datetime.now(tz=UTC)
        provider_status = self._provider_status()

        if status.state != ConnectionState.CONNECTED:
            return ProviderSnapshot(
                connection_status=provider_status,
                data_source=DataSourceMode.MT5,
                account=None,
                positions=(),
                updated_at=now,
                broker_server=status.server,
                message=status.message,
            )

        broker_symbol = self._ensure_broker_symbol()
        client = self._connection.client
        raw_account = client.account_info()
        if raw_account is None:
            return ProviderSnapshot(
                connection_status=ProviderConnectionStatus.ERROR,
                data_source=DataSourceMode.MT5,
                account=None,
                positions=(),
                updated_at=now,
                message="Không thể đọc thông tin tài khoản MT5.",
            )

        account = map_account_info(raw_account)
        positions: tuple[Position, ...] = ()
        if broker_symbol:
            raw_positions = client.positions_get(broker_symbol)
            if raw_positions:
                positions = tuple(
                    map_position(item, canonical_symbol=self._canonical_symbol)
                    for item in raw_positions
                )

        self._last_snapshot_at = now
        self._connection.health_check()
        return ProviderSnapshot(
            connection_status=self._provider_status(),
            data_source=DataSourceMode.MT5,
            account=account,
            positions=positions,
            updated_at=now,
            broker_server=account.server or status.server,
            message=status.message,
            stale=False,
        )

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        status = self._connection.connect()
        if status.state != ConnectionState.CONNECTED:
            return None
        broker_symbol = self._ensure_broker_symbol()
        if broker_symbol is None:
            return None
        raw_tick = self._connection.client.symbol_info_tick(broker_symbol)
        if raw_tick is None:
            return None
        tick = map_tick(broker_symbol, raw_tick)
        return Tick(
            symbol=symbol or self._canonical_symbol,
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            volume=tick.volume,
            timestamp=tick.timestamp,
        )

    def get_trade_history(self, query: TradeHistoryQuery) -> TradeHistoryResult:
        now = datetime.now(tz=UTC)
        status = self._connection.connect()
        if status.state != ConnectionState.CONNECTED:
            return TradeHistoryResult(trades=(), total=0, updated_at=now)

        date_to = query.end or now
        date_from = query.start or (date_to - timedelta(days=30))
        client = self._connection.client
        raw_deals = client.history_deals_get(date_from, date_to)
        if raw_deals is None:
            raw_deals = []

        trades = map_closed_trades_from_deals(
            list(raw_deals),
            canonical_symbol=self._canonical_symbol,
            strategy="ema_rsi_atr_v1",
        )
        filtered = self._filter_trades(trades, query)
        total = len(filtered)
        start = (query.page - 1) * query.page_size
        end = start + query.page_size
        return TradeHistoryResult(
            trades=tuple(filtered[start:end]),
            total=total,
            updated_at=now,
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
