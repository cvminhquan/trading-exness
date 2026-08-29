"""Trading engine factory."""

from __future__ import annotations

from exness_bot.broker.execution import ExecutableBroker
from exness_bot.config.settings import Settings
from exness_bot.engine.trading_engine import TradingEngine
from exness_bot.market_data.mt5_provider import MT5MarketDataProvider
from exness_bot.orders.manager import OrderManager
from exness_bot.persistence.factory import create_trading_repository
from exness_bot.persistence.repository import TradingRepository
from exness_bot.risk.manager import RiskManager
from exness_bot.strategy.ema_rsi_atr import EmaRsiAtrStrategy


def create_trading_engine(
    settings: Settings,
    broker: ExecutableBroker,
    *,
    repository: TradingRepository | None = None,
) -> TradingEngine:
    """Wire dependencies for the autonomous trading engine."""
    repo = repository or create_trading_repository(settings)
    market_data = MT5MarketDataProvider(broker, default_count=settings.candle_history_count)
    strategy = EmaRsiAtrStrategy(settings)
    risk_manager = RiskManager(settings)
    order_manager = OrderManager(broker, settings)

    return TradingEngine(
        settings=settings,
        broker=broker,
        market_data=market_data,
        strategy=strategy,
        risk_manager=risk_manager,
        order_manager=order_manager,
        repository=repo,
    )
