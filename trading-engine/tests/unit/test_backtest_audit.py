"""Deterministic audit tests for the backtesting engine."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from exness_bot.backtest.config import BacktestConfig
from exness_bot.backtest.engine import BacktestEngine
from exness_bot.backtest.loader import load_candles_from_csv
from exness_bot.backtest.models import ExitReason, SimulatedPosition
from exness_bot.backtest.simulator import SAME_BAR_EXIT_RULE, VirtualExecutor
from exness_bot.backtest.validation import validate_candle_series
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import OrderType, SignalAction, SignalDirection, Timeframe
from exness_bot.domain.models import (
    ApprovedOrderPlan,
    Candle,
    IndicatorSnapshot,
    OrderRequest,
    Signal,
)
from exness_bot.risk.manager import RiskManager
from exness_bot.risk.models import RiskState
from exness_bot.risk.position_sizer import calculate_position_size
from tests.fixtures.backtest_csv import write_uptrend_csv
from tests.fixtures.risk_data import make_account, make_buy_signal, make_xauusd_symbol


def _candle(
    ts: datetime,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=ts,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _plan(*, direction: SignalDirection = SignalDirection.LONG) -> ApprovedOrderPlan:
    action = SignalAction.BUY if direction == SignalDirection.LONG else SignalAction.SELL
    sl = 2338.0 if direction == SignalDirection.LONG else 2362.0
    tp = 2374.0 if direction == SignalDirection.LONG else 2338.0
    signal = Signal.create(
        action=action,
        strategy_name="audit",
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        entry_price=2350.0,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        indicators=IndicatorSnapshot(
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            atr_14=2.0,
        ),
        reason="audit",
    )
    return ApprovedOrderPlan(
        signal=signal,
        volume=0.01,
        stop_loss=sl,
        take_profit=tp,
        order_request=OrderRequest(
            symbol="XAUUSD",
            volume=0.01,
            order_type=OrderType.MARKET,
            direction=direction,
            stop_loss=sl,
            take_profit=tp,
        ),
    )


def _executor(**kwargs: object) -> VirtualExecutor:
    return VirtualExecutor(BacktestConfig(spread_points=20, slippage_points=1.0, **kwargs))


class TestExecutionAudit:
    def test_buy_hits_take_profit(self) -> None:
        executor = _executor(commission_per_lot=0.0)
        entry_bar = 5
        position = executor.with_bar_index(
            executor.fill_entry(_plan(direction=SignalDirection.LONG), _candle(
                datetime(2026, 1, 1, tzinfo=UTC),
                open_price=2350.0,
                high=2352.0,
                low=2348.0,
                close=2350.0,
            )),
            entry_bar,
        )
        exit_event = executor.check_exit(
            position,
            _candle(
                datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
                open_price=2370.0,
                high=2375.0,
                low=2369.0,
                close=2374.0,
            ),
            bar_index=entry_bar + 1,
        )
        assert exit_event is not None
        assert exit_event.exit_reason == ExitReason.TAKE_PROFIT
        assert exit_event.exit_price == pytest.approx(2373.89, abs=0.001)

    def test_buy_hits_stop_loss(self) -> None:
        executor = _executor(commission_per_lot=0.0)
        entry_bar = 3
        position = executor.with_bar_index(
            executor.fill_entry(_plan(direction=SignalDirection.LONG), _candle(
                datetime(2026, 1, 1, tzinfo=UTC),
                open_price=2350.0,
                high=2352.0,
                low=2348.0,
                close=2350.0,
            )),
            entry_bar,
        )
        exit_event = executor.check_exit(
            position,
            _candle(
                datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
                open_price=2340.0,
                high=2341.0,
                low=2337.0,
                close=2339.0,
            ),
            bar_index=entry_bar + 1,
        )
        assert exit_event is not None
        assert exit_event.exit_reason == ExitReason.STOP_LOSS
        assert exit_event.exit_price == pytest.approx(2337.89, abs=0.001)

    def test_sell_hits_take_profit(self) -> None:
        executor = _executor(commission_per_lot=0.0)
        entry_bar = 2
        position = executor.with_bar_index(
            executor.fill_entry(_plan(direction=SignalDirection.SHORT), _candle(
                datetime(2026, 1, 1, tzinfo=UTC),
                open_price=2350.0,
                high=2352.0,
                low=2348.0,
                close=2350.0,
            )),
            entry_bar,
        )
        exit_event = executor.check_exit(
            position,
            _candle(
                datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
                open_price=2335.0,
                high=2337.0,
                low=2330.0,
                close=2332.0,
            ),
            bar_index=entry_bar + 1,
        )
        assert exit_event is not None
        assert exit_event.exit_reason == ExitReason.TAKE_PROFIT
        assert exit_event.exit_price == pytest.approx(2338.11, abs=0.001)

    def test_sell_hits_stop_loss(self) -> None:
        executor = _executor(commission_per_lot=0.0)
        entry_bar = 2
        position = executor.with_bar_index(
            executor.fill_entry(_plan(direction=SignalDirection.SHORT), _candle(
                datetime(2026, 1, 1, tzinfo=UTC),
                open_price=2350.0,
                high=2352.0,
                low=2348.0,
                close=2350.0,
            )),
            entry_bar,
        )
        exit_event = executor.check_exit(
            position,
            _candle(
                datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
                open_price=2360.0,
                high=2363.0,
                low=2359.0,
                close=2361.0,
            ),
            bar_index=entry_bar + 1,
        )
        assert exit_event is not None
        assert exit_event.exit_reason == ExitReason.STOP_LOSS
        assert exit_event.exit_price == pytest.approx(2362.11, abs=0.001)

    def test_same_bar_sl_tp_is_conservative(self) -> None:
        executor = _executor()
        position = executor.with_bar_index(
            executor.fill_entry(_plan(), _candle(
                datetime(2026, 1, 1, tzinfo=UTC),
                open_price=2350.0,
                high=2352.0,
                low=2348.0,
                close=2350.0,
            )),
            1,
        )
        exit_event = executor.check_exit(
            position,
            _candle(
                datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
                open_price=2350.0,
                high=2380.0,
                low=2330.0,
                close=2350.0,
            ),
            bar_index=2,
        )
        assert exit_event is not None
        assert exit_event.exit_reason == ExitReason.STOP_LOSS
        assert SAME_BAR_EXIT_RULE == "stop_loss_first"

    def test_no_exit_on_entry_bar(self) -> None:
        executor = _executor()
        position = executor.with_bar_index(
            executor.fill_entry(_plan(), _candle(
                datetime(2026, 1, 1, tzinfo=UTC),
                open_price=2350.0,
                high=2380.0,
                low=2330.0,
                close=2350.0,
            )),
            10,
        )
        assert executor.check_exit(position, _candle(
            datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
            open_price=2350.0,
            high=2380.0,
            low=2330.0,
            close=2350.0,
        ), bar_index=10) is None


class TestDataQualityAudit:
    def test_insufficient_data_rejected(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "short.csv", bars=100)
        candles = load_candles_from_csv(csv_path, symbol="XAUUSD", timeframe=Timeframe.M15)
        with pytest.raises(ValueError, match="Need more than"):
            validate_candle_series(candles, Timeframe.M15, warmup_bars=200)

    def test_duplicate_candle_rejected(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "dup.csv", bars=210)
        text = csv_path.read_text(encoding="utf-8")
        lines = text.strip().split("\n")
        lines.insert(2, lines[1])
        csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        candles = load_candles_from_csv(csv_path, symbol="XAUUSD", timeframe=Timeframe.M15)
        with pytest.raises(ValueError, match="Duplicate"):
            validate_candle_series(candles, Timeframe.M15, warmup_bars=200)

    def test_missing_candle_gap_rejected(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "gap.csv", bars=210)
        candles = load_candles_from_csv(csv_path, symbol="XAUUSD", timeframe=Timeframe.M15)
        gap_series = candles[:100] + candles[102:]
        with pytest.raises(ValueError, match="Missing candle gap"):
            validate_candle_series(gap_series, Timeframe.M15, warmup_bars=50)


class TestCostsAndSizingAudit:
    def test_position_sizing_uses_equity_not_hardcoded(self) -> None:
        symbol = make_xauusd_symbol()
        volume = calculate_position_size(
            equity=10_000.0,
            risk_pct=0.5,
            entry_price=2350.0,
            stop_loss=2338.0,
            symbol=symbol,
        )
        assert volume == 0.04

    def test_spread_applied_to_entry_and_exit(self) -> None:
        executor = VirtualExecutor(BacktestConfig(spread_points=20, slippage_points=0.0))
        position = executor.fill_entry(_plan(), _candle(
            datetime(2026, 1, 1, tzinfo=UTC),
            open_price=2350.0,
            high=2352.0,
            low=2348.0,
            close=2350.0,
        ))
        assert position.entry_price == 2350.10
        exit_event = executor.check_exit(
            executor.with_bar_index(position, 1),
            _candle(
                datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
                open_price=2370.0,
                high=2375.0,
                low=2369.0,
                close=2374.0,
            ),
            bar_index=2,
        )
        assert exit_event is not None
        assert exit_event.exit_price == 2373.90

    def test_slippage_default_is_conservative(self) -> None:
        config = BacktestConfig()
        assert config.slippage_points >= 1.0

    def test_commission_reduces_net_pnl(self) -> None:
        executor = VirtualExecutor(BacktestConfig(commission_per_lot=7.0, slippage_points=0.0))
        position = executor.with_bar_index(
            executor.fill_entry(_plan(), _candle(
                datetime(2026, 1, 1, tzinfo=UTC),
                open_price=2350.0,
                high=2352.0,
                low=2348.0,
                close=2350.0,
            )),
            1,
        )
        exit_event = executor.check_exit(
            position,
            _candle(
                datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
                open_price=2370.0,
                high=2375.0,
                low=2369.0,
                close=2374.0,
            ),
            bar_index=2,
        )
        assert exit_event is not None
        trade = executor.build_trade(
            trade_id=1,
            position=position,
            exit_event=exit_event,
            exit_bar_index=2,
            signal_reason="audit",
        )
        assert trade.commission == pytest.approx(0.14, abs=0.001)
        assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.commission, abs=0.001)

    def test_manual_pnl_long_tp(self) -> None:
        executor = VirtualExecutor(BacktestConfig(
            spread_points=20,
            slippage_points=1.0,
            commission_per_lot=0.0,
        ))
        entry = 2350.0 + 0.10 + 0.01
        exit_fill = 2374.0 - 0.10 - 0.01
        expected_gross = ((exit_fill - entry) / 0.01) * 1.0 * 0.01
        position = SimulatedPosition(
            direction=SignalDirection.LONG,
            volume=0.01,
            entry_price=entry,
            stop_loss=2338.0,
            take_profit=2374.0,
            entry_time=datetime(2026, 1, 1, tzinfo=UTC),
            entry_bar_index=1,
        )
        dummy_candle = _candle(
            datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
            open_price=0,
            high=0,
            low=0,
            close=0,
        )
        trade = executor.build_trade(
            trade_id=1,
            position=position,
            exit_event=executor._exit_event(
                position,
                2374.0,
                dummy_candle,
                ExitReason.TAKE_PROFIT,
            ),
            exit_bar_index=2,
            signal_reason="audit",
        )
        assert trade.gross_pnl == pytest.approx(expected_gross, abs=0.001)


class TestRiskControlsAudit:
    def test_maximum_daily_loss_blocks_new_trades(self) -> None:
        settings = Settings(MAX_DAILY_LOSS_PCT=2.0)
        manager = RiskManager(settings)
        signal = make_buy_signal()
        account = make_account(equity=9700.0)
        state = RiskState(day_start_equity=10_000.0, peak_equity=10_000.0)
        decision = manager.assess(signal, account, make_xauusd_symbol(), [], state)
        from exness_bot.domain.models import RejectedSignal

        assert isinstance(decision, RejectedSignal)
        assert decision.reason == "Maximum daily loss exceeded"

    def test_maximum_drawdown_blocks_new_trades(self) -> None:
        settings = Settings(MAX_DRAWDOWN_PCT=5.0)
        manager = RiskManager(settings)
        signal = make_buy_signal()
        account = make_account(equity=9400.0)
        state = RiskState(day_start_equity=9400.0, peak_equity=10_000.0)
        decision = manager.assess(signal, account, make_xauusd_symbol(), [], state)
        from exness_bot.domain.models import RejectedSignal

        assert isinstance(decision, RejectedSignal)
        assert decision.reason == "Maximum drawdown exceeded"

    def test_maximum_open_positions_enforced_in_engine(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "uptrend.csv", bars=260)
        settings = Settings(MAX_OPEN_POSITIONS=1, TRADING_MODE="dry_run")
        config = BacktestConfig(warmup_bars=200)
        engine = BacktestEngine(settings, config=config)
        report = engine.run(str(csv_path))
        assert report.orders_approved <= report.metrics.total_trades + 1


class TestReproducibilityAudit:
    def test_identical_runs_produce_identical_results(self, tmp_path: Path) -> None:
        csv_path = write_uptrend_csv(tmp_path / "uptrend.csv", bars=260)
        settings = Settings(TRADING_MODE="dry_run")
        config = BacktestConfig(warmup_bars=200, slippage_points=1.0)
        first = BacktestEngine(settings, config=config).run(str(csv_path))
        second = BacktestEngine(settings, config=config).run(str(csv_path))
        assert first.model_dump() == second.model_dump()
