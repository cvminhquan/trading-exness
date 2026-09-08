"""Mock trading data provider for development."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from exness_bot.config.settings import Settings
from exness_bot.data.mock_data import mock_account, mock_closed_trades, mock_positions
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
    TradeHistoryQuery,
    TradeHistoryResult,
)
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, ClosedTrade, SymbolInfo, Tick
from exness_bot.market_data.candles import timeframe_duration

_MOCK_LAST: dict[str, float] = {
    "XAUUSD": 4456.40,
    "XAGUSD": 38.25,
    "EURUSD": 1.16820,
    "GBPUSD": 1.34210,
    "USDJPY": 147.852,
    "BTCUSD": 108450.0,
    "ETHUSD": 4280.0,
}


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
        target = (symbol or self._settings.symbol).strip().upper()
        last = _MOCK_LAST.get(target)
        if last is None:
            positions = mock_positions()
            last = positions[0].current_price if positions else 2350.0
        spread = max(last * 0.00008, 0.0001 if last < 10 else 0.02)
        return Tick(
            symbol=target,
            bid=round(last - spread / 2, 8),
            ask=round(last + spread / 2, 8),
            last=last,
            volume=100.0,
            timestamp=datetime.now(tz=UTC),
        )

    def get_symbol_info(self, symbol: str | None = None) -> SymbolInfo | None:
        tick = self.get_tick(symbol)
        if tick is None:
            return None
        spread_points = round(abs(tick.ask - tick.bid) / 0.01)
        return SymbolInfo(
            symbol=tick.symbol,
            bid=tick.bid,
            ask=tick.ask,
            point=0.01,
            digits=2,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            spread=max(spread_points, 1),
            trade_mode=4,
            visible=True,
            stops_level=0,
            freeze_level=0,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
        )

    def resolve_broker_symbol(self, symbol: str | None = None) -> str:
        target = (symbol or self._settings.symbol).strip().upper()
        if target == "XAUUSD":
            return "XAUUSDm"
        return target

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

    def get_balance_cashflow(self, start: datetime, end: datetime) -> float:
        """Mock: no deposits/withdrawals in the window."""
        _ = (start, end)
        return 0.0

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

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[Candle] | None:
        target = (symbol or self._settings.symbol).strip().upper()
        last = _MOCK_LAST.get(target, 2350.0)
        now = datetime.now(tz=UTC)
        step_minutes = max(1, int(timeframe_duration(timeframe).total_seconds() // 60))
        forming_open = now.replace(
            minute=(now.minute // step_minutes) * step_minutes,
            second=0,
            microsecond=0,
        )
        candles: list[Candle] = []
        for index in range(count):
            offset = count - 1 - index
            open_ts = forming_open - timedelta(minutes=step_minutes * offset)
            drift = (index - count / 2) * 0.05
            close = round(last + drift, 2)
            open_px = round(close - 0.12, 2)
            candles.append(
                Candle(
                    symbol=target,
                    timeframe=timeframe,
                    timestamp=open_ts,
                    open=open_px,
                    high=round(max(open_px, close) + 0.4, 2),
                    low=round(min(open_px, close) - 0.4, 2),
                    close=close,
                    volume=100.0,
                    spread=20,
                    tick_volume=100.0,
                    real_volume=0.0,
                )
            )
        return candles
