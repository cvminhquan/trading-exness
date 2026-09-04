"""Polling loop: CandleEngine events → SignalEngine. No orders."""

from __future__ import annotations

import signal
import threading

import structlog

from exness_bot.candle_engine.engine import CandleEngine
from exness_bot.signal_engine.engine import SignalEngine

logger = structlog.get_logger(__name__)


def run_signal_polling_loop(
    candle_engine: CandleEngine,
    signal_engine: SignalEngine,
    interval_seconds: float,
    *,
    stop_event: threading.Event | None = None,
) -> None:
    stop = stop_event or threading.Event()
    interval = max(0.05, float(interval_seconds))

    def handle_signal(_signum: int, _frame: object) -> None:
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    logger.info(
        "signal_engine_started",
        strategy=signal_engine.strategy_name,
        interval_seconds=interval,
    )
    signal_engine.warmup_from_provider()
    try:
        while not stop.is_set():
            poll = candle_engine.poll()
            if poll.events:
                signal_engine.process_events(poll.events)
            if stop.wait(interval):
                break
    finally:
        logger.info("signal_engine_stopped")
