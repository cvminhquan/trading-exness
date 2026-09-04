"""In-memory paper executor — implements ExecutionPort. No broker calls."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from exness_bot.backtest.config import BacktestConfig
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import SymbolInfo
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionAck,
    ExecutionIntent,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.models import (
    ExecutionMode,
    OrderStatus,
    PaperAccount,
    PaperExitReason,
    PaperRejection,
    PaperSnapshot,
    PositionStatus,
    VirtualExit,
    VirtualOrder,
    VirtualPosition,
)
from exness_bot.paper_execution.pricing import simulate_entry_fill, simulate_exit_fill
from exness_bot.risk.position_sizer import money_per_point_per_lot


class PaperExecutor:
    """Virtual fills and positions. Never talks to a trading adapter."""

    def __init__(self, snapshot: PaperSnapshot, *, config: BacktestConfig) -> None:
        self._config = config
        self._snapshot = snapshot

    @property
    def snapshot(self) -> PaperSnapshot:
        return self._snapshot

    def submit(self, intent: ExecutionIntent, *, quote: SymbolInfo) -> ExecutionAck:
        """Fill immediately from quote — fill_price is generated here, not by caller."""
        fill = simulate_entry_fill(side=intent.side, symbol=quote, config=self._config)
        seq = intent.intent_id.rsplit("-", maxsplit=1)[-1]
        order_id = f"paper-order-{seq}"
        position_id = f"paper-pos-{seq}"
        order = VirtualOrder(
            order_id=order_id,
            signal_id=intent.idempotency_key,
            symbol=intent.symbol,
            side=intent.side,
            requested_price=fill.requested_price,
            fill_price=fill.fill_price,
            volume=intent.requested_quantity,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            created_at=intent.created_at,
            status=OrderStatus.FILLED,
        )
        position = VirtualPosition(
            position_id=position_id,
            symbol=intent.symbol,
            side=intent.side,
            volume=intent.requested_quantity,
            entry_price=fill.fill_price,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            opened_at=intent.created_at,
            signal_id=intent.idempotency_key,
            current_price=fill.fill_price,
            last_calendar_day=intent.created_at,
        )
        snap = self._snapshot
        self._snapshot = replace(
            snap,
            positions=(*snap.positions, position),
            orders=(*snap.orders, order),
        )
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.FILLED,
            timestamp=intent.created_at,
            requested_price=fill.requested_price,
            fill_price=fill.fill_price,
            filled_quantity=intent.requested_quantity,
            broker_order_id=None,
            broker_position_id=None,
            reason=None,
        )

    def close_position(self, position_id: str, exit_fill: VirtualExit) -> VirtualPosition:
        remaining: list[VirtualPosition] = []
        closed: VirtualPosition | None = None
        for item in self._snapshot.positions:
            if item.position_id == position_id and item.status == PositionStatus.OPEN:
                closed = replace(
                    item,
                    status=PositionStatus.CLOSED,
                    realized_pnl=exit_fill.net_pnl,
                    unrealized_pnl=0.0,
                )
            else:
                remaining.append(item)
        if closed is None:
            msg = f"Unknown paper position {position_id}"
            raise ValueError(msg)
        cash = round(self._snapshot.cash_balance + exit_fill.net_pnl, 2)
        realized = round(self._snapshot.realized_pnl + exit_fill.net_pnl, 2)
        peak = max(self._snapshot.peak_equity, cash)
        self._snapshot = replace(
            self._snapshot,
            positions=tuple(remaining),
            exits=(*self._snapshot.exits, exit_fill),
            cash_balance=cash,
            realized_pnl=realized,
            peak_equity=peak,
            accumulated_swap=0.0,
        )
        return closed

    def get_open_positions(self) -> tuple[VirtualPosition, ...]:
        return tuple(
            item for item in self._snapshot.positions if item.status == PositionStatus.OPEN
        )

    def get_account_state(self) -> PaperAccount:
        unrealized = sum(item.unrealized_pnl for item in self.get_open_positions())
        equity = round(self._snapshot.cash_balance + unrealized, 2)
        peak = max(self._snapshot.peak_equity, equity)
        day_start = self._snapshot.day_start_equity
        daily = round(equity - day_start, 2)
        drawdown = 0.0
        if peak > 0:
            drawdown = round(((peak - equity) / peak) * 100.0, 4)
        return PaperAccount(
            initial_balance=self._snapshot.initial_balance,
            balance=self._snapshot.cash_balance,
            equity=equity,
            realized_pnl=self._snapshot.realized_pnl,
            unrealized_pnl=round(unrealized, 2),
            daily_pnl=daily,
            drawdown_pct=drawdown,
            peak_equity=peak,
            day_start_equity=day_start,
            mode=ExecutionMode.PAPER.value,
        )

    def mark_positions(self, symbol: SymbolInfo) -> None:
        updated: list[VirtualPosition] = []
        unrealized_total = 0.0
        for item in self._snapshot.positions:
            if item.status != PositionStatus.OPEN:
                updated.append(item)
                continue
            mark = symbol.bid if item.side == SignalDirection.LONG else symbol.ask
            pnl = _gross_pnl(item.side, item.entry_price, mark, item.volume, self._config)
            rounded = round(pnl, 2)
            unrealized_total += rounded
            updated.append(replace(item, unrealized_pnl=rounded, current_price=mark))
        equity = round(self._snapshot.cash_balance + unrealized_total, 2)
        peak = max(self._snapshot.peak_equity, equity)
        self._snapshot = replace(self._snapshot, positions=tuple(updated), peak_equity=peak)

    def accrue_swap(self, calendar_day: datetime) -> None:
        open_positions = self.get_open_positions()
        if not open_positions or self._config.swap_per_lot_per_day <= 0:
            return
        added = 0.0
        updated: list[VirtualPosition] = []
        for item in self._snapshot.positions:
            if item.status != PositionStatus.OPEN:
                updated.append(item)
                continue
            last = item.last_calendar_day
            last_day = last.date() if last is not None else None
            if last_day is not None and calendar_day.date() != last_day:
                added += self._config.swap_per_lot_per_day * item.volume
            updated.append(replace(item, last_calendar_day=calendar_day))
        if added:
            self._snapshot = replace(
                self._snapshot,
                positions=tuple(updated),
                accumulated_swap=round(self._snapshot.accumulated_swap + added, 6),
            )
        else:
            self._snapshot = replace(self._snapshot, positions=tuple(updated))

    def note_candle(self) -> None:
        self._snapshot = replace(
            self._snapshot,
            candles_processed=self._snapshot.candles_processed + 1,
        )

    def note_signal(self) -> None:
        self._snapshot = replace(
            self._snapshot,
            signal_count=self._snapshot.signal_count + 1,
        )

    def ensure_session(self, started_at: datetime) -> None:
        snap = self._snapshot
        if snap.session_id and snap.started_at is not None:
            return
        self._snapshot = replace(
            snap,
            session_id=snap.session_id or f"paper-{int(started_at.timestamp())}",
            started_at=snap.started_at or started_at,
        )

    def remember_key(self, key: str) -> None:
        if key in self._snapshot.executed_keys:
            return
        self._snapshot = replace(
            self._snapshot,
            executed_keys=(*self._snapshot.executed_keys, key),
        )

    def record_rejection(self, rejection: PaperRejection) -> None:
        self._snapshot = replace(
            self._snapshot,
            rejections=(*self._snapshot.rejections, rejection),
        )

    def upsert_intent(self, record: IntentRecord) -> None:
        remaining = tuple(
            item for item in self._snapshot.intents if item.intent_id != record.intent_id
        )
        self._snapshot = replace(self._snapshot, intents=(*remaining, record))

    def intent_by_key(self, idempotency_key: str) -> IntentRecord | None:
        for item in reversed(self._snapshot.intents):
            if item.idempotency_key == idempotency_key:
                return item
        return None

    def allocate_id(self) -> int:
        value = self._snapshot.next_id
        self._snapshot = replace(self._snapshot, next_id=value + 1)
        return value

    def has_key(self, key: str) -> bool:
        return key in self._snapshot.executed_keys

    def has_blocking_intent(self, key: str) -> bool:
        """CREATED / IN_FLIGHT / UNKNOWN for the same key must not spawn a new side effect."""
        for item in self._snapshot.intents:
            if item.idempotency_key != key:
                continue
            if item.lifecycle in {
                IntentLifecycle.INTENT_CREATED,
                IntentLifecycle.IN_FLIGHT,
                IntentLifecycle.UNKNOWN,
            }:
                return True
        return False

    def pop_swap(self) -> float:
        value = self._snapshot.accumulated_swap
        self._snapshot = replace(self._snapshot, accumulated_swap=0.0)
        return value

    def build_exit(
        self,
        position: VirtualPosition,
        *,
        trigger_price: float,
        reason: PaperExitReason,
        when: datetime,
        symbol: SymbolInfo,
    ) -> VirtualExit:
        fill = simulate_exit_fill(
            side=position.side,
            trigger_price=trigger_price,
            config=self._config,
            symbol=symbol,
        )
        gross = _gross_pnl(
            position.side,
            position.entry_price,
            fill,
            position.volume,
            self._config,
        )
        commission = self._config.commission_per_lot * position.volume * 2
        swap = self._snapshot.accumulated_swap
        net = round(gross - commission - swap, 2)
        return VirtualExit(
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            volume=position.volume,
            entry_price=position.entry_price,
            exit_price=fill,
            exit_timestamp=when,
            exit_reason=reason,
            gross_pnl=round(gross, 2),
            commission=round(commission, 2),
            swap=round(swap, 2),
            net_pnl=net,
            signal_id=position.signal_id,
        )


def _gross_pnl(
    side: SignalDirection,
    entry: float,
    exit_price: float,
    volume: float,
    config: BacktestConfig,
) -> float:
    symbol = config.to_symbol_info(close_price=exit_price)
    point_value = money_per_point_per_lot(symbol)
    points = (exit_price - entry) / config.point
    if side == SignalDirection.SHORT:
        points = -points
    return points * point_value * volume
