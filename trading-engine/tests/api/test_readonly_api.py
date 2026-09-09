"""Comprehensive read-only API tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from exness_bot.api.app import create_app
from exness_bot.api.dependencies import get_read_service
from exness_bot.api.services.read_service import ReadService
from exness_bot.backtest.baseline_runner import baseline_paths, run_baseline, write_baseline_outputs
from exness_bot.config.settings import Settings
from exness_bot.data.mock_provider import MockTradingDataProvider


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
        assert data["accountProfile"] == "demo"
        assert data["candleEngine"]["status"] == "STOPPED"
        assert data["candleEngine"]["dataSource"] == "MOCK"
        assert data["signalEngine"]["status"] == "STOPPED"
        assert data["signalEngine"]["strategy"] == "ema_rsi_atr_v1"
        assert data["signalEngine"]["dataSource"] == "MOCK"
        assert data["signalEngine"]["lastSignal"] is None
        assert data["paperExecution"]["status"] == "STOPPED"
        assert data["paperExecution"]["mode"] == "paper"
        assert data["paperExecution"]["openPositions"] == 0
        assert data["paperExecution"]["lastExecution"] is None


class TestPaper:
    def test_paper_readonly_snapshot(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/paper")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mode"] == "paper"
        assert data["researchOnly"] is True
        assert data["status"] == "STOPPED"
        assert data["openPositions"] == 0
        assert data["trades"] == []
        assert data["accountKind"] == "paper"
        assert data["positions"] == []

    def test_paper_has_no_mutation_routes(self, api_client: TestClient) -> None:
        assert api_client.post("/api/v1/paper").status_code in {405, 422}
        assert api_client.post("/api/v1/trade").status_code == 404
        assert api_client.post("/api/v1/order").status_code == 404
        assert api_client.post("/api/v1/execute").status_code == 404


class TestAccount:
    def test_account_snapshot(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/account")
        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data["balance"], float)
        assert data["currency"] == "USD"
        assert data["updatedAt"].endswith("Z")
        assert "leverage" in data
        assert "profit" in data


class TestQuotes:
    def test_quotes_watchlist_mock(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/quotes")
        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 2
        symbols = {item["symbol"] for item in data}
        assert "XAUUSD" in symbols
        assert "EURUSD" in symbols
        gold = next(item for item in data if item["symbol"] == "XAUUSD")
        assert gold["available"] is True
        assert gold["bid"] > 0
        assert gold["ask"] >= gold["bid"]
        assert gold["freshness"] == "LIVE"
        assert gold["updatedAt"].endswith("Z")

    def test_quotes_custom_symbols(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/quotes?symbols=EURUSD,BTCUSD")
        assert response.status_code == 200
        data = response.json()["data"]
        assert [item["symbol"] for item in data] == ["EURUSD", "BTCUSD"]


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


class TestAccounts:
    def test_list_accounts_hides_passwords(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/accounts")
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        for profile in data["profiles"]:
            assert "password" not in profile
        assert data["activeProfile"] == "demo"
        assert data["readOnly"] is True
        assert data["liveOrdersEnabled"] is False
        assert data["allowLiveTrading"] is False
        kinds = {item["id"] for item in data["profiles"]}
        assert kinds == {"demo", "live"}

    def test_switch_live_without_credentials(self, project_root: Path) -> None:
        settings = Settings(
            MT5_LOGIN=111,
            MT5_PASSWORD="demo-secret",
            MT5_SERVER="Exness-MT5Trial",
            MT5_LIVE_LOGIN=None,
            MT5_LIVE_PASSWORD="",
            MT5_LIVE_SERVER="",
        )
        service = ReadService(
            settings,
            MockTradingDataProvider(settings),
            project_root=project_root,
        )
        app = create_app()
        app.dependency_overrides[get_read_service] = lambda: service
        client = TestClient(app)
        response = client.post("/api/v1/accounts/active", json={"profile": "live"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "LIVE_ACCOUNT_NOT_CONFIGURED"

    def test_switch_invalid_profile(self, api_client: TestClient) -> None:
        response = api_client.post("/api/v1/accounts/active", json={"profile": "paper"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_PARAMETER"

    def test_switch_demo_to_live_when_configured(self, project_root: Path) -> None:
        settings = Settings(
            MT5_LOGIN=111,
            MT5_PASSWORD="demo-secret",
            MT5_SERVER="Exness-MT5Trial",
            MT5_LIVE_LOGIN=222,
            MT5_LIVE_PASSWORD="live-secret",
            MT5_LIVE_SERVER="Exness-MT5Real",
            ALLOW_LIVE_TRADING=False,
            TRADING_MODE="dry_run",
        )
        service = ReadService(
            settings,
            MockTradingDataProvider(settings),
            project_root=project_root,
        )
        app = create_app()
        app.dependency_overrides[get_read_service] = lambda: service
        client = TestClient(app)

        switched = client.post("/api/v1/accounts/active", json={"profile": "live"})
        assert switched.status_code == 200
        data = switched.json()["data"]
        assert data["activeProfile"] == "live"
        assert data["liveOrdersEnabled"] is False
        assert data["allowLiveTrading"] is False
        assert data["readOnly"] is True
        live = next(item for item in data["profiles"] if item["id"] == "live")
        assert live["active"] is True
        assert live["login"] == 222
        assert "live-secret" not in str(switched.json())

        status = client.get("/api/v1/status")
        assert status.json()["data"]["accountProfile"] == "live"


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

    def test_cors_preflight_post_accounts(self, api_client: TestClient) -> None:
        response = api_client.options(
            "/api/v1/accounts/active",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestReadOnlySecurity:
    def test_no_mutation_routes(self, api_client: TestClient) -> None:
        app = api_client.app
        allowed = {("/api/v1/accounts/active", "POST")}
        mutation_methods = {"POST", "PUT", "PATCH", "DELETE"}
        for route in app.routes:
            methods = getattr(route, "methods", set()) or set()
            path = getattr(route, "path", "")
            for method in methods & mutation_methods:
                assert (path, method) in allowed, f"Mutation route found: {path} {method}"

    def test_post_orders_rejected(self, api_client: TestClient) -> None:
        response = api_client.post("/api/v1/orders", json={})
        assert response.status_code in {404, 405}


class TestTechnicalSnapshot:
    def test_technical_snapshot_ok(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/analysis/XAUUSD/technical-snapshot")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["schema_version"] == "1.0"
        assert data["symbol"] == "XAUUSD"
        assert data["primary_timeframe"] == "M15"
        assert set(data["timeframes"]) == {"M15", "H1", "H4", "D1"}
        assert data["timeframes"]["M15"]["role"] == "PRIMARY"
        assert data["bot_analysis"]["production_strategy"] == "mtf_technical_v1"
        assert "freshness" in data
        assert isinstance(data["facts"], list)

    def test_technical_snapshot_compact(self, api_client: TestClient) -> None:
        response = api_client.get(
            "/api/v1/analysis/XAUUSD/technical-snapshot?view=compact"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert "facts" in data
        assert "ema20" in data["timeframes"]["M15"]
        assert "support_levels" not in data["timeframes"]["M15"]

    def test_technical_snapshot_no_post(self, api_client: TestClient) -> None:
        assert api_client.post("/api/v1/analysis/XAUUSD/technical-snapshot").status_code in {
            405,
            422,
        }


class TestValidation:
    def test_invalid_page_size(self, api_client: TestClient) -> None:
        response = api_client.get("/api/v1/trades?pageSize=0")
        assert response.status_code == 422
