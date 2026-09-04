"""Orchestrate SignalResult → RiskManager → ExecutionPort.submit. Virtual fills only."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import structlog

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.settings import Settings
from exness_bot.domain.clock import Clock, SystemClock
from exness_bot.domain.enums import SignalAction, SignalDirection, Timeframe
from exness_bot.domain.execution_validation import (
    ValidationCode,
    validate_quote,
    validate_sl_tp_distance,
    validate_stops_metadata,
    validate_volume,
)
from exness_bot.domain.models import (
    AccountInfo,
    ApprovedOrderPlan,
    Candle,
    Position,
    Signal,
    SymbolInfo,
    Tick,
)
from exness_bot.execution.eligibility import ExecutionEventKind
from exness_bot.execution.guard import (
    CompositeExecutionGuard,
    EventEligibilityGuard,
    UnresolvedIntentGuard,
)
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.planning import plan_from_approved
from exness_bot.execution.result import OrchestrationOutcome
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionQuery,
    UnavailableBrokerExecutionQuery,
)
from exness_bot.paper_execution.contract import (
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from exness_bot.paper_execution.models import (
    ConsumeResult,
    ExecutionOutcome,
    PaperAccount,
    PaperExitReason,
    PaperRejection,
    PaperSession,
    RejectionCode,
    VirtualExit,
    VirtualPosition,
)
from exness_bot.paper_execution.port import ExecutionPort
from exness_bot.paper_execution.pricing import simulate_entry_fill
from exness_bot.paper_execution.state import PaperStateStore
from exness_bot.paper_execution.unknown_recovery import reconcile_unknown_intents
from exness_bot.risk.manager import RiskManager
from exness_bot.risk.models import RiskState
from exness_bot.signal_engine.models import SignalEmission, SignalKind, SignalResult

logger = structlog.get_logger(__name__)


class ExecutionService:
    """Event-driven paper execution. Signal Engine stays unaware of this layer."""

    def __init__(
        self,
        *,
        risk_manager: RiskManager,
        store: PaperStateStore,
        settings: Settings,
        config: BacktestConfig,
        symbol_info: SymbolInfo,
        clock: Clock | None = None,
        port: ExecutionPort | None = None,
        broker_query: BrokerExecutionQuery | None = None,
    ) -> None:
        self._risk = risk_manager
        self._store = store
        self._settings = settings
        self._config = config
        self._symbol = _ensure_paper_stops(symbol_info, config)
        self._clock = clock or SystemClock()
        self._executor = PaperExecutor(store.load(), config=config)
        self._port: ExecutionPort = port or self._executor
        self._broker_query: BrokerExecutionQuery = (
            broker_query or UnavailableBrokerExecutionQuery()
        )
        self._intents = SnapshotIntentStore(self._executor, persist=self._persist)
        self._orchestrator = ExecutionOrchestrator(
            store=self._intents,
            port=self._port,
            clock=self._clock.now_utc,
            guard=CompositeExecutionGuard(
                guards=(
                    EventEligibilityGuard(),
                    UnresolvedIntentGuard(store=self._intents),
                )
            ),
            intent_id_factory=lambda _plan: f"paper-intent-{self._executor.allocate_id()}",
        )
        self._executor.ensure_session(self._clock.now_utc())
        recovered = self._intents.recover_in_flight_to_unknown(now=self._clock.now_utc())
        if recovered:
            logger.warning(
                "execution_intent_recovered_unknown",
                count=len(recovered),
                intent_ids=[item.intent_id for item in recovered],
            )
        reconciled = reconcile_unknown_intents(
            self._intents,
            self._broker_query,
            now=self._clock.now_utc(),
        )
        if reconciled:
            logger.info(
                "execution_intent_reconciled",
                count=len(reconciled),
                intent_ids=[item.intent_id for item in reconciled],
            )
        self._persist()

    def open_positions(self) -> tuple[VirtualPosition, ...]:
        return self._executor.get_open_positions()

    def account_state(self) -> PaperAccount:
        return self._executor.get_account_state()

    def session(self) -> PaperSession:
        account = self.account_state()
        snap = self._executor.snapshot
        return PaperSession(
            session_id=snap.session_id,
            started_at=snap.started_at,
            initial_balance=account.initial_balance,
            balance=account.balance,
            equity=account.equity,
            unrealized_pnl=account.unrealized_pnl,
            realized_pnl=account.realized_pnl,
            drawdown_pct=account.drawdown_pct,
            daily_pnl=account.daily_pnl,
            open_positions=len(self.open_positions()),
            execution_count=len(snap.orders),
            signal_count=snap.signal_count,
            candles_processed=snap.candles_processed,
            rejected_count=len(snap.rejections),
            mode=account.mode,
        )

    def journal(self) -> tuple[VirtualExit, ...]:
        return self._executor.snapshot.exits

    def rejections(self) -> tuple[PaperRejection, ...]:
        return self._executor.snapshot.rejections

    def intents(self) -> tuple[IntentRecord, ...]:
        return self._executor.snapshot.intents

    def last_execution(self) -> ConsumeResult | None:
        orders = self._executor.snapshot.orders
        rejections = self._executor.snapshot.rejections
        last_order = orders[-1] if orders else None
        last_rejection = rejections[-1] if rejections else None
        if last_order is None and last_rejection is None:
            return None
        if last_order is None and last_rejection is not None:
            return ConsumeResult(
                status=ExecutionOutcome.REJECTED,
                rejection_code=last_rejection.code,
                reason=last_rejection.reason,
            )
        if last_order is not None and (
            last_rejection is None or last_order.created_at >= last_rejection.at
        ):
            return ConsumeResult(status=ExecutionOutcome.FILLED, order=last_order)
        if last_rejection is None:
            return None
        return ConsumeResult(
            status=ExecutionOutcome.REJECTED,
            rejection_code=last_rejection.code,
            reason=last_rejection.reason,
        )

    def last_execution_at(self) -> datetime | None:
        orders = self._executor.snapshot.orders
        rejections = self._executor.snapshot.rejections
        last_order = orders[-1].created_at if orders else None
        last_rejection = rejections[-1].at if rejections else None
        if last_order is None:
            return last_rejection
        if last_rejection is None:
            return last_order
        return max(last_order, last_rejection)

    def update_quote(self, symbol: SymbolInfo) -> None:
        self._symbol = _ensure_paper_stops(symbol, self._config)

    def current_symbol(self) -> SymbolInfo:
        """Read-only quote/symbol snapshot used by preflight (no mutations)."""
        return self._symbol

    def update_quote_from_tick(self, tick: Tick, config: BacktestConfig) -> None:
        spread = self._symbol.spread
        if tick.ask > 0 and tick.bid > 0 and config.point > 0:
            spread = max(1, round((tick.ask - tick.bid) / config.point))
        self._symbol = config.to_symbol_info(close_price=tick.last or tick.bid).model_copy(
            update={
                "symbol": tick.symbol or self._symbol.symbol,
                "bid": tick.bid,
                "ask": tick.ask,
                "spread": spread,
                "stops_level": config.paper_stops_level,
                "freeze_level": config.paper_freeze_level,
            }
        )

    def mark_to_market(self, symbol: SymbolInfo) -> None:
        self._symbol = symbol
        self._executor.mark_positions(symbol)
        logger.debug("paper_position_marked_to_market", equity=self.account_state().equity)
        self._persist()

    def consume_results(self, results: Sequence[SignalResult]) -> list[ConsumeResult]:
        """
        Catch-up / burst gate at the execution boundary.

        Among executable actionable signals, only the latest candle_timestamp may execute.
        Historical / catch-up / non-executable signals are ignored.
        """
        outcomes: list[ConsumeResult] = []
        candidates = [
            item
            for item in results
            if item.actionable
            and item.executable
            and item.signal in {SignalKind.BUY, SignalKind.SELL}
            and item.emission == SignalEmission.SIGNAL_EMISSION
        ]
        latest_key: str | None = None
        if candidates:
            latest = max(candidates, key=lambda item: item.candle_timestamp)
            latest_key = latest.idempotency_key

        for item in results:
            if (
                latest_key is not None
                and item.idempotency_key != latest_key
                and item.actionable
                and item.signal in {SignalKind.BUY, SignalKind.SELL}
            ):
                self._executor.note_signal()
                outcomes.append(
                    ConsumeResult(
                        status=ExecutionOutcome.CATCHUP_IGNORED,
                        reason="Bỏ qua tín hiệu catch-up/historical — chỉ nến latest được khớp.",
                    )
                )
                self._persist()
                continue
            outcomes.append(self.consume(item))
        return outcomes

    def consume(self, result: SignalResult) -> ConsumeResult:
        self._executor.note_signal()
        if not result.actionable or result.signal not in {SignalKind.BUY, SignalKind.SELL}:
            self._persist()
            return ConsumeResult(status=ExecutionOutcome.IGNORED, reason="Không actionable.")
        if not result.executable or result.emission != SignalEmission.SIGNAL_EMISSION:
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.CATCHUP_IGNORED,
                reason="Tín hiệu không executable (catch-up/historical/warmup).",
            )
        if self._executor.has_key(result.idempotency_key):
            self._persist()
            return ConsumeResult(status=ExecutionOutcome.DUPLICATE, reason="Tín hiệu đã xử lý.")
        existing = self._intents.get_by_key(result.idempotency_key)
        if existing is not None and existing.lifecycle in {
            IntentLifecycle.INTENT_CREATED,
            IntentLifecycle.IN_FLIGHT,
            IntentLifecycle.UNKNOWN,
            IntentLifecycle.FILLED,
            IntentLifecycle.REJECTED,
        }:
            self._persist()
            if existing.lifecycle in {
                IntentLifecycle.INTENT_CREATED,
                IntentLifecycle.IN_FLIGHT,
                IntentLifecycle.UNKNOWN,
            }:
                return ConsumeResult(
                    status=ExecutionOutcome.UNKNOWN,
                    reason="Intent CREATED/IN_FLIGHT/UNKNOWN — không gửi side effect mới.",
                )
            return ConsumeResult(status=ExecutionOutcome.DUPLICATE, reason="Tín hiệu đã xử lý.")
        if self._executor.has_blocking_intent(result.idempotency_key):
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.UNKNOWN,
                reason="Intent IN_FLIGHT/UNKNOWN — không gửi side effect mới.",
            )

        side = (
            SignalDirection.LONG if result.signal == SignalKind.BUY else SignalDirection.SHORT
        )
        # Paper-only: simulate fill for RiskManager sizing. Intent still has NO fill_price;
        # PaperExecutor.submit regenerates the fill from the same quote.
        sizing_fill = simulate_entry_fill(side=side, symbol=self._symbol, config=self._config)
        signal = _to_signal(result, sizing_fill.fill_price)
        account = _paper_account_info(self._executor.get_account_state())
        risk_state = RiskState(
            day_start_equity=max(self._executor.snapshot.day_start_equity, 0.01),
            peak_equity=max(self._executor.snapshot.peak_equity, 0.01),
        )
        open_broker = [_to_broker_position(item) for item in self.open_positions()]
        decision = self._risk.assess(signal, account, self._symbol, open_broker, risk_state)
        now = self._clock.now_utc()
        if not isinstance(decision, ApprovedOrderPlan):
            code = map_rejection(decision.reason)
            self._executor.remember_key(result.idempotency_key)
            self._executor.record_rejection(
                PaperRejection(
                    signal_id=result.idempotency_key,
                    code=code,
                    reason=decision.reason,
                    at=now,
                )
            )
            logger.info(
                "paper_execution_rejected",
                code=code.value,
                reason=decision.reason,
                signal=result.signal.value,
            )
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.REJECTED,
                rejection_code=code,
                reason=decision.reason,
            )

        gate = _validate_before_submit(
            symbol=self._symbol,
            volume=decision.volume,
            entry_price=sizing_fill.fill_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            side=side,
        )
        if gate is not None:
            code, reason = gate
            self._executor.remember_key(result.idempotency_key)
            self._executor.record_rejection(
                PaperRejection(
                    signal_id=result.idempotency_key,
                    code=code,
                    reason=reason,
                    at=now,
                )
            )
            logger.info(
                "paper_execution_validation_rejected",
                code=code.value,
                reason=reason,
            )
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.REJECTED,
                rejection_code=code,
                reason=reason,
            )

        plan = plan_from_approved(
            result=result,
            decision=decision,
            side=side,
            now=now,
            event_kind=ExecutionEventKind.LIVE,
            plan_id=f"plan-{result.idempotency_key}",
        )
        orch = self._orchestrator.execute(plan, quote=self._symbol)
        self._executor.remember_key(result.idempotency_key)

        if orch.outcome == OrchestrationOutcome.BLOCKED:
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.UNKNOWN,
                reason=orch.message,
            )
        if orch.outcome == OrchestrationOutcome.DUPLICATE:
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.DUPLICATE,
                reason=orch.message,
            )
        if orch.outcome == OrchestrationOutcome.ERROR:
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.UNKNOWN,
                reason=orch.message,
            )
        if orch.outcome == OrchestrationOutcome.REJECTED:
            self._executor.record_rejection(
                PaperRejection(
                    signal_id=result.idempotency_key,
                    code=RejectionCode.INVALID_RISK,
                    reason=orch.message or "Execution rejected.",
                    at=self._clock.now_utc(),
                )
            )
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.REJECTED,
                rejection_code=RejectionCode.INVALID_RISK,
                reason=orch.message,
            )
        if orch.outcome == OrchestrationOutcome.UNKNOWN:
            self._persist()
            return ConsumeResult(
                status=ExecutionOutcome.UNKNOWN,
                reason=orch.message,
            )

        order = None
        position = None
        if orch.lifecycle is IntentLifecycle.FILLED and self._executor.snapshot.orders:
            order = self._executor.snapshot.orders[-1]
            opens = self.open_positions()
            position = opens[-1] if opens else None
        logger.info(
            "paper_execution_ack",
            intent_id=orch.intent.intent_id if orch.intent else None,
            ack=orch.ack.status.value if orch.ack else None,
            lifecycle=orch.lifecycle.value if orch.lifecycle else None,
            fill=orch.ack.fill_price if orch.ack else None,
        )
        self._persist()
        return ConsumeResult(
            status=ExecutionOutcome.FILLED,
            order=order,
            position=position,
            reason=orch.message,
        )

    def on_closed_candle(self, candle: Candle) -> VirtualExit | None:
        self._executor.note_candle()
        self._executor.accrue_swap(candle.timestamp)
        for position in self.open_positions():
            if candle.timestamp <= position.opened_at:
                continue
            reason, trigger = _exit_trigger(position, candle)
            if reason is None or trigger is None:
                continue
            exit_fill = self._executor.build_exit(
                position,
                trigger_price=trigger,
                reason=reason,
                when=candle.timestamp,
                symbol=self._symbol,
            )
            self._executor.close_position(position.position_id, exit_fill)
            logger.info(
                "paper_position_closed",
                position_id=position.position_id,
                reason=reason.value,
                net_pnl=exit_fill.net_pnl,
            )
            self._persist()
            return exit_fill
        self._executor.mark_positions(self._symbol)
        self._persist()
        return None

    def _persist(self) -> None:
        self._store.save(self._executor.snapshot)


def _to_signal(result: SignalResult, entry_price: float) -> Signal:
    action = SignalAction.BUY if result.signal == SignalKind.BUY else SignalAction.SELL
    return Signal.create(
        action=action,
        strategy_name=result.strategy,
        symbol=result.symbol,
        timeframe=Timeframe(result.timeframe),
        entry_price=entry_price,
        timestamp=result.candle_timestamp,
        indicators=result.indicators,
        reason=result.reason,
    )


def _paper_account_info(account: PaperAccount) -> AccountInfo:
    equity = account.equity
    return AccountInfo(
        login=0,
        balance=account.balance,
        equity=equity,
        margin=0.0,
        free_margin=max(equity, 0.0),
        leverage=500,
        trade_mode="demo",
        name="paper",
        server="PAPER",
    )


def _to_broker_position(item: VirtualPosition) -> Position:
    ticket = abs(hash(item.position_id)) % 1_000_000_000
    return Position(
        ticket=ticket,
        symbol=item.symbol,
        volume=item.volume,
        direction=item.side,
        open_price=item.entry_price,
        current_price=item.entry_price,
        stop_loss=item.stop_loss,
        take_profit=item.take_profit,
        open_time=item.opened_at,
    )


def _exit_trigger(
    position: VirtualPosition,
    candle: Candle,
) -> tuple[PaperExitReason | None, float | None]:
    if position.side == SignalDirection.LONG:
        sl_hit = candle.low <= position.stop_loss
        tp_hit = candle.high >= position.take_profit
        if sl_hit and tp_hit:
            return PaperExitReason.SL, position.stop_loss
        if sl_hit:
            return PaperExitReason.SL, position.stop_loss
        if tp_hit:
            return PaperExitReason.TP, position.take_profit
        return None, None
    sl_hit = candle.high >= position.stop_loss
    tp_hit = candle.low <= position.take_profit
    if sl_hit and tp_hit:
        return PaperExitReason.SL, position.stop_loss
    if sl_hit:
        return PaperExitReason.SL, position.stop_loss
    if tp_hit:
        return PaperExitReason.TP, position.take_profit
    return None, None


def _ensure_paper_stops(symbol: SymbolInfo, config: BacktestConfig) -> SymbolInfo:
    """Attach explicit paper research stops when caller omitted broker metadata."""
    updates: dict[str, int] = {}
    if symbol.stops_level is None:
        updates["stops_level"] = config.paper_stops_level
    if symbol.freeze_level is None:
        updates["freeze_level"] = config.paper_freeze_level
    if not updates:
        return symbol
    return symbol.model_copy(update=updates)


def _validate_before_submit(
    *,
    symbol: SymbolInfo,
    volume: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    side: SignalDirection,
) -> tuple[RejectionCode, str] | None:
    """Fail-closed gate — must run BEFORE persist(IN_FLIGHT) and submit()."""
    quote = validate_quote(symbol)
    if not quote.ok:
        return RejectionCode.INVALID_QUOTE, quote.message or quote.code.value
    vol = validate_volume(volume, symbol)
    if not vol.ok:
        return RejectionCode.INVALID_VOLUME, vol.message or vol.code.value
    stops = validate_stops_metadata(symbol)
    if not stops.ok:
        return RejectionCode.INVALID_STOPS, stops.message or stops.code.value
    distance = validate_sl_tp_distance(
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        side=side,
        symbol=symbol,
    )
    if not distance.ok:
        if distance.code == ValidationCode.INVALID_TP_DISTANCE:
            return RejectionCode.INVALID_TP, distance.message or distance.code.value
        return RejectionCode.INVALID_SL, distance.message or distance.code.value
    return None


def map_rejection(reason: str) -> RejectionCode:
    text = reason.lower()
    if "daily loss" in text:
        return RejectionCode.MAX_DAILY_LOSS
    if "drawdown" in text:
        return RejectionCode.MAX_DRAWDOWN
    if "open position" in text:
        return RejectionCode.MAX_OPEN_POSITIONS
    if "exceeds maximum" in text or "position size" in text:
        return RejectionCode.POSITION_SIZE_LIMIT
    if "bid/ask" in text or ("bid" in text and "ask" in text):
        return RejectionCode.INVALID_QUOTE
    if "atr" in text or "stop loss" in text:
        return RejectionCode.INVALID_SL
    return RejectionCode.INVALID_RISK
