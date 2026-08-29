"""Tests for the autonomous trading engine."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import OrderType, SignalAction, SignalDirection, Timeframe
from exness_bot.domain.models import (
    AccountInfo,
    ApprovedOrderPlan,
    IndicatorSnapshot,
    OrderRequest,
    OrderResult,
    Signal,
    SymbolInfo,
)
from exness_bot.engine.models import CycleStatus, PauseReason
from exness_bot.engine.trading_engine import TradingEngine
from exness_bot.persistence.sqlite_repository import SQLiteTradingRepository
from tests.fixtures.ohlc_data import make_uptrend_ohlc


def _make_bars_with_closed_candle(*, now: datetime) -> pd.DataFrame:
    """Build enough M15 bars so the penultimate candle is the latest closed one."""
    start = now - timedelta(minutes=15 * 260)
    timestamps = [start + timedelta(minutes=15 * i) for i in range(260)]
    ohlc = make_uptrend_ohlc(length=260, start=100.0)
    ohlc["timestamp"] = timestamps
    return ohlc


def _make_buy_signal() -> Signal:
    indicators = IndicatorSnapshot(
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ema_20=110.0,
        ema_50=105.0,
        ema_200=100.0,
        rsi_14=60.0,
        atr_14=2.0,
    )
    return Signal.create(
        action=SignalAction.BUY,
        strategy_name="ema_rsi_atr_v1",
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        entry_price=2350.0,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        indicators=indicators,
        reason="test buy",
    )


def _make_plan() -> ApprovedOrderPlan:
    signal = _make_buy_signal()
    order_request = OrderRequest(
        symbol="XAUUSD",
        volume=0.01,
        order_type=OrderType.MARKET,
        direction=SignalDirection.LONG,
        stop_loss=2338.0,
        take_profit=2374.0,
    )
    return ApprovedOrderPlan(
        signal=signal,
        volume=0.01,
        stop_loss=2338.0,
        take_profit=2374.0,
        order_request=order_request,
    )


def _make_account() -> AccountInfo:
    return AccountInfo(
        login=1,
        balance=10_000.0,
        equity=10_000.0,
        margin=0.0,
        free_margin=10_000.0,
        leverage=500,
        trade_mode="demo",
    )


def _make_symbol() -> SymbolInfo:
    return SymbolInfo(
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


def _build_engine(
    *,
    settings: Settings | None = None,
    repository: SQLiteTradingRepository | None = None,
) -> tuple[TradingEngine, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    settings = settings or Settings(TRADING_MODE="dry_run", DRY_RUN=True)
    broker = MagicMock()
    broker.is_connected.return_value = True
    broker.get_account_info.return_value = _make_account()
    broker.get_symbol_info.return_value = _make_symbol()
    broker.get_open_positions.return_value = []

    market_data = MagicMock()
    strategy = MagicMock()
    strategy.name = "ema_rsi_atr_v1"
    strategy.evaluate.return_value = Signal.create(
        action=SignalAction.HOLD,
        strategy_name="ema_rsi_atr_v1",
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        entry_price=2350.0,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        indicators=IndicatorSnapshot(timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)),
        reason="HOLD",
    )

    risk_manager = MagicMock()
    from exness_bot.domain.models import RejectedSignal

    risk_manager.assess.return_value = RejectedSignal(
        signal=strategy.evaluate.return_value,
        reason="HOLD signal — no action",
    )

    order_manager = MagicMock()
    order_manager.reconcile_positions.return_value = []

    repo = repository or SQLiteTradingRepository(":memory:")

    engine = TradingEngine(
        settings=settings,
        broker=broker,
        market_data=market_data,
        strategy=strategy,
        risk_manager=risk_manager,
        order_manager=order_manager,
        repository=repo,
    )
    return engine, broker, market_data, strategy, risk_manager, order_manager


class TestTradingEngine:
    def test_skips_when_no_closed_candle(self) -> None:
        engine, _, market_data, *_ = _build_engine()
        now = datetime(2026, 6, 1, 10, 5, tzinfo=UTC)
        bars = _make_bars_with_closed_candle(now=now)
        market_data.get_latest_bars.return_value = bars

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "exness_bot.engine.trading_engine.get_latest_closed_candle",
                lambda _bars, _tf, now=None: None,
            )
            result = engine.tick()

        assert result.status == CycleStatus.SKIPPED
        assert "No closed candle" in result.message

    def test_skips_already_processed_candle(self) -> None:
        now = datetime(2026, 6, 1, 12, 45, tzinfo=UTC)
        bars = _make_bars_with_closed_candle(now=now)
        repo = SQLiteTradingRepository(":memory:")
        closed_ts = bars.iloc[-2]["timestamp"]
        repo.try_claim_candle("XAUUSD", "M15", closed_ts)

        engine, _, market_data, *_ = _build_engine(repository=repo)
        market_data.get_latest_bars.return_value = bars

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "exness_bot.engine.trading_engine.get_latest_closed_candle",
                lambda _bars, _tf, now=None: _bars.iloc[-2],
            )
            result = engine.tick()

        assert result.status == CycleStatus.SKIPPED
        assert result.message == "Candle already processed"

    def test_completes_cycle_and_is_idempotent(self) -> None:
        now = datetime(2026, 6, 1, 12, 45, tzinfo=UTC)
        bars = _make_bars_with_closed_candle(now=now)
        engine, _, market_data, *_ = _build_engine()
        market_data.get_latest_bars.return_value = bars

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "exness_bot.engine.trading_engine.get_latest_closed_candle",
                lambda _bars, _tf, now=None: _bars.iloc[-2],
            )
            first = engine.tick()
            second = engine.tick()

        assert first.status == CycleStatus.COMPLETED
        assert second.status == CycleStatus.SKIPPED

    def test_pauses_on_mt5_disconnect(self) -> None:
        engine, broker, market_data, *_ = _build_engine()
        broker.is_connected.return_value = False
        market_data.get_latest_bars.return_value = _make_bars_with_closed_candle(
            now=datetime(2026, 6, 1, 12, 45, tzinfo=UTC)
        )

        result = engine.tick()
        assert result.status == CycleStatus.PAUSED
        assert result.pause_reason == PauseReason.MT5_DISCONNECTED
        assert engine.is_paused is True

    def test_executes_approved_order_in_dry_run(self) -> None:
        now = datetime(2026, 6, 1, 12, 45, tzinfo=UTC)
        bars = _make_bars_with_closed_candle(now=now)
        engine, _, market_data, _, risk_manager, order_manager = _build_engine()
        market_data.get_latest_bars.return_value = bars
        risk_manager.assess.return_value = _make_plan()
        order_manager.open_market_order.return_value = OrderResult(
            success=True,
            dry_run=True,
            volume=0.01,
            timestamp=datetime(2026, 6, 1, 12, 45, tzinfo=UTC),
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "exness_bot.engine.trading_engine.get_latest_closed_candle",
                lambda _bars, _tf, now=None: _bars.iloc[-2],
            )
            result = engine.tick()

        assert result.status == CycleStatus.COMPLETED
        order_manager.open_market_order.assert_called_once()

    def test_pauses_on_execution_failure(self) -> None:
        now = datetime(2026, 6, 1, 12, 45, tzinfo=UTC)
        bars = _make_bars_with_closed_candle(now=now)
        engine, _, market_data, _, risk_manager, order_manager = _build_engine(
            settings=Settings(TRADING_MODE="demo", DRY_RUN=False),
        )
        market_data.get_latest_bars.return_value = bars
        risk_manager.assess.return_value = _make_plan()
        order_manager.open_market_order.return_value = OrderResult(
            success=False,
            error_message="Rejected by broker",
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "exness_bot.engine.trading_engine.get_latest_closed_candle",
                lambda _bars, _tf, now=None: _bars.iloc[-2],
            )
            result = engine.tick()

        assert result.status == CycleStatus.PAUSED
        assert result.pause_reason == PauseReason.EXECUTION_ERROR
