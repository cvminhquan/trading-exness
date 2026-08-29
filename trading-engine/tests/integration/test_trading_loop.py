"""Integration tests for the trading loop."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalAction, Timeframe
from exness_bot.domain.models import IndicatorSnapshot, Signal
from exness_bot.engine.factory import create_trading_engine
from exness_bot.engine.models import CycleStatus
from exness_bot.persistence.sqlite_repository import SQLiteTradingRepository
from tests.fixtures.ohlc_data import make_uptrend_ohlc

pytestmark = pytest.mark.integration


def _bars(now: datetime) -> pd.DataFrame:
    start = now - timedelta(minutes=15 * 260)
    timestamps = [start + timedelta(minutes=15 * i) for i in range(260)]
    frame = make_uptrend_ohlc(length=260)
    frame["timestamp"] = timestamps
    return frame


@pytest.fixture
def in_memory_repo() -> SQLiteTradingRepository:
    return SQLiteTradingRepository(":memory:")


def test_end_to_end_hold_cycle(in_memory_repo: SQLiteTradingRepository) -> None:
    settings = Settings(TRADING_MODE="dry_run", DRY_RUN=True)
    broker = MagicMock()
    broker.is_connected.return_value = True
    broker.get_account_info.return_value = MagicMock(
        login=1,
        balance=10_000.0,
        equity=10_000.0,
        margin=0.0,
        free_margin=10_000.0,
        leverage=500,
        trade_mode="demo",
    )
    broker.get_symbol_info.return_value = MagicMock(
        symbol="XAUUSD",
        bid=2350.10,
        ask=2350.30,
        point=0.01,
        digits=2,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        trade_contract_size=100.0,
        spread=20,
        trade_mode=4,
        visible=True,
    )
    broker.get_open_positions.return_value = []
    broker.get_historical_candles.return_value = []

    now = datetime(2026, 6, 1, 12, 45, tzinfo=UTC)
    bars_df = _bars(now)

    class FakeMarketData:
        def get_latest_bars(self, symbol: str, timeframe: Timeframe, count: int) -> pd.DataFrame:
            return bars_df

    class FakeStrategy:
        name = "ema_rsi_atr_v1"

        def evaluate(
            self,
            bars: pd.DataFrame,
            indicators: IndicatorSnapshot | None = None,
        ) -> Signal:
            return Signal.create(
                action=SignalAction.HOLD,
                strategy_name=self.name,
                symbol="XAUUSD",
                timeframe=Timeframe.M15,
                entry_price=float(bars.iloc[-1]["close"]),
                timestamp=bars.iloc[-1]["timestamp"],
                indicators=indicators or IndicatorSnapshot(timestamp=datetime.now(tz=UTC)),
                reason="integration hold",
            )

    engine = create_trading_engine(settings, broker, repository=in_memory_repo)
    engine._market_data = FakeMarketData()  # type: ignore[method-assign]
    engine._strategy = FakeStrategy()  # type: ignore[method-assign]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "exness_bot.engine.trading_engine.get_latest_closed_candle",
            lambda _bars, _tf, now=None: _bars.iloc[-2],
        )
        result = engine.tick()

    assert result.status == CycleStatus.COMPLETED
    assert result.signal is not None
    assert result.signal.action == SignalAction.HOLD
    assert in_memory_repo.is_candle_processed(
        "XAUUSD",
        "M15",
        bars_df.iloc[-2]["timestamp"],
    )
