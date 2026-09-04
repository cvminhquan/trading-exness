"""Live closed-candle engine — market data only, no strategy or orders."""

from __future__ import annotations

import threading
from datetime import datetime

import structlog

from exness_bot.candle_engine.events import (
    CandlePollResult,
    CandlePollStatus,
    ClosedCandleEvent,
    candle_idempotency_key,
)
from exness_bot.candle_engine.state import CandleCursor, CandleStateStore
from exness_bot.data.models import ProviderConnectionStatus
from exness_bot.data.provider import TradingDataProvider
from exness_bot.domain.clock import Clock, SystemClock
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_data.candles import (
    closed_candles_only,
    normalize_timestamp,
    timeframe_duration,
    validate_live_candle,
)

logger = structlog.get_logger(__name__)


class CandleEngine:
    """Poll closed M15 candles exactly once. Never emit the forming bar."""

    def __init__(
        self,
        provider: TradingDataProvider,
        store: CandleStateStore,
        *,
        symbol: str,
        timeframe: Timeframe = Timeframe.M15,
        history_count: int = 64,
        clock: Clock | None = None,
        source: str | None = None,
    ) -> None:
        self._provider = provider
        self._store = store
        self._symbol = symbol.strip().upper()
        self._timeframe = timeframe
        self._history_count = max(2, history_count)
        self._clock = clock or SystemClock()
        self._source = source or provider.data_source.value
        self._lock = threading.Lock()
        self._last_result: CandlePollResult | None = None
        self._last_closed: Candle | None = None
        self._last_update: datetime | None = None
        self._broker_was_down = False

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> Timeframe:
        return self._timeframe

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            cursor = self._store.load()
            last_closed = self._last_closed
            last_update = self._last_update
            last_result = self._last_result
        status = "RUNNING"
        if last_result is not None and last_result.status in {
            CandlePollStatus.BROKER_DISCONNECTED,
            CandlePollStatus.DATA_UNAVAILABLE,
        }:
            status = "DISCONNECTED"
        return {
            "status": status,
            "last_processed": cursor.last_processed_timestamp,
            "last_closed": last_closed.timestamp if last_closed else None,
            "last_update": last_update,
            "data_source": self._source,
            "last_status": last_result.status.value if last_result else None,
        }

    def poll(self) -> CandlePollResult:
        now = self._clock.now_utc()
        result = self._poll(now)
        with self._lock:
            self._last_result = result
            self._last_update = now
        return result

    def _poll(self, now: datetime) -> CandlePollResult:
        snapshot = self._provider.get_snapshot()
        if self._provider.requires_live_broker() and snapshot.connection_status in {
            ProviderConnectionStatus.DISCONNECTED,
            ProviderConnectionStatus.UNAVAILABLE,
            ProviderConnectionStatus.ERROR,
        }:
            if not self._broker_was_down:
                logger.warning(
                    "candle_engine_mt5_unavailable",
                    connection=snapshot.connection_status.value,
                )
                self._broker_was_down = True
            return CandlePollResult(
                status=CandlePollStatus.BROKER_DISCONNECTED,
                message="MT5 chưa kết nối.",
            )

        candles = self._provider.get_candles(self._symbol, self._timeframe, self._history_count)
        if candles is None:
            if not self._broker_was_down:
                logger.warning("candle_engine_mt5_unavailable", reason="candles_none")
                self._broker_was_down = True
            return CandlePollResult(
                status=CandlePollStatus.DATA_UNAVAILABLE,
                message="Không lấy được nến từ provider.",
            )

        if self._broker_was_down:
            logger.info("candle_engine_mt5_reconnected")
            self._broker_was_down = False

        if not candles:
            return CandlePollResult(
                status=CandlePollStatus.DATA_UNAVAILABLE,
                message="Provider trả về danh sách nến rỗng.",
            )

        closed = closed_candles_only(candles, self._timeframe, now=now)
        if not closed:
            return CandlePollResult(
                status=CandlePollStatus.NO_CLOSED_CANDLE,
                message="Chưa có nến đóng.",
            )

        latest = closed[-1]
        with self._lock:
            self._last_closed = latest.model_copy(
                update={"timestamp": normalize_timestamp(latest.timestamp)}
            )

        cursor = self._store.load()
        last_processed = cursor.last_processed_timestamp
        if last_processed is not None:
            last_processed = normalize_timestamp(last_processed)

        if last_processed is None:
            self._persist(normalize_timestamp(latest.timestamp))
            logger.info(
                "candle_engine_warm_start",
                symbol=self._symbol,
                timeframe=self._timeframe.value,
                seeded_at=latest.timestamp.isoformat(),
            )
            return CandlePollResult(
                status=CandlePollStatus.CANDLE_ALREADY_PROCESSED,
                message="Khởi động: neo con trỏ tại nến đóng mới nhất, không phát sự kiện lịch sử.",
                latest_closed_at=latest.timestamp,
            )

        pending = [
            candle
            for candle in closed
            if normalize_timestamp(candle.timestamp) > last_processed
        ]
        if not pending:
            logger.debug(
                "candle_engine_already_processed",
                timestamp=latest.timestamp.isoformat(),
            )
            return CandlePollResult(
                status=CandlePollStatus.CANDLE_ALREADY_PROCESSED,
                message="Nến đóng mới nhất đã xử lý.",
                latest_closed_at=latest.timestamp,
            )

        events: list[ClosedCandleEvent] = []
        previous = last_processed
        step = timeframe_duration(self._timeframe)
        for candle in pending:
            error = validate_live_candle(candle, symbol=self._symbol, timeframe=self._timeframe)
            if error is not None:
                logger.warning(
                    "candle_engine_invalid_candle",
                    reason=error,
                    timestamp=candle.timestamp.isoformat(),
                )
                if not events:
                    return CandlePollResult(
                        status=CandlePollStatus.INVALID_CANDLE,
                        message=f"Nến không hợp lệ: {error}.",
                        latest_closed_at=latest.timestamp,
                    )
                break

            stamp = normalize_timestamp(candle.timestamp)
            if stamp <= previous:
                logger.warning(
                    "candle_engine_non_monotonic",
                    timestamp=stamp.isoformat(),
                    previous=previous.isoformat(),
                )
                continue

            gap = stamp - previous
            if gap > step * 1.001:
                logger.info(
                    "candle_engine_session_gap",
                    from_ts=previous.isoformat(),
                    to_ts=stamp.isoformat(),
                )

            utc_candle = candle.model_copy(update={"timestamp": stamp})
            key = candle_idempotency_key(
                self._symbol,
                self._timeframe.value,
                stamp,
            )
            event = ClosedCandleEvent(
                candle=utc_candle,
                detected_at=now,
                source=self._source,
                idempotency_key=key,
            )
            events.append(event)
            self._persist(stamp)
            previous = stamp
            logger.info(
                "candle_engine_closed_candle_detected",
                symbol=self._symbol,
                timeframe=self._timeframe.value,
                timestamp=candle.timestamp.isoformat(),
            )
            logger.info(
                "candle_engine_closed_candle_processed",
                idempotency_key=key,
            )

        if not events:
            return CandlePollResult(
                status=CandlePollStatus.CANDLE_ALREADY_PROCESSED,
                latest_closed_at=latest.timestamp,
            )
        return CandlePollResult(
            status=CandlePollStatus.CANDLE_PROCESSED,
            events=tuple(events),
            message=f"Đã xử lý {len(events)} nến đóng.",
            latest_closed_at=latest.timestamp,
        )

    def _persist(self, timestamp: datetime) -> None:
        self._store.save(
            CandleCursor(
                symbol=self._symbol,
                timeframe=self._timeframe.value,
                last_processed_timestamp=normalize_timestamp(timestamp),
            )
        )
