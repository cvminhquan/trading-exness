"""Optional API background loop for paper execution (candle + signal + paper)."""

from __future__ import annotations

import threading

import structlog

from exness_bot.api.services.read_service import ReadService
from exness_bot.candle_engine.factory import build_candle_engine
from exness_bot.config.settings import Settings
from exness_bot.paper_execution.factory import (
    build_execution_service,
    refresh_execution_quote,
)
from exness_bot.paper_execution.loop import run_paper_polling_loop
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.signal_engine.factory import build_signal_engine

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_execution: ExecutionService | None = None
_stop: threading.Event | None = None
_thread: threading.Thread | None = None


def get_api_paper_execution() -> ExecutionService | None:
    return _execution


def start_paper_execution_runtime(settings: Settings, service: ReadService) -> None:
    if not settings.paper_execution_enabled:
        return
    global _execution, _stop, _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        candle_engine = build_candle_engine(settings, service.provider)
        signal_engine = build_signal_engine(settings, service.provider)
        execution = build_execution_service(settings, provider=service.provider)
        service.attach_candle_engine(candle_engine)
        service.attach_signal_engine(signal_engine)
        service.attach_paper_execution(execution)
        stop = threading.Event()

        def refresh() -> None:
            refresh_execution_quote(execution, settings, service.provider)

        thread = threading.Thread(
            target=run_paper_polling_loop,
            args=(
                candle_engine,
                signal_engine,
                execution,
                float(settings.candle_poll_interval_seconds),
            ),
            kwargs={"stop_event": stop, "refresh_quote": refresh},
            daemon=True,
            name="paper-execution",
        )
        _execution = execution
        _stop = stop
        _thread = thread
        thread.start()
        logger.info("paper_execution_runtime_started")


def stop_paper_execution_runtime() -> None:
    global _execution, _stop, _thread
    with _lock:
        stop = _stop
        thread = _thread
        _stop = None
        _thread = None
        _execution = None
    if stop is not None:
        stop.set()
    if thread is not None:
        thread.join(timeout=5)
    logger.info("paper_execution_runtime_stopped")
