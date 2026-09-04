"""Phase 10.7 live read-only validation tests — no real MT5 required."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from exness_bot.api.app import create_app
from exness_bot.api.dependencies import get_read_service
from exness_bot.api.services.read_service import ReadService
from exness_bot.broker.mt5.mapper import map_account_info, map_position, map_tick
from exness_bot.config.settings import DataSource, Settings
from exness_bot.data.factory import create_trading_data_provider
from exness_bot.data.freshness import QuoteFreshness, classify_quote_freshness
from exness_bot.data.mock_provider import MockTradingDataProvider
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
    TradeHistoryQuery,
    TradeHistoryResult,
)
from exness_bot.data.mt5_provider import MT5TradingDataProvider
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import Tick


def _api_client(provider: object, settings: Settings | None = None) -> TestClient:
    resolved = settings or Settings(DATA_SOURCE="mock")
    service = ReadService(resolved, provider, project_root=Path(__file__).resolve().parents[2])
    app = create_app()
    app.dependency_overrides[get_read_service] = lambda: service
    return TestClient(app)


class _DisconnectedProvider:
    data_source = DataSourceMode.MT5

    def requires_live_broker(self) -> bool:
        return True

    def get_snapshot(self) -> ProviderSnapshot:
        return ProviderSnapshot(
            connection_status=ProviderConnectionStatus.DISCONNECTED,
            data_source=DataSourceMode.MT5,
            account=None,
            positions=(),
            updated_at=datetime.now(tz=UTC),
            message="Mất kết nối MT5.",
        )

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        return None

    def get_trade_history(self, query: TradeHistoryQuery) -> TradeHistoryResult:
        return TradeHistoryResult(trades=(), total=0, updated_at=datetime.now(tz=UTC))


class _StaleTickProvider(MockTradingDataProvider):
    def get_tick(self, symbol: str | None = None) -> Tick | None:
        tick = super().get_tick(symbol)
        if tick is None:
            return None
        return tick.model_copy(update={"timestamp": datetime.now(tz=UTC) - timedelta(seconds=30)})


class TestQuoteFreshness:
    def test_unavailable_when_missing(self) -> None:
        assert (
            classify_quote_freshness(available=False, tick_time=None)
            is QuoteFreshness.UNAVAILABLE
        )

    def test_live_within_threshold(self) -> None:
        now = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
        tick = now - timedelta(seconds=3)
        assert (
            classify_quote_freshness(
                available=True,
                tick_time=tick,
                now=now,
                stale_after_seconds=10,
            )
            is QuoteFreshness.LIVE
        )

    def test_stale_after_threshold(self) -> None:
        now = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
        tick = now - timedelta(seconds=11)
        assert (
            classify_quote_freshness(
                available=True,
                tick_time=tick,
                now=now,
                stale_after_seconds=10,
            )
            is QuoteFreshness.STALE
        )


class TestLiveMapping:
    def test_tick_timestamp_is_utc(self, mt5_tick_raw: SimpleNamespace) -> None:
        tick = map_tick("XAUUSD", mt5_tick_raw)
        assert tick.symbol == "XAUUSD"
        assert tick.timestamp.tzinfo is UTC
        assert tick.timestamp.utcoffset() == timedelta(0)
        assert tick.bid == 2350.10
        assert tick.ask == 2350.30

    def test_account_maps_profit_and_leverage(self, mt5_account_raw: SimpleNamespace) -> None:
        mt5_account_raw.profit = 50.0
        mt5_account_raw.margin_level = 2500.0
        account = map_account_info(mt5_account_raw)
        assert account.leverage == 500
        assert account.profit == 50.0
        assert account.margin_level == 2500.0
        assert account.currency == "USD"

    def test_position_maps_swap_and_ticket(self, mt5_position_raw: SimpleNamespace) -> None:
        position = map_position(mt5_position_raw, canonical_symbol="XAUUSD")
        assert position.ticket == 1001
        assert position.symbol == "XAUUSD"
        assert position.direction == SignalDirection.LONG
        assert position.swap == -0.25
        assert position.open_time.tzinfo is UTC


class TestNoMockFallback:
    def test_mt5_data_source_never_returns_mock_provider(self) -> None:
        settings = Settings(DATA_SOURCE="mt5", MT5_ENABLED=True)
        provider = create_trading_data_provider(settings)
        assert isinstance(provider, MT5TradingDataProvider)
        assert not isinstance(provider, MockTradingDataProvider)
        assert settings.data_source == DataSource.MT5


class TestQuotesApiSchema:
    def test_mock_quotes_are_live_canonical_xauusd(self) -> None:
        client = _api_client(MockTradingDataProvider(Settings(DATA_SOURCE="mock")))
        response = client.get("/api/v1/quotes?symbols=XAUUSD")
        assert response.status_code == 200
        gold = response.json()["data"][0]
        assert gold["symbol"] == "XAUUSD"
        assert gold["freshness"] == "LIVE"
        assert gold["available"] is True
        assert gold["bid"] > 0
        assert gold["ask"] >= gold["bid"]
        assert gold["spread"] == round(gold["ask"] - gold["bid"], 8)
        assert gold["updatedAt"].endswith("Z")

    def test_stale_tick_is_not_labelled_live(self) -> None:
        settings = Settings(DATA_SOURCE="mock", LIVE_DATA_STALE_SECONDS=10)
        client = _api_client(_StaleTickProvider(settings), settings)
        gold = client.get("/api/v1/quotes?symbols=XAUUSD").json()["data"][0]
        assert gold["available"] is True
        assert gold["freshness"] == "STALE"

    def test_account_schema_includes_mt5_fields(self) -> None:
        client = _api_client(MockTradingDataProvider(Settings(DATA_SOURCE="mock")))
        data = client.get("/api/v1/account").json()["data"]
        assert data["leverage"] == 500
        assert data["profit"] == 113.8
        assert data["marginLevel"] is not None
        assert data["currency"] == "USD"
        assert "password" not in str(data).lower()

    def test_positions_include_swap(self) -> None:
        client = _api_client(MockTradingDataProvider(Settings(DATA_SOURCE="mock")))
        item = client.get("/api/v1/positions").json()["data"][0]
        assert item["id"] == "1001"
        assert item["symbol"] == "XAUUSD"
        assert item["swap"] == -0.5
        assert item["openedAt"].endswith("Z")

    def test_trades_include_commission_swap_utc(self) -> None:
        client = _api_client(MockTradingDataProvider(Settings(DATA_SOURCE="mock")))
        item = client.get("/api/v1/trades").json()["data"][0]
        assert item["closedAt"].endswith("Z")
        assert "commission" in item
        assert "swap" in item
        assert item["symbol"] == "XAUUSD"


class TestDisconnectedBroker:
    def test_health_still_ok(self) -> None:
        client = _api_client(_DisconnectedProvider(), Settings(DATA_SOURCE="mt5"))
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_status_reports_disconnected(self) -> None:
        client = _api_client(_DisconnectedProvider(), Settings(DATA_SOURCE="mt5"))
        data = client.get("/api/v1/status").json()["data"]
        assert data["connectionStatus"] == "DISCONNECTED"
        assert data["botStatus"] == "DISCONNECTED"

    def test_account_returns_broker_unavailable(self) -> None:
        client = _api_client(_DisconnectedProvider(), Settings(DATA_SOURCE="mt5"))
        response = client.get("/api/v1/account")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "BROKER_UNAVAILABLE"

    def test_quotes_are_unavailable_not_mocked(self) -> None:
        client = _api_client(_DisconnectedProvider(), Settings(DATA_SOURCE="mt5"))
        gold = client.get("/api/v1/quotes?symbols=XAUUSD").json()["data"][0]
        assert gold["symbol"] == "XAUUSD"
        assert gold["available"] is False
        assert gold["freshness"] == "UNAVAILABLE"
        assert gold["bid"] is None


class TestReadOnlyApiSurface:
    def test_v1_has_no_trade_mutation_routes(self) -> None:
        source = (
            Path(__file__).resolve().parents[2] / "src" / "exness_bot" / "api" / "routes" / "v1.py"
        ).read_text(encoding="utf-8")
        assert source.count("@router.post") == 1
        assert "/accounts/active" in source
        assert "@router.put" not in source
        assert "@router.patch" not in source
        assert "@router.delete" not in source
        for forbidden in (
            "order_send",
            "order_check",
            "position_close",
            "TRADE_ACTION_DEAL",
            "TRADE_ACTION_PENDING",
            "TRADE_ACTION_SLTP",
            "TRADE_ACTION_REMOVE",
        ):
            assert forbidden not in source
