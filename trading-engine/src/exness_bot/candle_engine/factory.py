"""Build a live candle engine from settings — no strategy, no orders."""

from __future__ import annotations

from pathlib import Path

from exness_bot.candle_engine.engine import CandleEngine
from exness_bot.candle_engine.state import CandleStateStore, FileCandleStateStore
from exness_bot.config.settings import Settings
from exness_bot.data.provider import TradingDataProvider
from exness_bot.domain.clock import Clock
from exness_bot.domain.enums import Timeframe

ENGINE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_PATH = ENGINE_ROOT / ".candle_engine_state.json"


def parse_candle_timeframe(value: str) -> Timeframe:
    normalized = value.strip().upper()
    try:
        return Timeframe(normalized)
    except ValueError as exc:
        msg = f"Unsupported CANDLE_TIMEFRAME: {value}"
        raise ValueError(msg) from exc


def build_candle_engine(
    settings: Settings,
    provider: TradingDataProvider,
    *,
    store: CandleStateStore | None = None,
    clock: Clock | None = None,
    state_path: Path | None = None,
) -> CandleEngine:
    """Create a CandleEngine using canonical symbol; broker suffixes stay in the provider."""
    symbol = settings.resolved_candle_symbol
    timeframe = parse_candle_timeframe(settings.candle_timeframe)
    resolved_store = store or FileCandleStateStore(
        state_path or DEFAULT_STATE_PATH,
        symbol=symbol,
        timeframe=timeframe.value,
    )
    return CandleEngine(
        provider,
        resolved_store,
        symbol=symbol,
        timeframe=timeframe,
        history_count=settings.candle_history_count,
        clock=clock,
        source=provider.data_source.value.upper(),
    )
