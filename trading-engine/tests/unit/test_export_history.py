"""Tests for MT5 historical data export tool."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from exness_bot.backtest.loader import load_candles_from_csv
from exness_bot.broker.mt5.client import MT5Client
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.tools.export_history.config import (
    build_export_config,
    default_output_path,
    parse_export_date,
    timeframe_from_string,
)
from exness_bot.tools.export_history.exporter import HistoricalExporter
from exness_bot.tools.export_history.fetcher import EmptyHistoryError, fetch_historical_rates
from exness_bot.tools.export_history.models import GapKind
from exness_bot.tools.export_history.serializer import write_history_csv
from exness_bot.tools.export_history.symbol_resolver import (
    SymbolResolutionError,
    find_matching_symbols,
    resolve_broker_symbol,
)
from exness_bot.tools.export_history.validation import classify_gap, validate_exported_rates
from tests.conftest import MockMT5Module
from tests.fixtures.export_rates import make_rates_array


class TestExportConfig:
    def test_parse_export_date_start(self) -> None:
        parsed = parse_export_date("2023-01-01")
        assert parsed == datetime(2023, 1, 1, tzinfo=UTC)

    def test_parse_export_date_end_of_day(self) -> None:
        parsed = parse_export_date("2026-08-29", end_of_day=True)
        assert parsed.hour == 23
        assert parsed.minute == 59

    def test_invalid_date_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid date"):
            parse_export_date("29-08-2026")

    def test_build_config_requires_dates(self) -> None:
        with pytest.raises(ValueError, match="Start and end dates are required"):
            build_export_config(
                symbol="XAUUSD",
                timeframe="M15",
                start=None,
                end=None,
                output=None,
            )

    def test_build_config_from_env_defaults(self) -> None:
        settings = Settings(
            HISTORICAL_SYMBOL="XAUUSD",
            HISTORICAL_START="2023-01-01",
            HISTORICAL_END="2023-02-01",
        )
        config = build_export_config(
            symbol=None,
            timeframe=None,
            start=None,
            end=None,
            output=None,
            settings=settings,
        )
        assert config.symbol == "XAUUSD"
        assert config.timeframe == Timeframe.M15

    def test_invalid_date_range(self) -> None:
        with pytest.raises(ValueError, match="End date must be after start date"):
            build_export_config(
                symbol="XAUUSD",
                timeframe="M15",
                start="2026-01-01",
                end="2025-01-01",
                output=None,
            )

    def test_timeframe_mapping(self) -> None:
        assert timeframe_from_string("m15") == Timeframe.M15

    def test_unsupported_timeframe(self) -> None:
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            timeframe_from_string("M2")

    def test_default_output_path_uses_symbol(self) -> None:
        path = default_output_path("XAUUSDm", Timeframe.M15)
        assert path.name == "XAUUSDm_M15.csv"


class TestSymbolResolver:
    def test_resolve_exact_symbol(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        client = MT5Client(default_settings, mt5_module=mock_mt5_module)
        assert resolve_broker_symbol(client, "XAUUSD") == "XAUUSD"

    def test_resolve_fuzzy_single_match(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        def symbol_info(symbol: str) -> SimpleNamespace | None:
            if symbol == "XAUUSDm":
                return SimpleNamespace(name="XAUUSDm", visible=True)
            return None

        mock_mt5_module.symbol_info = symbol_info  # type: ignore[method-assign]
        mock_mt5_module.symbols_get_value = [
            SimpleNamespace(name="XAUUSDm"),
        ]
        client = MT5Client(default_settings, mt5_module=mock_mt5_module)
        assert resolve_broker_symbol(client, "XAUUSD") == "XAUUSDm"

    def test_invalid_symbol_lists_matches(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.symbol_info_value = None
        mock_mt5_module.symbols_get_value = [
            SimpleNamespace(name="XAUUSDm"),
            SimpleNamespace(name="XAUUSD"),
        ]
        client = MT5Client(default_settings, mt5_module=mock_mt5_module)
        with pytest.raises(SymbolResolutionError, match="Possible matches"):
            resolve_broker_symbol(client, "XAU")

    def test_find_matching_symbols_exact_match(self, mock_mt5_module: MockMT5Module) -> None:
        mock_mt5_module.symbols_get_value = [
            SimpleNamespace(name="XAUUSD"),
            SimpleNamespace(name="XAUUSDm"),
            SimpleNamespace(name="EURUSD"),
        ]
        client = MT5Client(Settings(), mt5_module=mock_mt5_module)
        matches = find_matching_symbols(client, "XAUUSD")
        assert matches == ["XAUUSD"]

    def test_find_matching_symbols_prefix_only(self, mock_mt5_module: MockMT5Module) -> None:
        mock_mt5_module.symbols_get_value = [
            SimpleNamespace(name="XAUUSDm"),
            SimpleNamespace(name="XAUUSDz"),
        ]
        client = MT5Client(Settings(), mt5_module=mock_mt5_module)
        matches = find_matching_symbols(client, "XAUUSD")
        assert "XAUUSDm" in matches
        assert "XAUUSDz" in matches


class TestSerializerAndLoader:
    def test_csv_serialization_and_loader_compat(self, tmp_path: Path) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        rates = make_rates_array(start=start, bars=5)
        csv_path = tmp_path / "XAUUSD_M15.csv"
        write_history_csv(csv_path, rates)

        text = csv_path.read_text(encoding="utf-8")
        assert "tick_volume,spread,real_volume" in text
        assert "+00:00" in text

        candles = load_candles_from_csv(csv_path, symbol="XAUUSD", timeframe=Timeframe.M15)
        assert len(candles) == 5
        assert candles[0].volume == 100.0
        assert candles[0].spread == 20
        assert candles[0].timestamp.tzinfo is not None


class TestValidation:
    def test_weekend_gap_is_normal(self) -> None:
        prev = datetime(2024, 1, 5, 22, 0, tzinfo=UTC)
        curr = datetime(2024, 1, 8, 1, 0, tzinfo=UTC)
        assert classify_gap(prev, curr, curr - prev) == GapKind.NORMAL_SESSION

    def test_weekday_long_gap_is_unexpected(self) -> None:
        prev = datetime(2024, 1, 3, 10, 0, tzinfo=UTC)
        curr = datetime(2024, 1, 3, 20, 0, tzinfo=UTC)
        assert classify_gap(prev, curr, curr - prev) == GapKind.UNEXPECTED

    def test_validate_exported_rates(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        rates = make_rates_array(start=start, bars=10, spread=15)
        report = validate_exported_rates(rates, timeframe=Timeframe.M15)
        assert report.candle_count == 10
        assert report.duplicate_count == 0
        assert report.ohlc_valid is True
        assert report.timezone == "UTC"
        assert report.spread is not None
        assert report.spread.minimum == 15
        assert report.spread.maximum == 15


class TestFetcher:
    def test_fetch_historical_rates(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)
        mock_mt5_module.copy_rates_range_value = make_rates_array(start=start, bars=20)
        client = MT5Client(default_settings, mt5_module=mock_mt5_module)
        client.ensure_symbol_selected = lambda _symbol: None  # type: ignore[method-assign]

        rates = fetch_historical_rates(
            client,
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            start=start,
            end=end,
        )
        assert len(rates) == 20

    def test_empty_result_raises(
        self,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        mock_mt5_module.copy_rates_value = None
        mock_mt5_module.copy_rates_range_value = None
        client = MT5Client(default_settings, mt5_module=mock_mt5_module)
        client.ensure_symbol_selected = lambda _symbol: None  # type: ignore[method-assign]

        with pytest.raises(EmptyHistoryError):
            fetch_historical_rates(
                client,
                symbol="XAUUSD",
                timeframe=Timeframe.M15,
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 2, tzinfo=UTC),
            )


class TestExporterIntegration:
    def test_export_writes_csv_and_reports(
        self,
        tmp_path: Path,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        start = datetime(2023, 1, 1, tzinfo=UTC)
        mock_mt5_module.copy_rates_range_value = make_rates_array(start=start, bars=50)
        mock_mt5_module.terminal_info_value = SimpleNamespace(connected=True)

        config = build_export_config(
            symbol="XAUUSD",
            timeframe="M15",
            start="2023-01-01",
            end="2023-02-01",
            output=str(tmp_path / "custom.csv"),
        )
        client = MT5Client(default_settings, mt5_module=mock_mt5_module)
        exporter = HistoricalExporter(default_settings, client=client)
        result = exporter.export(config)

        assert result.output_path.exists()
        assert result.validation.candle_count == 50
        assert result.broker_symbol == "XAUUSD"

    def test_exporter_never_calls_order_send(
        self,
        tmp_path: Path,
        default_settings: Settings,
        mock_mt5_module: MockMT5Module,
    ) -> None:
        start = datetime(2023, 1, 1, tzinfo=UTC)
        mock_mt5_module.copy_rates_range_value = make_rates_array(start=start, bars=3)
        mock_mt5_module.terminal_info_value = SimpleNamespace(connected=True)

        def fail_order_send(_request: object) -> None:
            msg = "order_send must not be called"
            raise AssertionError(msg)

        mock_mt5_module.order_send = fail_order_send  # type: ignore[method-assign]

        config = build_export_config(
            symbol="XAUUSD",
            timeframe="M15",
            start="2023-01-01",
            end="2023-02-01",
            output=str(tmp_path / "out.csv"),
        )
        client = MT5Client(default_settings, mt5_module=mock_mt5_module)
        exporter = HistoricalExporter(default_settings, client=client)
        exporter.export(config)
