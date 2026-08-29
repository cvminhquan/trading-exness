"""Comprehensive read-only API tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from exness_bot.api.app import create_app
from exness_bot.api.dependencies import get_read_service
from exness_bot.api.services.read_service import ReadService
from exness_bot.config.settings import Settings
from exness_bot.data.mock_provider import MockTradingDataProvider


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


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


class TestHealth:
    def test_health_ok(self, api_client: TestClient) -> None:
        response = api_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestStatus:
    def test_status_connected_mock(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/status")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        data = body["data"]
        assert data["connectionStatus"] == "CONNECTED"
        assert data["botStatus"] == "RUNNING"
        assert "tradingMode" in data


class TestAccount:
    def test_account_snapshot(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/account")
        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data["balance"], float)
        assert data["currency"] == "USD"
        assert data["updatedAt"].endswith("Z")


class TestPositions:
    def test_positions_mock(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/positions")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] >= 1
        assert body["data"][0]["symbol"] == "XAUUSD"


class TestTrades:
    def test_trades_mock_paginated(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/trades?page=1&pageSize=10")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] >= 1
        assert body["meta"]["pageSize"] == 10

    def test_trades_invalid_result(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/trades?result=INVALID")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_PARAMETER"


class TestStrategy:
    def test_strategy_hold_mock(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/strategy")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["currentSignal"]["action"] == "HOLD"
        assert data["status"] == "RUNNING"


class TestRisk:
    def test_risk_limits(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/risk")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["limits"]) >= 5
        assert data["riskPerTradePct"] == 0.5


class TestSettings:
    def test_settings_readonly(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/settings")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["strategy"] == "ema_rsi_atr_v1"
        assert data["symbol"] == "XAUUSD"


class TestOverview:
    def test_overview(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/overview")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "account" in data
        assert "currentSignal" in data


class TestBacktests:
    def test_list_backtests(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/backtests")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert body["meta"]["total"] >= 1

    def test_backtest_detail(self, api_client: TestClient) -> None:
        report_id = "ema_rsi_atr_v1_XAUUSD_M15_baseline"
        response = api_client.get(f"/api/v1/backtests/{report_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == report_id
        assert data["status"] == "insufficient_data"
        assert data["performance"] is None

    def test_backtest_not_found(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/backtests/nonexistent-id")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BACKTEST_NOT_FOUND"


class TestCors:
    def test_cors_preflight(self, api_client: TestClient) -> None:
        response = api_client.options(
            "/api/v1/status",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestReadOnlySecurity:
    def test_no_mutation_routes(self, api_client: TestClient) -> None:
        app = api_client.app
        mutation_methods = {"POST", "PUT", "PATCH", "DELETE"}
        for route in app.routes:
            methods = getattr(route, "methods", set())
            forbidden = methods & mutation_methods
            assert not forbidden, f"Mutation route found: {route.path} {forbidden}"

    def test_post_orders_rejected(self, api_client: TestClient) -> None:
        response = api_client.post("/api/v1/orders", json={})
        assert response.status_code in {404, 405}


class TestValidation:
    def test_invalid_page_size(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/trades?pageSize=0")
        assert response.status_code == 422
