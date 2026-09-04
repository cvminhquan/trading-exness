"""Polling loop and process signals for the live candle engine."""

from __future__ import annotations

import signal
import threading

import structlog

from exness_bot.candle_engine.engine import CandleEngine

logger = structlog.get_logger(__name__)


def run_polling_loop(
    engine: CandleEngine,
    interval_seconds: float,
    *,
    stop_event: threading.Event | None = None,
) -> None:
    """Poll until stop_event is set. SIGINT/SIGTERM request a clean stop on the main thread."""
    stop = stop_event or threading.Event()
    interval = max(0.05, float(interval_seconds))

    def handle_signal(_signum: int, _frame: object) -> None:
        logger.info("candle_engine_shutdown_signal")
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    logger.info(
        "candle_engine_started",
        symbol=engine.symbol,
        timeframe=engine.timeframe.value,
        interval_seconds=interval,
    )
    try:
        while not stop.is_set():
            engine.poll()
            if stop.wait(interval):
                break
    finally:
        logger.info("candle_engine_stopped")
