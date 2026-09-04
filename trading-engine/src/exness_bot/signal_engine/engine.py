"""Live Signal Engine — closed candles only, no orders."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pandas as pd
import structlog

from exness_bot.candle_engine.events import ClosedCandleEvent
from exness_bot.data.provider import TradingDataProvider
from exness_bot.domain.clock import Clock, SystemClock
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, IndicatorSnapshot
from exness_bot.indicators.calculator import IndicatorCalculator
from exness_bot.market_data.candles import (
    candles_to_dataframe,
    closed_candles_only,
    is_candle_closed,
    normalize_timestamp,
    validate_live_candle,
)
from exness_bot.signal_engine.adapter import (
    build_conditions,
    indicators_are_valid,
    map_action,
)
from exness_bot.signal_engine.models import (
    SignalCycleResult,
    SignalCycleStatus,
    SignalEmission,
    SignalKind,
    SignalResult,
    signal_idempotency_key,
)
from exness_bot.signal_engine.state import SignalCursor, SignalStateStore
from exness_bot.strategy.base import Strategy
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME

logger = structlog.get_logger(__name__)

ComputeSnapshot = Callable[[pd.DataFrame], IndicatorSnapshot]


class SignalEngine:
    """Evaluate ema_rsi_atr_v1 on ClosedCandleEvent. Never executes trades."""

    def __init__(
        self,
        store: SignalStateStore,
        strategy: Strategy,
        *,
        symbol: str,
        timeframe: Timeframe,
        warmup_bars: int,
        clock: Clock | None = None,
        source: str = "MOCK",
        provider: TradingDataProvider | None = None,
        history_count: int = 250,
        compute_snapshot: ComputeSnapshot | None = None,
        rsi_long_min: float = 50.0,
        rsi_long_max: float = 70.0,
    ) -> None:
        self._store = store
        self._strategy = strategy
        self._symbol = symbol.strip().upper()
        self._timeframe = timeframe
        self._warmup_bars = warmup_bars
        self._clock = clock or SystemClock()
        self._source = source
        self._provider = provider
        self._history_count = max(warmup_bars + 2, history_count)
        self._compute = compute_snapshot or IndicatorCalculator.compute
        self._rsi_long_min = rsi_long_min
        self._rsi_long_max = rsi_long_max
        self._history: list[Candle] = []
        self._last_result: SignalResult | None = None

    @property
    def history(self) -> tuple[Candle, ...]:
        return tuple(self._history)

    @property
    def strategy_name(self) -> str:
        return self._strategy.name

    @property
    def last_result(self) -> SignalResult | None:
        return self._last_result

    def snapshot(self) -> dict[str, object]:
        cursor = self._store.load()
        last = self._last_result
        return {
            "status": "RUNNING" if self._history else "STOPPED",
            "strategy": self.strategy_name,
            "last_processed": cursor.last_processed_timestamp,
            "last_signal": last.signal.value if last else None,
            "last_signal_at": last.generated_at if last else None,
            "last_candle": last.candle_timestamp if last else None,
            "data_source": self._source,
            "indicators": last.indicators if last else None,
            "reason": last.reason if last else None,
            "actionable": last.actionable if last else False,
        }

    def warmup(self, candles: list[Candle], *, now: datetime | None = None) -> SignalCycleResult:
        reference = now or self._clock.now_utc()
        closed = closed_candles_only(candles, self._timeframe, now=reference)
        if len(closed) <= self._warmup_bars:
            logger.warning(
                "insufficient_history",
                count=len(closed),
                warmup_bars=self._warmup_bars,
            )
            return SignalCycleResult(
                status=SignalCycleStatus.INSUFFICIENT_HISTORY,
                message="Chưa đủ nến đóng để warmup chỉ báo.",
            )
        self._history = list(closed)
        stored = self._store.load()
        if stored.last_processed_timestamp is not None:
            logger.info("signal_engine_started", mode="warm", strategy=self.strategy_name)
            return SignalCycleResult(
                status=SignalCycleStatus.WARMUP_COMPLETE,
                message="Warm start: đã khôi phục cursor, không phát tín hiệu lịch sử.",
            )
        self._persist(normalize_timestamp(closed[-1].timestamp))
        logger.info("signal_engine_started", mode="cold", strategy=self.strategy_name)
        return SignalCycleResult(
            status=SignalCycleStatus.WARMUP_COMPLETE,
            message="Cold start: warmup chỉ báo, không phát tín hiệu lịch sử.",
        )

    def warmup_from_provider(self) -> SignalCycleResult:
        if self._provider is None:
            return SignalCycleResult(
                status=SignalCycleStatus.DATA_UNAVAILABLE,
                message="Không có data provider.",
            )
        candles = self._provider.get_candles(self._symbol, self._timeframe, self._history_count)
        if candles is None:
            return SignalCycleResult(
                status=SignalCycleStatus.DATA_UNAVAILABLE,
                message="Không lấy được nến từ provider.",
            )
        return self.warmup(candles)

    def process_events(
        self,
        events: tuple[ClosedCandleEvent, ...],
        *,
        now: datetime | None = None,
    ) -> SignalCycleResult:
        reference = now or self._clock.now_utc()
        if not self._history:
            return SignalCycleResult(
                status=SignalCycleStatus.INSUFFICIENT_HISTORY,
                message="Chưa warmup.",
            )
        ordered = sorted(events, key=lambda item: normalize_timestamp(item.candle.timestamp))
        cursor = self._store.load().last_processed_timestamp
        pending: list[ClosedCandleEvent] = []
        saw_forming = False
        for event in ordered:
            candle = event.candle
            stamp = normalize_timestamp(candle.timestamp)
            if cursor is not None and stamp <= normalize_timestamp(cursor):
                continue
            if not is_candle_closed(stamp, self._timeframe, now=reference):
                saw_forming = True
                continue
            error = validate_live_candle(candle, symbol=self._symbol, timeframe=self._timeframe)
            if error is not None:
                logger.warning("invalid_indicator", reason="invalid_candle", detail=error)
                return SignalCycleResult(
                    status=SignalCycleStatus.INVALID_CANDLE,
                    message=f"Nến không hợp lệ: {error}.",
                )
            pending.append(event)
        if not pending:
            if saw_forming:
                return SignalCycleResult(
                    status=SignalCycleStatus.FORMING_REJECTED,
                    message="Bỏ qua nến đang hình thành.",
                )
            return SignalCycleResult(
                status=SignalCycleStatus.ALREADY_PROCESSED,
                message="Sự kiện nến đã xử lý.",
            )

        *stale, latest = pending
        for event in stale:
            self._append(event.candle)
            self._persist(normalize_timestamp(event.candle.timestamp))
            logger.debug(
                "indicator_calculation",
                mode="catchup",
                timestamp=event.candle.timestamp.isoformat(),
            )

        result = self._emit(latest.candle, now=reference)
        return SignalCycleResult(
            status=(
                SignalCycleStatus.SIGNAL_EMITTED
                if result.signal in {SignalKind.BUY, SignalKind.SELL}
                else (
                    SignalCycleStatus.INVALID_INDICATOR
                    if result.signal == SignalKind.INVALID
                    else SignalCycleStatus.NO_SIGNAL
                )
            ),
            results=(result,),
            catchup_count=len(stale),
            message=result.reason,
        )

    def _emit(self, candle: Candle, *, now: datetime) -> SignalResult:
        self._append(candle)
        stamp = normalize_timestamp(candle.timestamp)
        frame = candles_to_dataframe(
            [item for item in self._history if normalize_timestamp(item.timestamp) <= stamp]
        )
        snapshot = self._compute(frame)
        logger.debug(
            "indicator_calculation",
            mode="emit",
            timestamp=stamp.isoformat(),
            ema_20=snapshot.ema_20,
            ema_50=snapshot.ema_50,
            ema_200=snapshot.ema_200,
            rsi_14=snapshot.rsi_14,
            atr_14=snapshot.atr_14,
        )
        valid, missing = indicators_are_valid(snapshot)
        generated_at = now
        key = signal_idempotency_key(self._symbol, self._timeframe.value, stamp, self.strategy_name)
        if not valid:
            logger.warning("invalid_indicator", missing=list(missing))
            logger.debug(
                "indicator_calculation",
                timestamp=stamp.isoformat(),
                ema_20=snapshot.ema_20,
                rsi_14=snapshot.rsi_14,
                atr_14=snapshot.atr_14,
            )
            result = SignalResult(
                symbol=self._symbol,
                timeframe=self._timeframe.value,
                candle_timestamp=stamp,
                signal=SignalKind.INVALID,
                generated_at=generated_at,
                source=self._source,
                strategy=self.strategy_name,
                indicators=snapshot,
                reason=f"Chỉ báo không hợp lệ: {', '.join(missing)}.",
                conditions=(),
                idempotency_key=key,
                emission=SignalEmission.SIGNAL_EMISSION,
                actionable=False,
                executable=False,
            )
            self._last_result = result
            self._persist(stamp)
            return result

        signal = self._strategy.evaluate(frame, snapshot)
        kind = map_action(signal.action)
        actionable = kind in {SignalKind.BUY, SignalKind.SELL}
        if actionable:
            logger.info(
                "new_signal",
                signal=kind.value,
                timestamp=stamp.isoformat(),
                strategy=self.strategy_name,
            )
        else:
            logger.debug("no_signal", timestamp=stamp.isoformat(), reason=signal.reason)
        result = SignalResult(
            symbol=self._symbol,
            timeframe=self._timeframe.value,
            candle_timestamp=stamp,
            signal=kind,
            generated_at=generated_at,
            source=self._source,
            strategy=self.strategy_name or STRATEGY_NAME,
            indicators=snapshot,
            reason=signal.reason,
            conditions=build_conditions(
                signal,
                rsi_long_min=self._rsi_long_min,
                rsi_long_max=self._rsi_long_max,
            ),
            idempotency_key=key,
            emission=SignalEmission.SIGNAL_EMISSION,
            actionable=actionable,
            executable=actionable,
        )
        self._last_result = result
        self._persist(stamp)
        return result

    def _append(self, candle: Candle) -> None:
        stamp = normalize_timestamp(candle.timestamp)
        self._history = [
            item for item in self._history if normalize_timestamp(item.timestamp) < stamp
        ]
        self._history.append(candle.model_copy(update={"timestamp": stamp}))
        self._history.sort(key=lambda item: item.timestamp)

    def _persist(self, timestamp: datetime) -> None:
        self._store.save(
            SignalCursor(
                symbol=self._symbol,
                timeframe=self._timeframe.value,
                strategy=self.strategy_name,
                last_processed_timestamp=timestamp,
            )
        )
