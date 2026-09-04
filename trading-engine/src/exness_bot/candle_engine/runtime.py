"""Process-wide candle engine for the read-only API (optional background poll)."""

from __future__ import annotations

import threading

import structlog

from exness_bot.api.services.read_service import ReadService
from exness_bot.candle_engine.engine import CandleEngine
from exness_bot.candle_engine.factory import build_candle_engine
from exness_bot.candle_engine.loop import run_polling_loop
from exness_bot.config.settings import Settings

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_engine: CandleEngine | None = None
_stop: threading.Event | None = None
_thread: threading.Thread | None = None


def get_api_candle_engine() -> CandleEngine | None:
    return _engine


def start_candle_engine_runtime(settings: Settings, service: ReadService) -> None:
    """Start polling in a daemon thread. No-op when CANDLE_ENGINE_ENABLED is false."""
    global _engine, _stop, _thread
    if not settings.candle_engine_enabled:
        return
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        engine = build_candle_engine(settings, service.provider)
        service.attach_candle_engine(engine)
        stop = threading.Event()
        thread = threading.Thread(
            target=run_polling_loop,
            args=(engine, float(settings.candle_poll_interval_seconds)),
            kwargs={"stop_event": stop},
            daemon=True,
            name="candle-engine",
        )
        _engine = engine
        _stop = stop
        _thread = thread
        thread.start()
        logger.info("candle_engine_runtime_started")


def stop_candle_engine_runtime() -> None:
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
    logger.info("candle_engine_runtime_stopped")
