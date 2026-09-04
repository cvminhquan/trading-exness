"""Shared test fixtures."""

from types import SimpleNamespace

import numpy as np
import pytest

from exness_bot.broker.mt5.client import MT5Client
from exness_bot.broker.mt5.mapper import MT5_TRADE_MODE_FULL
from exness_bot.config.settings import Settings


@pytest.fixture
def default_settings() -> Settings:
    """Settings with safe DEMO defaults."""
    return Settings(
        TRADING_MODE="demo",
        DRY_RUN=True,
        ALLOW_LIVE_TRADING=False,
        MT5_LOGIN=12345678,
        MT5_PASSWORD="demo-password",
        MT5_SERVER="Exness-MT5Trial",
    )


@pytest.fixture
def live_settings_unsafe() -> Settings:
    """Settings attempting live trading without allow flag (should be coerced)."""
    return Settings(
        TRADING_MODE="live",
        DRY_RUN=False,
        ALLOW_LIVE_TRADING=False,
    )


@pytest.fixture
def mt5_account_raw() -> SimpleNamespace:
    return SimpleNamespace(
        login=12345678,
        balance=10000.0,
        equity=10050.0,
        margin=100.0,
        margin_free=9950.0,
        currency="USD",
        leverage=500,
        name="Demo Account",
        server="Exness-MT5Trial",
        trade_mode=0,
    )


@pytest.fixture
def mt5_symbol_raw() -> SimpleNamespace:
    return SimpleNamespace(
        name="XAUUSD",
        bid=2350.10,
        ask=2350.30,
        point=0.01,
        digits=2,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        trade_contract_size=100.0,
        spread=20,
        trade_mode=MT5_TRADE_MODE_FULL,
        visible=True,
    )


@pytest.fixture
def mt5_tick_raw() -> SimpleNamespace:
    return SimpleNamespace(
        bid=2350.10,
        ask=2350.30,
        last=2350.20,
        volume=100.0,
        time=1_700_000_000,
    )


