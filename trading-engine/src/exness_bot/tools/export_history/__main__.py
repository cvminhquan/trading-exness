"""CLI for historical data export."""

from __future__ import annotations

import argparse
import sys

import structlog

from exness_bot.broker.mt5.exceptions import BrokerError
from exness_bot.config.settings import get_settings
from exness_bot.logging.setup import configure_logging
from exness_bot.tools.export_history.config import build_export_config
from exness_bot.tools.export_history.exporter import HistoricalExporter, render_validation_report
from exness_bot.tools.export_history.fetcher import EmptyHistoryError
from exness_bot.tools.export_history.symbol_resolver import SymbolResolutionError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_history",
        description="Export historical OHLCV data from MT5 (read-only, no orders)",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Symbol to export (default: HISTORICAL_SYMBOL or SYMBOL setting)",
    )
    parser.add_argument(
        "--timeframe",
        default=None,
        help="Timeframe enum value, e.g. M15 (default: TIMEFRAME setting)",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Start date YYYY-MM-DD (required unless HISTORICAL_START is set)",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="End date YYYY-MM-DD (required unless HISTORICAL_END is set)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path (default: data/historical/{symbol}_{timeframe}.csv)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = structlog.get_logger(__name__)
    args = build_parser().parse_args(argv)

    try:
        config = build_export_config(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start=args.start,
            end=args.end,
            output=args.output,
            settings=get_settings(),
        )
    except ValueError as exc:
        logger.error("export_config_invalid", error=str(exc))
        print(str(exc), file=sys.stderr)
        return 2

    try:
        result = HistoricalExporter(get_settings()).export(config)
    except SymbolResolutionError as exc:
        logger.error("symbol_resolution_failed", requested=exc.requested)
        print(str(exc), file=sys.stderr)
        return 3
    except EmptyHistoryError as exc:
        logger.error("empty_history", error=str(exc))
        print(str(exc), file=sys.stderr)
        return 4
    except BrokerError as exc:
        logger.error("mt5_export_failed", error=str(exc))
        print(str(exc), file=sys.stderr)
        return 5

    print(render_validation_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
