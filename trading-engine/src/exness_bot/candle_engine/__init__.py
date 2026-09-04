"""Live candle engine package."""

from exness_bot.candle_engine.engine import CandleEngine
from exness_bot.candle_engine.events import (
    CandlePollResult,
    CandlePollStatus,
    ClosedCandleEvent,
    candle_idempotency_key,
)
from exness_bot.candle_engine.factory import build_candle_engine
from exness_bot.candle_engine.loop import run_polling_loop
from exness_bot.candle_engine.state import (
    CandleCursor,
    FileCandleStateStore,
    InMemoryCandleStateStore,
)

__all__ = [
    "CandleCursor",
    "CandleEngine",
    "CandlePollResult",
    "CandlePollStatus",
    "ClosedCandleEvent",
    "FileCandleStateStore",
    "InMemoryCandleStateStore",
    "build_candle_engine",
    "candle_idempotency_key",
    "run_polling_loop",
]
