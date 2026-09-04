"""Tests for trading data providers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from exness_bot.config.settings import DataSource, Settings
from exness_bot.data.backtest_provider import BacktestTradingDataProvider
from exness_bot.data.factory import create_trading_data_provider
from exness_bot.data.mock_provider import MockTradingDataProvider
from exness_bot.data.models import ProviderConnectionStatus, TradeHistoryQuery
from exness_bot.data.mt5_provider import MT5TradingDataProvider
from exness_bot.domain.enums import Timeframe
from exness_bot.market_data.candles import is_candle_closed


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(DATA_SOURCE="mock")


class TestMockProvider:
    def test_snapshot_connected(self, mock_settings: Settings) -> None:
        provider = MockTradingDataProvider(mock_settings)
        snapshot = provider.get_snapshot()
        assert snapshot.connection_status == ProviderConnectionStatus.CONNECTED
        assert snapshot.account is not None
        assert len(snapshot.positions) == 1

    def test_trade_history_pagination(self, mock_settings: Settings) -> None:
        provider = MockTradingDataProvider(mock_settings)
        result = provider.get_trade_history(TradeHistoryQuery(page=1, page_size=2))
        assert result.total >= 2
        assert len(result.trades) == 2

    def test_trade_filter_win(self, mock_settings: Settings) -> None:
        provider = MockTradingDataProvider(mock_settings)
        result = provider.get_trade_history(TradeHistoryQuery(result="WIN"))
        assert all(trade.net_pnl > 0 for trade in result.trades)

    def test_get_candles_oldest_first_last_is_forming(self, mock_settings: Settings) -> None:
        provider = MockTradingDataProvider(mock_settings)
        candles = provider.get_candles("XAUUSD", Timeframe.M15, 8)
        assert candles is not None
        assert len(candles) == 8
        stamps = [item.timestamp for item in candles]
        assert stamps == sorted(stamps)
        now = datetime.now(tz=UTC)
        assert is_candle_closed(candles[-1].timestamp, Timeframe.M15, now=now) is False
        if len(candles) >= 2:
            assert candles[-1].timestamp - candles[-2].timestamp == timedelta(minutes=15)


class TestBacktestProvider:
    def test_no_live_data(self, mock_settings: Settings) -> None:
        settings = Settings(DATA_SOURCE="backtest")
        provider = BacktestTradingDataProvider(settings)
        snapshot = provider.get_snapshot()
        assert snapshot.connection_status == ProviderConnectionStatus.DISCONNECTED
        assert snapshot.positions == ()


class TestProviderFactory:
    def test_create_mock(self, mock_settings: Settings) -> None:
        provider = create_trading_data_provider(mock_settings)
        assert isinstance(provider, MockTradingDataProvider)

    def test_create_mt5(self) -> None:
        settings = Settings(DATA_SOURCE="mt5", MT5_ENABLED=True)
        provider = create_trading_data_provider(settings)
        assert isinstance(provider, MT5TradingDataProvider)

    def test_data_source_enum(self) -> None:
        assert DataSource.MOCK.value == "mock"