@pytest.fixture
def mt5_rates_array() -> np.ndarray:
    return np.array(
        [
            (1_700_000_000, 2350.0, 2355.0, 2348.0, 2352.0, 500, 2, 500),
            (1_700_000_900, 2352.0, 2356.0, 2350.0, 2354.0, 480, 2, 480),
        ],
        dtype=[
            ("time", "i8"),
            ("open", "f8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
            ("tick_volume", "i8"),
            ("spread", "i4"),
            ("real_volume", "i8"),
        ],
    )


@pytest.fixture
def mt5_position_raw() -> SimpleNamespace:
    return SimpleNamespace(
        ticket=1001,
        symbol="XAUUSD",
        volume=0.01,
        type=0,
        price_open=2350.0,
        price_current=2352.0,
        sl=2338.0,
        tp=2374.0,
        profit=2.0,
        time=1_700_000_000,
        swap=-0.25,
    )


@pytest.fixture
def mt5_pending_order_raw() -> SimpleNamespace:
    return SimpleNamespace(
        ticket=2001,
        symbol="XAUUSD",
        type=2,
        volume_current=0.01,
        price_open=2340.0,
        sl=0.0,
        tp=0.0,
        time_setup=1_700_000_000,
        comment="pending",
    )


class MockMT5Module:
    """Mock MetaTrader5 module for unit tests."""

    def __init__(self) -> None:
        self.initialize_result = True
        self.login_result = True
        self.last_error_value = (0, "Success")
        self.account_info_value: SimpleNamespace | None = None
        self.terminal_info_value: SimpleNamespace | None = None
        self.symbol_info_value: SimpleNamespace | None = None
        self.symbol_info_tick_value: SimpleNamespace | None = None
        self.positions_get_value: list[SimpleNamespace] | None = None
        self.orders_get_value: list[SimpleNamespace] | None = None
        self.copy_rates_value: np.ndarray | None = None
        self.copy_rates_range_value: np.ndarray | None = None
        self.copy_rates_from_value: np.ndarray | None = None
        self.symbols_get_value: list[SimpleNamespace] = []
        self.symbol_select_result = True
        self.initialize_calls: list[str | None] = []
        self.initialize_kwargs: dict[str, object] = {}
        self.login_calls: list[tuple[int, str, str]] = []
        self.shutdown_called = False
        self.history_deals_get_value: list[SimpleNamespace] | None = None
        self.history_orders_get_value: list[SimpleNamespace] | None = None

    def initialize(self, path: str | None = None, **kwargs: object) -> bool:
        self.initialize_calls.append(path)
        self.initialize_kwargs = dict(kwargs)
        return self.initialize_result

    def shutdown(self) -> None:
        self.shutdown_called = True

    def login(self, login: int, password: str, server: str) -> bool:
        self.login_calls.append((login, password, server))
        return self.login_result

    def last_error(self) -> tuple[int, str]:
        return self.last_error_value

    def account_info(self) -> SimpleNamespace | None:
        return self.account_info_value

    def terminal_info(self) -> SimpleNamespace | None:
        return self.terminal_info_value

    def symbol_info(self, symbol: str) -> SimpleNamespace | None:
        return self.symbol_info_value

    def symbol_info_tick(self, symbol: str) -> SimpleNamespace | None:
        return self.symbol_info_tick_value

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        return self.symbol_select_result

    def positions_get(self, symbol: str | None = None) -> list[SimpleNamespace] | None:
        return self.positions_get_value

    def orders_get(self, symbol: str | None = None) -> list[SimpleNamespace] | None:
        return self.orders_get_value

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: int,
        start_pos: int,
        count: int,
    ) -> np.ndarray | None:
        if self.copy_rates_value is None:
            return None
        return self.copy_rates_value

    def copy_rates_range(
        self,
        symbol: str,
        timeframe: int,
        date_from: object,
        date_to: object,
    ) -> np.ndarray | None:
        if self.copy_rates_range_value is None:
            return self.copy_rates_value
        return self.copy_rates_range_value

    def copy_rates_from(
        self,
        symbol: str,
        timeframe: int,
        date_from: object,
        count: int,
    ) -> np.ndarray | None:
        if self.copy_rates_from_value is None:
            return self.copy_rates_value
        return self.copy_rates_from_value

    def symbols_get(self, group: str = "*") -> list[SimpleNamespace]:
        return self.symbols_get_value

    def history_deals_get(
        self,
        date_from: object,
        date_to: object,
        group: str = "*",
    ) -> list[SimpleNamespace] | None:
        return self.history_deals_get_value

    def history_orders_get(
        self,
        date_from: object,
        date_to: object,
        group: str = "*",
    ) -> list[SimpleNamespace] | None:
        return self.history_orders_get_value

    def version(self) -> tuple[int, int, str]:
        return (5, 0, "mock")


@pytest.fixture
def mock_mt5_module(
    mt5_account_raw: SimpleNamespace,
    mt5_symbol_raw: SimpleNamespace,
    mt5_tick_raw: SimpleNamespace,
    mt5_rates_array: np.ndarray,
    mt5_position_raw: SimpleNamespace,
    mt5_pending_order_raw: SimpleNamespace,
) -> MockMT5Module:
    module = MockMT5Module()
    module.account_info_value = mt5_account_raw
    module.terminal_info_value = SimpleNamespace(connected=True, trade_allowed=True)
    module.symbol_info_value = mt5_symbol_raw
    module.symbol_info_tick_value = mt5_tick_raw
    module.positions_get_value = [mt5_position_raw]
    module.orders_get_value = [mt5_pending_order_raw]
    module.copy_rates_value = mt5_rates_array
    return module


@pytest.fixture
def mt5_client(default_settings: Settings, mock_mt5_module: MockMT5Module) -> MT5Client:
    return MT5Client(default_settings, mt5_module=mock_mt5_module)
