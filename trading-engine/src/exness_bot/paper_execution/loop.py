"""Polling loop: closed candle → exit check → signal → paper consume."""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable, Sequence

import structlog

from exness_bot.candle_engine.engine import CandleEngine
from exness_bot.candle_engine.events import ClosedCandleEvent
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.signal_engine.engine import SignalEngine

logger = structlog.get_logger(__name__)

QuoteRefresh = Callable[[], None]


def run_paper_polling_loop(
    candle_engine: CandleEngine,
    signal_engine: SignalEngine,
    execution: ExecutionService,
    interval_seconds: float,
    *,
    stop_event: threading.Event | None = None,
    refresh_quote: QuoteRefresh | None = None,
) -> None:
    stop = stop_event or threading.Event()
    interval = max(0.05, float(interval_seconds))

    def handle_signal(_signum: int, _frame: object) -> None:
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    logger.info("paper_execution_started", mode="paper")
    signal_engine.warmup_from_provider()
    try:
        while not stop.is_set():
            if refresh_quote is not None:
                refresh_quote()
            poll = candle_engine.poll()
            if poll.events:
                process_closed_candles(poll.events, signal_engine, execution)
            if stop.wait(interval):
                break
    finally:
        logger.info("paper_execution_stopped")


def process_closed_candles(
    events: Sequence[ClosedCandleEvent],
    signal_engine: SignalEngine,
    execution: ExecutionService,
) -> None:
    for event in events:
        execution.on_closed_candle(event.candle)
    processed = signal_engine.process_events(tuple(events))
    execution.consume_results(processed.results)
