"""Trading engine — orchestrates the autonomous M15 bar-close loop."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel

from exness_bot.broker.execution import ExecutableBroker
from exness_bot.config.safety import SafetyGuard
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import ApprovedOrderPlan
from exness_bot.engine.models import CycleStatus, PauseReason, TradingCycleResult
from exness_bot.indicators.calculator import IndicatorCalculator
from exness_bot.market_data.candles import (
    bars_through_closed_candle,
    get_latest_closed_candle,
    normalize_timestamp,
)
from exness_bot.market_data.provider import MarketDataProvider
from exness_bot.orders.context import OrderExecutionContext
from exness_bot.orders.manager import OrderManager
from exness_bot.persistence.models import TradingEventRecord
from exness_bot.persistence.repository import TradingRepository
from exness_bot.risk.decision import is_risk_approved, risk_rejection_reason
from exness_bot.risk.manager import RiskManager
from exness_bot.risk.models import RiskState
from exness_bot.strategy.base import Strategy

logger = structlog.get_logger(__name__)


class TradingEngine:
    """
    Orchestrates: Market Data → Strategy → Risk → Orders.

    Processes only newly closed M15 candles with idempotent persistence.
    """

    def __init__(
        self,
        settings: Settings,
        broker: ExecutableBroker,
        market_data: MarketDataProvider,
        strategy: Strategy,
        risk_manager: RiskManager,
        order_manager: OrderManager,
        repository: TradingRepository,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        self._settings = settings
        self._broker = broker
        self._market_data = market_data
        self._strategy = strategy
        self._risk_manager = risk_manager
        self._order_manager = order_manager
        self._repository = repository
        self._safety = safety_guard or SafetyGuard(settings)
        self._timeframe = Timeframe(settings.timeframe)
        self._paused = False
        self._pause_reason: PauseReason | None = None

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def pause_reason(self) -> PauseReason | None:
        return self._pause_reason

    def startup(self) -> None:
        """Initialize engine and run safety checks."""
        logger.info(
            "engine_startup",
            symbol=self._settings.symbol,
            timeframe=self._settings.timeframe,
            trading_mode=self._settings.trading_mode.value,
            dry_run=self._settings.dry_run,
            is_dry_run_mode=self._settings.is_dry_run_mode,
            allow_live_trading=self._settings.allow_live_trading,
        )

        for result in self._safety.validate_startup():
            if result.allowed:
                continue
            logger.warning("startup_safety_check", message=result.message)

        if not self._repository.health_check():
            self._set_paused(PauseReason.DATABASE_UNAVAILABLE, "Database health check failed")

    def resume(self) -> None:
        """Clear pause state after an operator resolves the underlying issue."""
        self._paused = False
        self._pause_reason = None
        logger.info("engine_resumed")

    def tick(self) -> TradingCycleResult:
        """Execute one trading cycle for the latest closed candle."""
        if self._paused:
            pause_label = self._pause_reason.value if self._pause_reason else "unknown"
            return TradingCycleResult(
                status=CycleStatus.PAUSED,
                message=f"Engine paused: {pause_label}",
                paused=True,
                pause_reason=self._pause_reason,
            )

        symbol = self._settings.symbol
        timeframe = self._timeframe

        try:
            if not self._broker.is_connected():
                return self._pause(PauseReason.MT5_DISCONNECTED, "MT5 broker is not connected")

            if not self._repository.health_check():
                return self._pause(PauseReason.DATABASE_UNAVAILABLE, "Database unavailable")

            bars = self._market_data.get_latest_bars(
                symbol,
                timeframe,
                self._settings.candle_history_count,
            )
            if bars.empty:
                return self._pause(PauseReason.MARKET_DATA_UNAVAILABLE, "No market data returned")

            closed_candle = get_latest_closed_candle(bars, timeframe)
            if closed_candle is None:
                return TradingCycleResult(
                    status=CycleStatus.SKIPPED,
                    message="No closed candle available yet",
                )

            candle_timestamp = normalize_timestamp(closed_candle["timestamp"])
            if self._repository.is_candle_processed(symbol, timeframe.value, candle_timestamp):
                return TradingCycleResult(
                    status=CycleStatus.SKIPPED,
                    candle_timestamp=candle_timestamp,
                    message="Candle already processed",
                )

            if not self._repository.try_claim_candle(symbol, timeframe.value, candle_timestamp):
                return TradingCycleResult(
                    status=CycleStatus.SKIPPED,
                    candle_timestamp=candle_timestamp,
                    message="Candle already claimed by another worker",
                )

            return self._process_closed_candle(
                symbol=symbol,
                timeframe=timeframe,
                candle_timestamp=candle_timestamp,
                bars=bars,
                closed_candle=closed_candle,
            )
        except Exception as exc:
            logger.exception("engine_unexpected_error", error=str(exc))
            return self._pause(PauseReason.UNEXPECTED_ERROR, str(exc), exc=exc)

    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("engine_shutdown", paused=self._paused, pause_reason=self._pause_reason)
        if self._broker.is_connected():
            self._broker.disconnect()
        if hasattr(self._repository, "close"):
            self._repository.close()

    def _process_closed_candle(
        self,
        *,
        symbol: str,
        timeframe: Timeframe,
        candle_timestamp: datetime,
        bars: Any,
        closed_candle: Any,
    ) -> TradingCycleResult:
        evaluation_bars = bars_through_closed_candle(bars, closed_candle)

        try:
            indicators = IndicatorCalculator.compute(evaluation_bars)
        except ValueError as exc:
            return self._pause(PauseReason.MARKET_DATA_UNAVAILABLE, str(exc), exc=exc)

        self._persist_stage(symbol, timeframe.value, candle_timestamp, "INDICATORS", indicators)

        try:
            signal = self._strategy.evaluate(evaluation_bars, indicators)
        except Exception as exc:
            return self._pause(PauseReason.STRATEGY_ERROR, str(exc), exc=exc)

        self._persist_stage(symbol, timeframe.value, candle_timestamp, "SIGNAL", signal)

        try:
            account = self._broker.get_account_info()
            symbol_info = self._broker.get_symbol_info(symbol)
            open_positions = self._broker.get_open_positions(symbol)
            risk_state = self._repository.load_risk_state() or RiskState.from_equity(account.equity)
            risk_decision = self._risk_manager.assess(
                signal,
                account,
                symbol_info,
                open_positions,
                risk_state,
            )
        except Exception as exc:
            return self._pause(PauseReason.RISK_ERROR, str(exc), exc=exc)

        risk_outcome = risk_rejection_reason(risk_decision)
        self._persist_stage(
            symbol,
            timeframe.value,
            candle_timestamp,
            "RISK_DECISION",
            {"outcome": risk_outcome, "approved": is_risk_approved(risk_decision)},
        )

        order_result = None
        if isinstance(risk_decision, ApprovedOrderPlan):
            try:
                context = OrderExecutionContext(
                    account=account,
                    symbol_info=symbol_info,
                    open_positions=open_positions,
                    risk_state=risk_state,
                    entry_price=signal.entry_price,
                )
                order_result = self._order_manager.open_market_order(risk_decision, context)
            except Exception as exc:
                return self._pause(PauseReason.EXECUTION_ERROR, str(exc), exc=exc)

            self._persist_stage(
                symbol,
                timeframe.value,
                candle_timestamp,
                "ORDER",
                order_result,
            )

            if not order_result.success and not order_result.dry_run:
                return self._pause(
                    PauseReason.EXECUTION_ERROR,
                    order_result.error_message or "Order execution failed",
                )

        try:
            positions_after = self._broker.get_open_positions(symbol)
            reconciliation = self._order_manager.reconcile_positions(positions_after)
        except Exception as exc:
            return self._pause(PauseReason.EXECUTION_ERROR, str(exc), exc=exc)

        self._persist_stage(
            symbol,
            timeframe.value,
            candle_timestamp,
            "EXECUTION",
            {
                "order_success": order_result.success if order_result else None,
                "reconciliation": reconciliation,
            },
        )

        updated_state = RiskState(
            day_start_equity=risk_state.day_start_equity,
            peak_equity=max(risk_state.peak_equity, account.equity),
        )
        self._repository.save_risk_state(updated_state)

        logger.info(
            "trading_cycle_complete",
            symbol=symbol,
            timeframe=timeframe.value,
            candle_timestamp=candle_timestamp.isoformat(),
            signal_action=signal.action.value,
            signal_reason=signal.reason,
            risk_outcome=risk_outcome,
            order_success=order_result.success if order_result else None,
            order_dry_run=order_result.dry_run if order_result else None,
            reconciliation_count=len(reconciliation),
        )

        return TradingCycleResult(
            status=CycleStatus.COMPLETED,
            candle_timestamp=candle_timestamp,
            indicators=indicators,
            signal=signal,
            risk_outcome=risk_outcome,
            order_result=order_result,
            reconciliation=reconciliation,
            message="Trading cycle completed",
        )

    def _persist_stage(
        self,
        symbol: str,
        timeframe: str,
        candle_timestamp: datetime,
        stage: str,
        payload: object,
    ) -> None:
        try:
            self._repository.save_event(
                TradingEventRecord(
                    symbol=symbol,
                    timeframe=timeframe,
                    candle_timestamp=candle_timestamp,
                    stage=stage,
                    payload=_serialize_payload(payload),
                    created_at=datetime.now(tz=UTC),
                )
            )
        except Exception as exc:
            msg = f"Failed to persist {stage} event: {exc}"
            raise RuntimeError(msg) from exc

    def _pause(
        self,
        reason: PauseReason,
        message: str,
        *,
        exc: Exception | None = None,
    ) -> TradingCycleResult:
        self._set_paused(reason, message)
        if exc is not None:
            logger.error("engine_paused", reason=reason.value, message=message, error=str(exc))
        else:
            logger.error("engine_paused", reason=reason.value, message=message)
        return TradingCycleResult(
            status=CycleStatus.PAUSED,
            message=message,
            paused=True,
            pause_reason=reason,
        )

    def _set_paused(self, reason: PauseReason, message: str) -> None:
        self._paused = True
        self._pause_reason = reason
        logger.warning("engine_pause_set", reason=reason.value, message=message)


def _serialize_payload(payload: object) -> dict[str, Any]:
    if isinstance(payload, BaseModel):
        dumped = payload.model_dump(mode="json")
        return dumped
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"items": payload}
    return {"value": str(payload)}
