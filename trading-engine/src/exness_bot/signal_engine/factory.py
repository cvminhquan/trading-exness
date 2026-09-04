"""Build SignalEngine from settings — read-only data provider only."""

from __future__ import annotations

from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.candle_engine.factory import parse_candle_timeframe
from exness_bot.config.settings import Settings
from exness_bot.data.provider import TradingDataProvider
from exness_bot.domain.clock import Clock
from exness_bot.signal_engine.engine import SignalEngine
from exness_bot.signal_engine.state import FileSignalStateStore, SignalStateStore
from exness_bot.strategy.ema_rsi_atr import EmaRsiAtrStrategy

ENGINE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_PATH = ENGINE_ROOT / ".signal_engine_state.json"


def build_signal_engine(
    settings: Settings,
    provider: TradingDataProvider | None = None,
    *,
    store: SignalStateStore | None = None,
    clock: Clock | None = None,
    state_path: Path | None = None,
) -> SignalEngine:
    symbol = settings.resolved_candle_symbol
    timeframe = parse_candle_timeframe(settings.candle_timeframe)
    warmup_bars = BacktestConfig.from_settings(settings).warmup_bars
    strategy = EmaRsiAtrStrategy(settings)
    resolved_store = store or FileSignalStateStore(
        state_path or DEFAULT_STATE_PATH,
        symbol=symbol,
        timeframe=timeframe.value,
        strategy=strategy.name,
    )
    source = provider.data_source.value.upper() if provider is not None else "MOCK"
    return SignalEngine(
        resolved_store,
        strategy,
        symbol=symbol,
        timeframe=timeframe,
        warmup_bars=warmup_bars,
        clock=clock,
        source=source,
        provider=provider,
        history_count=settings.candle_history_count,
        rsi_long_min=settings.rsi_long_min,
        rsi_long_max=settings.rsi_long_max,
    )
