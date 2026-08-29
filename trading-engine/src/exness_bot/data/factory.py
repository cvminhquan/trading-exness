"""Centralized trading data provider factory."""

from __future__ import annotations

from exness_bot.config.settings import DataSource, Settings
from exness_bot.data.backtest_provider import BacktestTradingDataProvider
from exness_bot.data.mock_provider import MockTradingDataProvider
from exness_bot.data.models import DataSourceMode
from exness_bot.data.mt5_provider import MT5TradingDataProvider
from exness_bot.data.provider import TradingDataProvider


def create_trading_data_provider(settings: Settings) -> TradingDataProvider:
    """Select read-only data provider based on configuration."""
    source = settings.data_source
    if source == DataSource.MT5:
        return MT5TradingDataProvider(settings)
    if source == DataSource.BACKTEST:
        return BacktestTradingDataProvider(settings)
    return MockTradingDataProvider(settings)


def data_source_mode(settings: Settings) -> DataSourceMode:
    """Map settings enum to provider mode."""
    mapping = {
        DataSource.MOCK: DataSourceMode.MOCK,
        DataSource.BACKTEST: DataSourceMode.BACKTEST,
        DataSource.MT5: DataSourceMode.MT5,
    }
    return mapping[settings.data_source]
