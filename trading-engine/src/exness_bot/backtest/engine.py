"""Deterministic backtest engine."""

from __future__ import annotations

import structlog

from exness_bot.backtest.config import BacktestConfig
from exness_bot.backtest.loader import candles_to_backtest_frame, load_candles_from_csv
from exness_bot.backtest.metrics import calculate_metrics
from exness_bot.backtest.models import (
    BacktestReport,
    EquityPoint,
    ExitReason,
    SimulatedPosition,
    TradeRecord,
)
from exness_bot.backtest.simulator import VirtualExecutor
from exness_bot.backtest.validation import validate_candle_series
from exness_bot.config.settings import Settings
from exness_bot.domain.models import AccountInfo, ApprovedOrderPlan
from exness_bot.indicators.calculator import IndicatorCalculator
from exness_bot.risk.decision import is_risk_approved
from exness_bot.risk.manager import RiskManager
from exness_bot.risk.models import RiskState
from exness_bot.strategy.base import Strategy
from exness_bot.strategy.ema_rsi_atr import EmaRsiAtrStrategy

logger = structlog.get_logger(__name__)


class BacktestEngine:
    """
    Bar-by-bar backtest with no MT5 connectivity.

    Evaluates one closed candle at a time using only past and current data.
    """

    def __init__(
        self,
        settings: Settings,
        strategy: Strategy | None = None,
        config: BacktestConfig | None = None,
    ) -> None:
        self._settings = settings
        self._strategy = strategy or EmaRsiAtrStrategy(settings)
        self._config = config or BacktestConfig.from_settings(settings)
        self._risk_manager = RiskManager(settings)
        self._executor = VirtualExecutor(self._config)

    def run(self, data_path: str) -> BacktestReport:
        """Execute a full backtest on historical CSV candles."""
        candles = load_candles_from_csv(
            data_path,
            symbol=self._config.symbol,
            timeframe=self._config.timeframe,
        )
        validate_candle_series(
            candles,
            self._config.timeframe,
            warmup_bars=self._config.warmup_bars,
        )

        equity = self._config.initial_equity
        peak_equity = equity
        day_start_equity = equity
        current_day: object | None = None

        trades: list[TradeRecord] = []
        equity_curve: list[EquityPoint] = []
        open_position: SimulatedPosition | None = None
        open_signal_reason = ""
        accumulated_swap = 0.0
        last_candle_day: object | None = None

        signals_generated = 0
        orders_approved = 0
        orders_rejected = 0
        trade_counter = 0

        for bar_index in range(self._config.warmup_bars, len(candles)):
            candle = candles[bar_index]
            history = candles[: bar_index + 1]
            history_frame = candles_to_backtest_frame(history)

            if open_position is not None:
                candle_day = candle.timestamp.date()
                if (
                    last_candle_day is not None
                    and candle_day != last_candle_day
                    and self._config.swap_per_lot_per_day > 0
                ):
                    accumulated_swap += (
                        self._config.swap_per_lot_per_day * open_position.volume
                    )
                last_candle_day = candle_day

                exit_event = self._executor.check_exit(
                    open_position,
                    candle,
                    bar_index=bar_index,
                )
                if exit_event is not None:
                    trade_counter += 1
                    trade = self._executor.build_trade(
                        trade_id=trade_counter,
                        position=open_position,
                        exit_event=exit_event,
                        exit_bar_index=bar_index,
                        signal_reason=open_signal_reason,
                        swap_cost=accumulated_swap,
                    )
                    trades.append(trade)
                    equity += trade.net_pnl
                    peak_equity = max(peak_equity, equity)
                    open_position = None
                    open_signal_reason = ""
                    accumulated_swap = 0.0

            candle_day = candle.timestamp.date()
            if current_day != candle_day:
                current_day = candle_day
                day_start_equity = equity

            if open_position is None:
                indicators = IndicatorCalculator.compute(history_frame)
                signal = self._strategy.evaluate(history_frame, indicators)
                signals_generated += 1

                account = AccountInfo(
                    login=0,
                    balance=equity,
                    equity=equity,
                    margin=0.0,
                    free_margin=equity,
                    leverage=500,
                    trade_mode="demo",
                )
                symbol_info = self._config.to_symbol_info(close_price=candle.close)
                risk_state = RiskState(
                    day_start_equity=day_start_equity,
                    peak_equity=peak_equity,
                )
                decision = self._risk_manager.assess(
                    signal,
                    account,
                    symbol_info,
                    [],
                    risk_state,
                )

                if is_risk_approved(decision):
                    orders_approved += 1
                    assert isinstance(decision, ApprovedOrderPlan)
                    open_position = self._executor.with_bar_index(
                        self._executor.fill_entry(decision, candle),
                        bar_index,
                    )
                    open_signal_reason = signal.reason
                else:
                    orders_rejected += 1

            equity_curve.append(
                EquityPoint(
                    timestamp=candle.timestamp,
                    equity=equity,
                    bar_index=bar_index,
                )
            )

        if open_position is not None:
            last_candle = candles[-1]
            exit_event = self._executor.close_at_price(
                open_position,
                last_candle,
                reason=ExitReason.END_OF_DATA,
            )
            trade_counter += 1
            trade = self._executor.build_trade(
                trade_id=trade_counter,
                position=open_position,
                exit_event=exit_event,
                exit_bar_index=len(candles) - 1,
                signal_reason=open_signal_reason,
                swap_cost=accumulated_swap,
            )
            trades.append(trade)
            equity += trade.net_pnl
            equity_curve.append(
                EquityPoint(
                    timestamp=last_candle.timestamp,
                    equity=equity,
                    bar_index=len(candles) - 1,
                )
            )

        metrics = calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_equity=self._config.initial_equity,
        )

        report = BacktestReport(
            strategy_name=self._strategy.name,
            symbol=self._config.symbol,
            timeframe=self._config.timeframe.value,
            config=self._config,
            assumptions=self._config.assumptions,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            bars_processed=len(candles) - self._config.warmup_bars,
            signals_generated=signals_generated,
            orders_approved=orders_approved,
            orders_rejected=orders_rejected,
        )

        logger.info(
            "backtest_complete",
            strategy=report.strategy_name,
            trades=metrics.total_trades,
            net_profit=metrics.net_profit,
            win_rate=metrics.win_rate,
        )
        return report
