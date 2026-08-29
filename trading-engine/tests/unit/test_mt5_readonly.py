"""Tests for MT5 read-only client and safety boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from exness_bot.broker.mt5.connection_manager import ConnectionState, MT5ConnectionManager
from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient
from exness_bot.broker.mt5.trading_client import MT5TradingClient
from exness_bot.config.settings import Settings
from tests.conftest import MockMT5Module


class TestMT5ReadOnlyClientSafety:
    def test_readonly_client_has_no_order_send(self) -> None:
        assert "order_send" not in dir(MT5ReadOnlyClient)

    def test_trading_client_has_order_send(self) -> None:
        assert hasattr(MT5TradingClient, "order_send")

    def test_readonly_module_files_contain_no_order_send(self) -> None:
        root = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
        readonly_paths = [
            root / "broker/mt5/read_only_client.py",
            root / "broker/mt5/connection_manager.py",
            root / "broker/mt5/symbol_resolver.py",
            root / "data/mt5_provider.py",
        ]
        forbidden_patterns = ("def order_send", ".order_send(")
        for path in readonly_paths:
            source = path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                assert pattern not in source, f"{pattern} found in {path}"

    def test_readonly_client_connects(self, default_settings: Settings) -> None:
        module = MockMT5Module()
        client = MT5ReadOnlyClient(default_settings, mt5_module=module)
        client.initialize()
        client.login()
        assert client.is_logged_in is True
        assert module.shutdown_called is False


class TestMT5ConnectionManager:
    def test_unavailable_on_linux(self, default_settings: Settings) -> None:
        settings = Settings(
            TRADING_MODE="demo",
            DATA_SOURCE="mt5",
            MT5_ENABLED=True,
            MT5_LOGIN=123,
            MT5_PASSWORD="x",
        )
        manager = MT5ConnectionManager(settings, client=MT5ReadOnlyClient(settings))
        status = manager.connect()
        if __import__("sys").platform != "win32":
            assert status.state == ConnectionState.UNAVAILABLE

    def test_lazy_connect_with_mock(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("exness_bot.broker.mt5.connection_manager.sys.platform", "win32")
        settings = Settings(
            TRADING_MODE="demo",
            DATA_SOURCE="mt5",
            MT5_ENABLED=True,
            MT5_LOGIN=12345678,
            MT5_PASSWORD="demo-password",
        )
        client = MT5ReadOnlyClient(settings, mt5_module=mock_mt5_module)
        manager = MT5ConnectionManager(settings, client=client)
        assert manager.status.state == ConnectionState.DISCONNECTED
        status = manager.connect()
        assert status.state == ConnectionState.CONNECTED
        assert mock_mt5_module.initialize_calls

    def test_reconnect_after_credential_change(
        self,
        mock_mt5_module: MockMT5Module,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("exness_bot.broker.mt5.connection_manager.sys.platform", "win32")
        settings = Settings(
            TRADING_MODE="demo",
            DATA_SOURCE="mt5",
            MT5_ENABLED=True,
            MT5_LOGIN=111,
            MT5_PASSWORD="demo-password",
            MT5_SERVER="Exness-MT5Trial",
        )
        client = MT5ReadOnlyClient(settings, mt5_module=mock_mt5_module)
        manager = MT5ConnectionManager(settings, client=client)
        first = manager.connect()
        assert first.state == ConnectionState.CONNECTED
        client.set_credentials(222, "live-password", "Exness-MT5Real")
        second = manager.reconnect()
        assert second.state == ConnectionState.CONNECTED
        assert mock_mt5_module.login_calls[-1] == (222, "live-password", "Exness-MT5Real")
