"""Tests for MT5Adapter error handling and data retrieval."""

from types import SimpleNamespace

import pytest

from exness_bot.broker.mt5.adapter import MT5Adapter
from exness_bot.broker.mt5.client import MT5Client
from exness_bot.broker.mt5.exceptions import (
    MT5AuthenticationError,
    MT5ConnectionError,
    MT5DataError,
    MT5MarketClosedError,
    MT5NotConnectedError,
    MT5SymbolError,
)
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from tests.conftest import MockMT5Module


@pytest.fixture
def connected_adapter(
    default_settings: Settings,
    mock_mt5_module: MockMT5Module,
) -> MT5Adapter:
    client = MT5Client(default_settings, mt5_module=mock_mt5_module)
    adapter = MT5Adapter(default_settings, client=client)
    assert adapter.connect() is True
    return adapter


class TestMT5AdapterConnect:
    def test_connect_success(self, connected_adapter: MT5Adapter) -> None:
        assert connected_adapter.is_connected() is True
        health = connected_adapter.health_check()
        assert health.connected is True
        assert health.account_login == 12345678

    def test_connect_initialize_failure_returns_false(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.initialize_result = False
        mock_mt5_module.last_error_value = (1, "Initialize failed")
        adapter = MT5Adapter(
            default_settings,
            client=MT5Client(default_settings, mt5_module=mock_mt5_module),
        )
        assert adapter.connect() is False
        assert adapter.is_connected() is False

    def test_connect_succeeds_when_auth_happens_in_initialize(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.login_result = False
        adapter = MT5Adapter(
            default_settings,
            client=MT5Client(default_settings, mt5_module=mock_mt5_module),
        )
        assert adapter.connect() is True
        assert mock_mt5_module.initialize_kwargs["login"] == 12345678

    def test_connect_missing_credentials_returns_false(
        self,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        settings = Settings(
            TRADING_MODE="demo",
            MT5_LOGIN=None,
            MT5_PASSWORD="",
        )
        adapter = MT5Adapter(
            settings,
            client=MT5Client(settings, mt5_module=mock_mt5_module),
        )
        assert adapter.connect() is False

    def test_client_login_raises_without_credentials(self, mock_mt5_module: MockMT5Module) -> None:
        settings = Settings(MT5_LOGIN=None, MT5_PASSWORD="")
        client = MT5Client(settings, mt5_module=mock_mt5_module)
        client.initialize()
        with pytest.raises(MT5AuthenticationError):
            client.login()


class TestMT5AdapterDisconnect:
    def test_disconnect(
        self,
        connected_adapter: MT5Adapter,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        connected_adapter.disconnect()
        assert connected_adapter.is_connected() is False
        assert mock_mt5_module.shutdown_called is True


class TestMT5AdapterAccount:
    def test_get_account_info(self, connected_adapter: MT5Adapter) -> None:
        account = connected_adapter.get_account_info()
        assert account.login == 12345678
        assert account.equity == 10050.0

    def test_get_account_info_not_connected(self, default_settings: Settings) -> None:
        adapter = MT5Adapter(default_settings)
        with pytest.raises(MT5NotConnectedError):
            adapter.get_account_info()


class TestMT5AdapterSymbol:
    def test_get_symbol_info(self, connected_adapter: MT5Adapter) -> None:
        info = connected_adapter.get_symbol_info("XAUUSD")
        assert info.symbol == "XAUUSD"

    def test_get_symbol_info_invalid(
        self,
        connected_adapter: MT5Adapter,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.symbol_info_value = None
        with pytest.raises(MT5SymbolError):
            connected_adapter.get_symbol_info("INVALID")


class TestMT5AdapterTick:
    def test_get_current_tick(self, connected_adapter: MT5Adapter) -> None:
        tick = connected_adapter.get_current_tick("XAUUSD")
        assert tick.symbol == "XAUUSD"
        assert tick.bid > 0

    def test_get_current_tick_market_closed(
        self,
        connected_adapter: MT5Adapter,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.symbol_info_tick_value = None
        with pytest.raises(MT5MarketClosedError):
            connected_adapter.get_current_tick("XAUUSD")


class TestMT5AdapterPositionsAndOrders:
    def test_get_open_positions(self, connected_adapter: MT5Adapter) -> None:
        positions = connected_adapter.get_open_positions("XAUUSD")
        assert len(positions) == 1
        assert positions[0].symbol == "XAUUSD"

    def test_get_pending_orders(self, connected_adapter: MT5Adapter) -> None:
        orders = connected_adapter.get_pending_orders("XAUUSD")
        assert len(orders) == 1
        assert orders[0].ticket == 2001

    def test_empty_positions_when_none(
        self,
        connected_adapter: MT5Adapter,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.positions_get_value = None
        assert connected_adapter.get_open_positions() == []


class TestMT5AdapterHistoricalCandles:
    def test_get_historical_candles_m15(self, connected_adapter: MT5Adapter) -> None:
        candles = connected_adapter.get_historical_candles("XAUUSD", Timeframe.M15, 2)
        assert len(candles) == 2
        assert candles[0].timeframe == Timeframe.M15
        assert candles[-1].close == 2354.0

    def test_invalid_candle_count_raises(self, connected_adapter: MT5Adapter) -> None:
        with pytest.raises(ValueError, match="Candle count"):
            connected_adapter.get_historical_candles("XAUUSD", Timeframe.M15, 0)

    def test_no_rates_raises_data_error(
        self,
        connected_adapter: MT5Adapter,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.copy_rates_value = None
        mock_mt5_module.symbol_info_tick_value = SimpleNamespace(
            bid=2350.1, ask=2350.3, last=2350.2, volume=1.0, time=1_700_000_000
        )
        with pytest.raises(MT5DataError):
            connected_adapter.get_historical_candles("XAUUSD", Timeframe.M15, 10)

    def test_market_closed_on_empty_rates(
        self,
        connected_adapter: MT5Adapter,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.copy_rates_value = None
        mock_mt5_module.symbol_info_tick_value = None
        mock_mt5_module.symbol_info_value = SimpleNamespace(
            name="XAUUSD",
            bid=0.0,
            ask=0.0,
            point=0.01,
            digits=2,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            spread=0,
            trade_mode=0,
            visible=True,
        )
        with pytest.raises(MT5MarketClosedError):
            connected_adapter.get_historical_candles("XAUUSD", Timeframe.M15, 10)


class TestMT5ClientErrors:
    def test_initialize_failure_raises(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.initialize_result = False
        mock_mt5_module.last_error_value = (100, "Terminal not found")
        client = MT5Client(default_settings, mt5_module=mock_mt5_module)
        with pytest.raises(MT5ConnectionError, match="initialize failed"):
            client.initialize()
