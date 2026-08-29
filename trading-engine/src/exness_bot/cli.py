"""Command-line interface."""

from __future__ import annotations

import argparse
import signal
import sys
import time

import structlog

from exness_bot import __version__
from exness_bot.config.settings import get_settings
from exness_bot.engine.factory import create_trading_engine
from exness_bot.engine.models import CycleStatus
from exness_bot.logging.setup import configure_logging

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exness-bot",
        description="Exness algorithmic trading bot via MetaTrader 5",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    run_parser = subparsers.add_parser("run", help="Run the trading engine")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Force dry-run mode (log orders, do not submit)",
    )
    run_parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single trading cycle and exit",
    )

    subparsers.add_parser("status", help="Show current configuration and safety status")

    backtest_parser = subparsers.add_parser("backtest", help="Run strategy backtest")
    backtest_parser.add_argument("--file", required=True, help="Path to historical CSV data")
    backtest_parser.add_argument(
        "--json",
        dest="json_output",
        default=None,
        help="Write machine-readable JSON report to this path",
    )

    baseline_parser = subparsers.add_parser(
        "baseline",
        help="Run Phase 7.2 baseline backtest and write report artifacts",
    )
    baseline_parser.add_argument(
        "--file",
        default=None,
        help="Optional CSV path; defaults to best dataset under data/",
    )

    return parser


def handle_status() -> int:
    settings = get_settings()
    logger.info(
        "bot_status",
        version=__version__,
        trading_mode=settings.trading_mode.value,
        dry_run=settings.dry_run,
        is_dry_run_mode=settings.is_dry_run_mode,
        allow_live_trading=settings.allow_live_trading,
        is_live_trading_enabled=settings.is_live_trading_enabled,
        symbol=settings.symbol,
        timeframe=settings.timeframe,
    )
    return 0


def handle_run(dry_run: bool | None, once: bool) -> int:
    settings = get_settings()
    if dry_run is not None:
        object.__setattr__(settings, "dry_run", dry_run)

    try:
        from exness_bot.broker.mt5.adapter import MT5Adapter
    except ImportError:
        logger.error(
            "mt5_import_failed",
            message="MetaTrader5 package is not available on this platform",
        )
        return 1

    broker = MT5Adapter(settings)
    if not broker.connect():
        logger.error("mt5_connect_failed")
        return 1

    engine = create_trading_engine(settings, broker)
    engine.startup()

    shutdown_requested = False

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info("shutdown_signal_received")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    exit_code = 0
    try:
        if once:
            result = engine.tick()
            logger.info(
                "tick_complete",
                status=result.status.value,
                message=result.message,
                paused=result.paused,
            )
            if result.paused:
                exit_code = 1
        else:
            while not shutdown_requested:
                if engine.is_paused:
                    logger.error(
                        "engine_paused_stopping",
                        reason=engine.pause_reason.value if engine.pause_reason else None,
                    )
                    exit_code = 1
                    break

                result = engine.tick()
                logger.info("tick_complete", status=result.status.value, message=result.message)

                if result.status == CycleStatus.PAUSED:
                    exit_code = 1
                    break

                time.sleep(settings.loop_poll_seconds)
    finally:
        engine.shutdown()

    return exit_code


def handle_backtest(data_file: str, json_output: str | None) -> int:
    from exness_bot.backtest.runner import BacktestRunner

    settings = get_settings()
    runner = BacktestRunner(settings)
    try:
        runner.run(data_file, json_output=json_output)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("backtest_failed", error=str(exc))
        return 1
    return 0


def handle_baseline(data_file: str | None) -> int:
    from exness_bot.backtest.baseline_runner import (
        baseline_paths,
        run_baseline,
        write_baseline_outputs,
    )

    settings = get_settings()
    result = run_baseline(settings, data_path=data_file)
    write_baseline_outputs(result, baseline_paths())
    logger.info(
        "baseline_complete",
        status=result.status,
        classification=result.classification.classification.value,
    )
    return 0 if result.status in {"completed", "insufficient_data"} else 1


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "status":
        return handle_status()
    if args.command == "run":
        return handle_run(dry_run=args.dry_run, once=args.once)
    if args.command == "backtest":
        return handle_backtest(data_file=args.file, json_output=args.json_output)
    if args.command == "baseline":
        return handle_baseline(data_file=args.file)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
