"""Phase 17.2 hotfix — preview data source must satisfy MtfDataSource.get_candles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
)
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, Tick
from exness_bot.execution.integration.demo_cli import (
    build_candidate_status_from_mtf_provider,
)
from exness_bot.execution.integration.factory import require_durable_setup_store
from exness_bot.market_analysis.mtf_service import MTF_TIMEFRAMES
from tests.fixtures.risk_data import make_account, make_xauusd_symbol

_NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _candle(ts: datetime, price: float = 2340.0) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=ts,
        open=price,
        high=price + 1,
        low=price - 1,
        close=price,
        volume=100.0,
        is_closed=True,
    )


def _closed_series(tf: Timeframe, n: int = 80) -> list[Candle]:
    # Space bars so they are closed relative to _NOW for each TF.
    step = {
        Timeframe.M15: timedelta(minutes=15),
        Timeframe.H1: timedelta(hours=1),
        Timeframe.H4: timedelta(hours=4),
        Timeframe.D1: timedelta(days=1),
    }[tf]
    out: list[Candle] = []
    for i in range(n):
        ts = _NOW - step * (n - i + 1)
        c = _candle(ts, 2340.0 + (i % 5) * 0.5)
        out.append(
            Candle(
                symbol="XAUUSD",
                timeframe=tf,
                timestamp=ts,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
                is_closed=True,
            )
        )
    return out


class IncompletePreviewDataSource:
    """Reproduces the Phase 17.2 bug: snapshot/tick only — no get_candles."""

    def get_snapshot(self) -> ProviderSnapshot:
        return ProviderSnapshot(
            connection_status=ProviderConnectionStatus.CONNECTED,
            data_source=DataSourceMode.MT5,
            account=make_account(),
            positions=(),
            updated_at=_NOW,
        )

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        del symbol
        return Tick(
            symbol="XAUUSD",
            bid=2340.9,
            ask=2341.1,
            last=2341.0,
            volume=1.0,
            timestamp=_NOW,
        )


class FullPreviewDataSource:
    """Satisfies MtfDataSource — same surface as MT5TradingDataProvider candles API."""

    def __init__(self, *, empty_tfs: set[str] | None = None) -> None:
        self.empty_tfs = empty_tfs or set()
        self.calls: list[tuple[str, Timeframe, int]] = []
        self._candles = {tf: _closed_series(tf) for tf in MTF_TIMEFRAMES}

    def get_snapshot(self) -> ProviderSnapshot:
        return ProviderSnapshot(
            connection_status=ProviderConnectionStatus.CONNECTED,
            data_source=DataSourceMode.MT5,
            account=make_account(),
            positions=(),
            updated_at=_NOW,
        )

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        del symbol
        return Tick(
            symbol="XAUUSD",
            bid=2340.9,
            ask=2341.1,
            last=2341.0,
            volume=1.0,
            timestamp=_NOW,
        )

    def get_symbol_info(self, symbol: str | None = None) -> Any:
        del symbol
        return make_xauusd_symbol(bid=2340.9, ask=2341.1).model_copy(
            update={"trade_tick_size": 0.01, "trade_tick_value": 1.0}
        )

    def resolve_broker_symbol(self, symbol: str | None = None) -> str | None:
        canonical = (symbol or "XAUUSD").strip().upper()
        if canonical == "XAUUSD":
            return "XAUUSDm"
        return canonical

    def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle] | None:
        self.calls.append((symbol, timeframe, count))
        if timeframe.value in self.empty_tfs:
            return None
        series = self._candles[timeframe]
        return series[-count:] if count < len(series) else list(series)


def _settings(tmp_path: Path) -> Settings:
    db = tmp_path / "setup.db"
    return Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{db.as_posix()}",
        SYMBOL="XAUUSD",
        MT5_SYMBOL="XAUUSDm",
        LIVE_SYMBOL_MAP="XAUUSD:XAUUSDm",
        CANDLE_HISTORY_COUNT=80,
    )


def test_incomplete_datasource_blocked_not_attribute_error(tmp_path: Path) -> None:
    """Regression: '_DataSource' object has no attribute 'get_candles'."""
    settings = _settings(tmp_path)
    store = require_durable_setup_store(settings)
    result = build_candidate_status_from_mtf_provider(
        settings=settings,
        provider=IncompletePreviewDataSource(),
        setup_store=store,
        symbol="XAUUSD",
    )
    assert result.status is None
    assert result.blocked_result is not None
    assert "MTF_DATA_UNAVAILABLE" in result.blocked_result
    assert "get_candles" in result.blocked_result
    assert "AttributeError" not in (result.blocked_result or "")


def test_full_provider_retrieves_all_mtf_timeframes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = require_durable_setup_store(settings)
    provider = FullPreviewDataSource()
    result = build_candidate_status_from_mtf_provider(
        settings=settings,
        provider=provider,
        setup_store=store,
        symbol="XAUUSD",
    )
    assert result.blocked_result is None
    assert result.timeframe_status is not None
    for tf in ("M15", "H1", "H4", "D1"):
        assert result.timeframe_status[tf] != "INSUFFICIENT"
    requested = {tf for _, tf, _ in provider.calls}
    assert requested == set(MTF_TIMEFRAMES)
    assert all(sym == "XAUUSD" for sym, _, _ in provider.calls)


def test_broker_symbol_mapping_xauusd_to_xauusdm(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = require_durable_setup_store(settings)
    provider = FullPreviewDataSource()
    result = build_candidate_status_from_mtf_provider(
        settings=settings,
        provider=provider,
        setup_store=store,
        symbol="XAUUSD",
    )
    assert result.blocked_result is None
    assert result.status is not None
    # Mapping owned by provider.resolve_broker_symbol — used by MTF service
    assert provider.resolve_broker_symbol("XAUUSD") == "XAUUSDm"


def test_unavailable_candles_blocked_lists_timeframe(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = require_durable_setup_store(settings)
    provider = FullPreviewDataSource(empty_tfs={"H4"})
    result = build_candidate_status_from_mtf_provider(
        settings=settings,
        provider=provider,
        setup_store=store,
        symbol="XAUUSD",
    )
    assert result.status is None
    assert result.blocked_result is not None
    assert "MTF_DATA_UNAVAILABLE" in result.blocked_result
    assert "H4" in result.blocked_result


def test_get_candles_signature_matches_protocol() -> None:
    """Document exact reused signature: get_candles(symbol, timeframe, count)."""
    provider = FullPreviewDataSource()
    candles = provider.get_candles("XAUUSD", Timeframe.M15, 50)
    assert candles is not None
    assert len(candles) == 50
    assert candles[0].timestamp < candles[-1].timestamp
