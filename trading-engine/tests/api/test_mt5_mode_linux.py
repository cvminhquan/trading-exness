"""API tests for MT5 mode graceful failure on Linux."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from exness_bot.api.app import create_app
from exness_bot.api.dependencies import get_read_service
from exness_bot.api.services.read_service import ReadService
from exness_bot.config.settings import Settings
from exness_bot.data.factory import create_trading_data_provider


@pytest.fixture
def mt5_api_client(project_root: Path) -> TestClient:
    settings = Settings(
        DATA_SOURCE="mt5",
        MT5_ENABLED=True,
        MT5_LOGIN=1,
        MT5_PASSWORD="x",
    )
    provider = create_trading_data_provider(settings)
    service = ReadService(settings, provider, project_root=project_root)
    app = create_app()
    app.dependency_overrides[get_read_service] = lambda: service
    return TestClient(app)


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux graceful-failure test")
class TestMT5ModeLinux:
    def test_status_still_works(self, mt5_api_client: TestClient) -> None:
        response = mt5_api_client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["connectionStatus"] == "DISCONNECTED"

    def test_account_returns_503(self, mt5_api_client: TestClient) -> None:
        response = mt5_api_client.get("/api/v1/account")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "BROKER_UNAVAILABLE"

    def test_backtests_still_work(self, mt5_api_client: TestClient) -> None:
        response = mt5_api_client.get("/api/v1/backtests")
        assert response.status_code == 200

    def test_health_ok(self, mt5_api_client: TestClient) -> None:
        response = mt5_api_client.get("/health")
        assert response.status_code == 200

    def test_quotes_unavailable_not_mocked(self, mt5_api_client: TestClient) -> None:
        response = mt5_api_client.get("/api/v1/quotes?symbols=XAUUSD")
        assert response.status_code == 200
        gold = response.json()["data"][0]
        assert gold["symbol"] == "XAUUSD"
        assert gold["available"] is False
        assert gold["freshness"] == "UNAVAILABLE"
        assert gold["bid"] is None
