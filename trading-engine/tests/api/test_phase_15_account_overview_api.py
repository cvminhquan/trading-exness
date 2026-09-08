"""API tests for Phase 15.X account overview endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from exness_bot.api.app import create_app
from exness_bot.api.dependencies import get_read_service
from exness_bot.api.services.read_service import ReadService
from exness_bot.backtest.baseline_runner import baseline_paths, run_baseline, write_baseline_outputs
from exness_bot.config.settings import Settings
from exness_bot.data.mock_provider import MockTradingDataProvider
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
)
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import AccountInfo, Position


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    result = run_baseline(Settings(), project_root=tmp_path)
    write_baseline_outputs(result, baseline_paths(tmp_path))
    return tmp_path


@pytest.fixture
def api_client(project_root: Path) -> TestClient:
    settings = Settings()
    service = ReadService(
        settings,
        MockTradingDataProvider(settings),
        project_root=project_root,
    )
    app = create_app()
    app.dependency_overrides[get_read_service] = lambda: service
    return TestClient(app)


class TestAccountOverviewApi:
    def test_overview_live_mock(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/account/overview")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "LIVE"
        assert "balance" in data
        assert "equity" in data
        assert "freeMargin" in data
        assert "unrealizedPnl" in data
        assert "realizedPnlToday" in data
        assert "totalPnlToday" in data
        assert data["totalPnlToday"] == pytest.approx(
            data["realizedPnlToday"] + data["unrealizedPnl"]
        )
        assert "ageSeconds" in data
        assert "updatedAt" in data
        assert data["loginMasked"] is not None
        assert "password" not in str(response.json()).lower() or "mt5_password" not in str(
            response.json()
        ).lower()
        assert "MT5_PASSWORD" not in str(response.json())
        safety = data["safety"]
        assert safety["killSwitch"] in {"ON", "OFF"}
        assert safety["executionMode"] in {"PAPER", "LIVE"}
        assert safety["mt5Status"] == "CONNECTED"

    def test_legacy_account_unchanged_keys(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/account")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "todayPnl" in data
        assert "drawdownPct" in data
        assert "realizedPnlToday" not in data

    def test_daily_pnl_history(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/account/pnl/daily", params={"days": 7})
        assert response.status_code == 200
        rows = response.json()["data"]
        assert len(rows) == 7
        assert "date" in rows[0]
        assert "realizedPnl" in rows[0]

    def test_overview_disconnected(self, project_root: Path) -> None:
        class DisconnectedProvider(MockTradingDataProvider):
            def get_snapshot(self) -> ProviderSnapshot:
                return ProviderSnapshot(
                    connection_status=ProviderConnectionStatus.DISCONNECTED,
                    data_source=DataSourceMode.MOCK,
                    account=None,
                    positions=(),
                    updated_at=datetime.now(tz=UTC),
                    message="Mất kết nối MT5.",
                )

            def requires_live_broker(self) -> bool:
                return True

        settings = Settings()
        service = ReadService(
            settings,
            DisconnectedProvider(settings),
            project_root=project_root,
        )
        app = create_app()
        app.dependency_overrides[get_read_service] = lambda: service
        client = TestClient(app)
        response = client.get("/api/v1/account/overview")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "DISCONNECTED"
        assert data["balance"] is None
        assert data["message"]

    def test_tiny_account_and_negative_pnl(self, project_root: Path) -> None:
        class TinyProvider(MockTradingDataProvider):
            def get_snapshot(self) -> ProviderSnapshot:
                account = AccountInfo(
                    login=4158,
                    balance=10.50,
                    equity=10.63,
                    margin=1.24,
                    free_margin=9.39,
                    currency="USD",
                    leverage=100,
                    server="Exness-MT5Trial17",
                    trade_mode="demo",
                    profit=0.13,
                    margin_level=857.25,
                )
                positions = (
                    Position(
                        ticket=1,
                        symbol="XAUUSD",
                        volume=0.01,
                        direction=SignalDirection.LONG,
                        open_price=4398.67,
                        current_price=4401.12,
                        stop_loss=None,
                        take_profit=None,
                        profit=0.13,
                        swap=0.0,
                        open_time=datetime.now(tz=UTC),
                    ),
                )
                return ProviderSnapshot(
                    connection_status=ProviderConnectionStatus.CONNECTED,
                    data_source=DataSourceMode.MOCK,
                    account=account,
                    positions=positions,
                    updated_at=datetime.now(tz=UTC),
                    broker_server=account.server,
                )

            def get_trade_history(self, query):  # type: ignore[no-untyped-def]
                from exness_bot.data.models import TradeHistoryResult
                from exness_bot.domain.models import ClosedTrade

                trade = ClosedTrade(
                    id="x",
                    symbol="XAUUSD",
                    strategy="ema_rsi_atr_v1",
                    direction=SignalDirection.LONG,
                    volume=0.01,
                    entry_price=1.0,
                    exit_price=1.0,
                    gross_pnl=-0.05,
                    commission=-0.03,
                    swap=0.0,
                    net_pnl=-0.08,
                    exit_reason="manual",
                    closed_at=datetime.now(tz=UTC),
                    r_multiple=None,
                )
                return TradeHistoryResult(
                    trades=(trade,),
                    total=1,
                    updated_at=datetime.now(tz=UTC),
                )

        settings = Settings()
        service = ReadService(
            settings,
            TinyProvider(settings),
            project_root=project_root,
        )
        app = create_app()
        app.dependency_overrides[get_read_service] = lambda: service
        client = TestClient(app)
        data = client.get("/api/v1/account/overview").json()["data"]
        assert data["balance"] == 10.50
        assert data["equity"] == 10.63
        assert data["unrealizedPnl"] == pytest.approx(0.13)
        assert data["realizedPnlToday"] == pytest.approx(-0.08)
        assert data["totalPnlToday"] == pytest.approx(0.05)
        assert data["loginMasked"] == "***4158"
        assert data["dailyReturnAvailable"] is True
        assert data["dailyReturnPct"] is not None
