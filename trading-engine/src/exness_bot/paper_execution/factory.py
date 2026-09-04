"""Build ExecutionService from settings. No broker trading client."""

from __future__ import annotations

from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.live_enablement import assert_live_execution_not_operational
from exness_bot.config.settings import Settings
from exness_bot.data.provider import TradingDataProvider
from exness_bot.domain.clock import Clock
from exness_bot.domain.models import SymbolInfo
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.paper_execution.state import FilePaperStateStore, PaperStateStore
from exness_bot.risk.manager import RiskManager

ENGINE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_PATH = ENGINE_ROOT / ".paper_execution_state.json"


def build_execution_service(
    settings: Settings,
    *,
    store: PaperStateStore | None = None,
    symbol_info: SymbolInfo | None = None,
    clock: Clock | None = None,
    state_path: Path | None = None,
    provider: TradingDataProvider | None = None,
) -> ExecutionService:
    """
    Default composition: Paper ExecutionPort only.

    Phase 12.8 GatedMT5ExecutionPort is NEVER wired here.
    Use exness_bot.execution.mt5.factory.build_gated_mt5_execution_port explicitly.
    """
    assert_live_execution_not_operational(settings)
    config = BacktestConfig.from_settings(settings)
    resolved_store = store or FilePaperStateStore(state_path or DEFAULT_STATE_PATH)
    resolved_symbol = symbol_info or _symbol_from_provider(config, provider)
    return ExecutionService(
        risk_manager=RiskManager(settings),
        store=resolved_store,
        settings=settings,
        config=config,
        symbol_info=resolved_symbol,
        clock=clock,
    )


def refresh_execution_quote(
    service: ExecutionService,
    settings: Settings,
    provider: TradingDataProvider,
) -> None:
    tick = provider.get_tick(settings.resolved_candle_symbol)
    if tick is None:
        return
    service.update_quote_from_tick(tick, BacktestConfig.from_settings(settings))


def _symbol_from_provider(
    config: BacktestConfig,
    provider: TradingDataProvider | None,
) -> SymbolInfo:
    fallback = config.to_symbol_info(close_price=2350.0)
    if provider is None:
        return fallback
    tick = provider.get_tick(config.symbol)
    if tick is None or tick.bid <= 0 or tick.ask <= 0:
        return fallback
    spread = fallback.spread
    if config.point > 0:
        spread = max(1, round((tick.ask - tick.bid) / config.point))
    return fallback.model_copy(
        update={
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": spread,
            "stops_level": config.paper_stops_level,
            "freeze_level": config.paper_freeze_level,
        }
    )
