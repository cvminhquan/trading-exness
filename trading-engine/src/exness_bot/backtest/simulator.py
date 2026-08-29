"""Virtual order execution for backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from exness_bot.backtest.config import BacktestConfig
from exness_bot.backtest.models import ExitReason, SimulatedPosition, TradeRecord
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import ApprovedOrderPlan, Candle
from exness_bot.risk.position_sizer import money_per_point_per_lot

# When both SL and TP are reachable inside one bar, assume SL (conservative).
SAME_BAR_EXIT_RULE = "stop_loss_first"


@dataclass(frozen=True)
class ExitEvent:
    """Simulated position exit."""

    exit_price: float
    exit_time: datetime
    exit_reason: ExitReason


class VirtualExecutor:
    """Simulate fills, spread, slippage, and SL/TP intrabar resolution."""

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        self._symbol_info = config.to_symbol_info(close_price=1.0)
        self._point_value = money_per_point_per_lot(self._symbol_info)

    def fill_entry(self, plan: ApprovedOrderPlan, candle: Candle) -> SimulatedPosition:
        """Open a virtual position at the signal bar close."""
        if plan.order_request.direction == SignalDirection.LONG:
            price = candle.close + self._half_spread_price() + self._slippage_price()
        else:
            price = candle.close - self._half_spread_price() - self._slippage_price()

        return SimulatedPosition(
            direction=plan.order_request.direction,
            volume=plan.volume,
            entry_price=price,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            entry_time=candle.timestamp,
            entry_bar_index=-1,
        )

    def with_bar_index(self, position: SimulatedPosition, bar_index: int) -> SimulatedPosition:
        return position.model_copy(update={"entry_bar_index": bar_index})

    def check_exit(
        self,
        position: SimulatedPosition,
        candle: Candle,
        *,
        bar_index: int,
    ) -> ExitEvent | None:
        """
        Return an exit when SL/TP is touched within the candle range.

        Exits are never evaluated on the entry bar (entry occurs at bar close).
        """
        if bar_index <= position.entry_bar_index:
            return None

        if position.direction == SignalDirection.LONG:
            sl_hit = candle.low <= position.stop_loss
            tp_hit = candle.high >= position.take_profit
            if sl_hit and tp_hit:
                return self._exit_event(
                    position,
                    position.stop_loss,
                    candle,
                    ExitReason.STOP_LOSS,
                )
            if sl_hit:
                return self._exit_event(
                    position,
                    position.stop_loss,
                    candle,
                    ExitReason.STOP_LOSS,
                )
            if tp_hit:
                return self._exit_event(
                    position,
                    position.take_profit,
                    candle,
                    ExitReason.TAKE_PROFIT,
                )
            return None

        sl_hit = candle.high >= position.stop_loss
        tp_hit = candle.low <= position.take_profit
        if sl_hit and tp_hit:
            return self._exit_event(
                position,
                position.stop_loss,
                candle,
                ExitReason.STOP_LOSS,
            )
        if sl_hit:
            return self._exit_event(
                position,
                position.stop_loss,
                candle,
                ExitReason.STOP_LOSS,
            )
        if tp_hit:
            return self._exit_event(
                position,
                position.take_profit,
                candle,
                ExitReason.TAKE_PROFIT,
            )
        return None

    def close_at_price(
        self,
        position: SimulatedPosition,
        candle: Candle,
        *,
        reason: ExitReason,
    ) -> ExitEvent:
        return self._exit_event(position, candle.close, candle, reason)

    def build_trade(
        self,
        *,
        trade_id: int,
        position: SimulatedPosition,
        exit_event: ExitEvent,
        exit_bar_index: int,
        signal_reason: str,
        swap_cost: float = 0.0,
    ) -> TradeRecord:
        gross_pnl = self._calculate_pnl(
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_event.exit_price,
            volume=position.volume,
        )
        commission = self._config.commission_per_lot * position.volume * 2
        net_pnl = gross_pnl - commission - swap_cost
        return TradeRecord(
            trade_id=trade_id,
            direction=position.direction,
            volume=position.volume,
            entry_price=position.entry_price,
            exit_price=exit_event.exit_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            entry_time=position.entry_time,
            exit_time=exit_event.exit_time,
            exit_reason=exit_event.exit_reason,
            gross_pnl=gross_pnl,
            commission=commission,
            net_pnl=net_pnl,
            bars_held=max(exit_bar_index - position.entry_bar_index, 0),
            signal_reason=signal_reason,
        )

    def _exit_event(
        self,
        position: SimulatedPosition,
        trigger_price: float,
        candle: Candle,
        reason: ExitReason,
    ) -> ExitEvent:
        fill = self._exit_fill_price(position.direction, trigger_price)
        return ExitEvent(
            exit_price=fill,
            exit_time=candle.timestamp,
            exit_reason=reason,
        )

    def _exit_fill_price(self, direction: SignalDirection, trigger_price: float) -> float:
        """Apply adverse spread and slippage on exit fills."""
        cost = self._half_spread_price() + self._slippage_price()
        if direction == SignalDirection.LONG:
            return trigger_price - cost
        return trigger_price + cost

    def _calculate_pnl(
        self,
        *,
        direction: SignalDirection,
        entry_price: float,
        exit_price: float,
        volume: float,
    ) -> float:
        points = (exit_price - entry_price) / self._config.point
        if direction == SignalDirection.SHORT:
            points = -points
        return points * self._point_value * volume

    def _half_spread_price(self) -> float:
        return self._config.spread_points * self._config.point / 2

    def _slippage_price(self) -> float:
        return self._config.slippage_points * self._config.point
