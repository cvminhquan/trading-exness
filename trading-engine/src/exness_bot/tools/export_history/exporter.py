"""Historical data export orchestration (read-only MT5 access)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy.typing as npt
import structlog

from exness_bot.broker.mt5.client import MT5Client
from exness_bot.broker.mt5.exceptions import MT5ConnectionError
from exness_bot.config.settings import Settings
from exness_bot.tools.export_history.config import ExportConfig, default_output_path
from exness_bot.tools.export_history.fetcher import fetch_historical_rates
from exness_bot.tools.export_history.models import ExportValidationReport
from exness_bot.tools.export_history.serializer import write_history_csv
from exness_bot.tools.export_history.symbol_resolver import resolve_broker_symbol
from exness_bot.tools.export_history.validation import validate_exported_rates

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ExportResult:
    """Outcome of a historical export run."""

    config: ExportConfig
    broker_symbol: str
    output_path: Path
    rates: npt.NDArray[Any]
    validation: ExportValidationReport


class HistoricalExporter:
    """
    Read-only MT5 historical data exporter.

    This class never calls order_send or modifies positions/account state.
    """

    def __init__(self, settings: Settings, *, client: MT5Client | None = None) -> None:
        self._settings = settings
        self._client = client or MT5Client(settings)

    def connect(self) -> None:
        """Initialize and authenticate with MT5."""
        if not self._client.is_initialized:
            self._client.initialize()
        if not self._client.is_logged_in:
            self._client.login()

        terminal = self._client.terminal_info()
        if terminal is None or not getattr(terminal, "connected", False):
            msg = "MT5 terminal is not connected. Open MetaTrader 5 and sign in first."
            raise MT5ConnectionError(msg)

    def disconnect(self) -> None:
        """Shutdown MT5 connection."""
        self._client.shutdown()

    def export(self, config: ExportConfig) -> ExportResult:
        """Export historical rates to CSV and return validation report."""
        self.connect()
        try:
            broker_symbol = resolve_broker_symbol(self._client, config.symbol)
            rates = fetch_historical_rates(
                self._client,
                symbol=broker_symbol,
                timeframe=config.timeframe,
                start=config.start,
                end=config.end,
            )
            output_path = config.output or default_output_path(
                broker_symbol,
                config.timeframe,
            )

            write_history_csv(output_path, rates)
            validation = validate_exported_rates(rates, timeframe=config.timeframe)

            logger.info(
                "history_export_complete",
                broker_symbol=broker_symbol,
                candles=validation.candle_count,
                output=str(output_path),
            )
            return ExportResult(
                config=config,
                broker_symbol=broker_symbol,
                output_path=output_path,
                rates=rates,
                validation=validation,
            )
        finally:
            self.disconnect()


def render_validation_report(result: ExportResult) -> str:
    """Render human-readable validation summary."""
    v = result.validation
    lines = [
        f"Exported: {result.output_path}",
        f"Broker symbol: {result.broker_symbol}",
        f"Candles: {v.candle_count}",
        f"First timestamp: {v.first_timestamp}",
        f"Last timestamp: {v.last_timestamp}",
        f"Duplicates: {v.duplicate_count}",
        f"Normal session gaps: {v.normal_session_gaps}",
        f"Unexpected gaps: {v.unexpected_gaps}",
        f"Missing bars (est.): {v.missing_bars_total}",
        f"OHLC valid: {v.ohlc_valid}",
        f"Timezone: {v.timezone}",
    ]
    if v.spread is not None:
        lines.extend(
            [
                f"Spread min/avg/max: {v.spread.minimum} / {v.spread.average} / {v.spread.maximum}",
                f"Spread samples: {v.spread.samples}",
            ]
        )
    else:
        lines.append("Spread: not available in export")
    return "\n".join(lines)
