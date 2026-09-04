"""Optional API background loop for Signal Engine (includes candle poll)."""

from __future__ import annotations

import threading

import structlog

from exness_bot.api.services.read_service import ReadService
from exness_bot.candle_engine.factory import build_candle_engine
from exness_bot.config.settings import Settings
from exness_bot.signal_engine.engine import SignalEngine
from exness_bot.signal_engine.factory import build_signal_engine
from exness_bot.signal_engine.loop import run_signal_polling_loop

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_engine: SignalEngine | None = None
_stop: threading.Event | None = None
_thread: threading.Thread | None = None


def get_api_signal_engine() -> SignalEngine | None:
    return _engine


def start_signal_engine_runtime(settings: Settings, service: ReadService) -> None:
    if not settings.signal_engine_enabled:
        return
    global _engine, _stop, _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        candle_engine = build_candle_engine(settings, service.provider)
        signal_engine = build_signal_engine(settings, service.provider)
        service.attach_candle_engine(candle_engine)
        service.attach_signal_engine(signal_engine)
        stop = threading.Event()
        thread = threading.Thread(
            target=run_signal_polling_loop,
            args=(candle_engine, signal_engine, float(settings.candle_poll_interval_seconds)),
            kwargs={"stop_event": stop},
            daemon=True,
            name="signal-engine",
        )
        _engine = signal_engine
        _stop = stop
        _thread = thread
        thread.start()
        logger.info("signal_engine_runtime_started")


def stop_signal_engine_runtime() -> None:
    global _engine, _stop, _thread
    with _lock:
        stop = _stop
        thread = _thread
        _stop = None
        _thread = None
        _engine = None
    if stop is not None:
        stop.set()
    if thread is not None:
        thread.join(timeout=5)
    logger.info("signal_engine_runtime_stopped")
