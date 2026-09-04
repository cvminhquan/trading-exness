"""Deterministic tests for the live closed-candle engine — no real MT5."""

from __future__ import annotations

import inspect
import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from exness_bot.candle_engine.engine import CandleEngine
from exness_bot.candle_engine.events import CandlePollResult, CandlePollStatus
from exness_bot.candle_engine.loop import run_polling_loop
from exness_bot.candle_engine.state import (
    CandleCursor,
    FileCandleStateStore,
    InMemoryCandleStateStore,
)
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
    TradeHistoryQuery,
    TradeHistoryResult,
)
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, Tick
from exness_bot.market_data.candles import is_candle_closed

SYMBOL = "XAUUSD"
TF = Timeframe.M15
PLUS7 = timezone(timedelta(hours=7))


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 29, hour, minute, second, tzinfo=UTC)


def _candle(
    open_ts: datetime,
    *,
    open_px: float = 2349.0,
    high: float = 2351.0,
    low: float = 2348.0,
    close: float = 2350.0,
    symbol: str = SYMBOL,
    timeframe: Timeframe = TF,
    volume: float = 100.0,
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=open_ts,
        open=open_px,
        high=high,
        low=low,
        close=close,
        volume=volume,
        spread=20,
        tick_volume=volume,
        real_volume=0.0,
    )


class FakeTradingDataProvider:
    """In-memory provider for CandleEngine tests."""

    def __init__(self) -> None:
        self.connected = True
        self.candles: list[Candle] = []
        self.unavailable = False

    @property
    def data_source(self) -> DataSourceMode:
        return DataSourceMode.MT5

    def requires_live_broker(self) -> bool:
        return True

    def get_snapshot(self) -> ProviderSnapshot:
        status = (
            ProviderConnectionStatus.CONNECTED
            if self.connected
            else ProviderConnectionStatus.DISCONNECTED
        )
        return ProviderSnapshot(
            connection_status=status,
            data_source=DataSourceMode.MT5,
            account=None,
            positions=(),
            updated_at=datetime.now(tz=UTC),
            message=None if self.connected else "Mất kết nối MT5.",
        )

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        return None

    def get_trade_history(self, query: TradeHistoryQuery) -> TradeHistoryResult:
        return TradeHistoryResult(trades=(), total=0, updated_at=datetime.now(tz=UTC))

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[Candle] | None:
        if not self.connected or self.unavailable:
            return None
        return list(self.candles)


def _engine(
    provider: FakeTradingDataProvider,
    clock: FakeClock,
    *,
    store: InMemoryCandleStateStore | FileCandleStateStore | None = None,
    cursor: datetime | None = None,
) -> CandleEngine:
    resolved = store or InMemoryCandleStateStore(
        CandleCursor(
            symbol=SYMBOL,
            timeframe=TF.value,
            last_processed_timestamp=cursor,
        )
    )
    return CandleEngine(
        provider,
        resolved,
        symbol=SYMBOL,
        timeframe=TF,
        history_count=16,
        clock=clock,
        source="MT5",
    )


def _timestamps(result: CandlePollResult) -> list[datetime]:
    return [event.candle.timestamp for event in result.events]


class TestClosedCandleDetection:
    def test_forming_candle_is_ignored(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 0))]
        clock = FakeClock(_at(10, 14, 59))
        engine = _engine(provider, clock, cursor=_at(9, 45))
        result = engine.poll()
        assert result.status == CandlePollStatus.NO_CLOSED_CANDLE
        assert result.events == ()

    def test_closed_candle_is_detected(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15))]
        clock = FakeClock(_at(10, 15, 0))
        engine = _engine(provider, clock, cursor=_at(9, 45))
        result = engine.poll()
        assert result.status == CandlePollStatus.CANDLE_PROCESSED
        assert _timestamps(result) == [_at(10, 0)]

    def test_exact_candle_boundary(self) -> None:
        open_time = _at(10, 0)
        assert is_candle_closed(open_time, TF, now=_at(10, 14, 59)) is False
        assert is_candle_closed(open_time, TF, now=_at(10, 15, 0)) is True
        clock = FakeClock(_at(10, 15, 0))
        assert is_candle_closed(open_time, TF, clock=clock) is True


class TestIdempotency:
    def test_closed_candle_processed_once(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15))]
        clock = FakeClock(_at(10, 16))
        engine = _engine(provider, clock, cursor=_at(9, 45))
        first = engine.poll()
        assert _timestamps(first) == [_at(10, 0)]
        second = engine.poll()
        assert second.status == CandlePollStatus.CANDLE_ALREADY_PROCESSED
        assert second.events == ()

    def test_repeated_polling_does_not_duplicate(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15))]
        clock = FakeClock(_at(10, 31))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        stamps: list[datetime] = []
        for _ in range(5):
            stamps.extend(_timestamps(engine.poll()))
        assert stamps == [_at(10, 15)]

    def test_next_candle_processes_once(self) -> None:
        provider = FakeTradingDataProvider()
        clock = FakeClock(_at(10, 31))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15)), _candle(_at(10, 30))]
        first = engine.poll()
        assert _timestamps(first) == [_at(10, 15)]
        assert engine.poll().events == ()
        clock.set(_at(10, 46))
        provider.candles.append(_candle(_at(10, 45)))
        assert _timestamps(engine.poll()) == [_at(10, 30)]
        clock.set(_at(11, 1))
        provider.candles.append(_candle(_at(11, 0)))
        assert _timestamps(engine.poll()) == [_at(10, 45)]


class TestMissedAndReconnect:
    def test_multiple_missed_candles_process_chronologically(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [
            _candle(_at(10, 45)),
            _candle(_at(10, 15)),
            _candle(_at(10, 30)),
            _candle(_at(11, 0)),
        ]
        clock = FakeClock(_at(11, 2))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        result = engine.poll()
        assert _timestamps(result) == [_at(10, 15), _at(10, 30), _at(10, 45)]

    def test_mt5_disconnect_does_not_reset_cursor(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15))]
        clock = FakeClock(_at(10, 16))
        engine = _engine(provider, clock, cursor=_at(9, 45))
        engine.poll()
        provider.connected = False
        disconnected = engine.poll()
        assert disconnected.status == CandlePollStatus.BROKER_DISCONNECTED
        assert disconnected.events == ()
        assert engine.snapshot()["last_processed"] == _at(10, 0)

    def test_mt5_reconnect_processes_missing_closed_once(self) -> None:
        provider = FakeTradingDataProvider()
        clock = FakeClock(_at(10, 31))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15))]
        assert _timestamps(engine.poll()) == [_at(10, 15)]
        provider.connected = False
        engine.poll()
        provider.connected = True
        clock.set(_at(10, 32))
        provider.candles = [_candle(_at(10, 15)), _candle(_at(10, 30))]
        assert engine.poll().events == ()
        clock.set(_at(10, 45))
        provider.candles = [_candle(_at(10, 15)), _candle(_at(10, 30)), _candle(_at(10, 45))]
        assert _timestamps(engine.poll()) == [_at(10, 30)]
        assert engine.poll().events == ()


class TestValidation:
    def test_malformed_candle_rejected(self) -> None:
        provider = FakeTradingDataProvider()
        bad = _candle(_at(10, 15), high=2340.0, low=2348.0, open_px=2349.0, close=2350.0)
        provider.candles = [_candle(_at(10, 0)), bad]
        clock = FakeClock(_at(10, 31))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        result = engine.poll()
        assert result.status == CandlePollStatus.INVALID_CANDLE
        assert result.events == ()
        assert engine.snapshot()["last_processed"] == _at(10, 0)

    def test_duplicate_candle_rejected(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [
            _candle(_at(10, 15), close=2350.0),
            _candle(_at(10, 15), close=2399.0),
        ]
        clock = FakeClock(_at(10, 31))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        result = engine.poll()
        assert _timestamps(result) == [_at(10, 15)]
        assert result.events[0].candle.close == 2350.0
        assert engine.poll().events == ()

    def test_non_monotonic_candles_sorted_oldest_first(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 30)), _candle(_at(10, 15))]
        clock = FakeClock(_at(10, 45))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        assert _timestamps(engine.poll()) == [_at(10, 15), _at(10, 30)]

    def test_utc_normalization(self) -> None:
        provider = FakeTradingDataProvider()
        local_open = datetime(2026, 8, 29, 17, 15, tzinfo=PLUS7)
        provider.candles = [_candle(local_open)]
        clock = FakeClock(_at(10, 31))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        result = engine.poll()
        assert _timestamps(result) == [_at(10, 15)]
        assert result.events[0].candle.timestamp.tzinfo is UTC

    def test_naive_timestamp_treated_as_utc(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(datetime(2026, 8, 29, 10, 15))]
        clock = FakeClock(_at(10, 31))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        assert _timestamps(engine.poll()) == [_at(10, 15)]

    def test_normal_market_session_gap(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 15)), _candle(_at(11, 0))]
        clock = FakeClock(_at(11, 16))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        result = engine.poll()
        assert result.status == CandlePollStatus.CANDLE_PROCESSED
        assert _timestamps(result) == [_at(10, 15), _at(11, 0)]

    def test_no_look_ahead_forming_values_not_emitted(self) -> None:
        provider = FakeTradingDataProvider()
        forming = _candle(_at(10, 30), close=9999.0, high=10000.0)
        provider.candles = [_candle(_at(10, 15), close=2350.0), forming]
        clock = FakeClock(_at(10, 31))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        result = engine.poll()
        assert _timestamps(result) == [_at(10, 15)]
        assert all(event.candle.close != 9999.0 for event in result.events)
        close_delta = timedelta(minutes=15)
        for event in result.events:
            assert event.candle.timestamp + close_delta <= clock.now_utc()


class TestRestartAndClock:
    def test_restart_does_not_reemit(self, tmp_path: Path) -> None:
        store = FileCandleStateStore(tmp_path / "state.json", symbol=SYMBOL, timeframe=TF.value)
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15))]
        clock = FakeClock(_at(10, 16))
        first = _engine(provider, clock, store=store)
        assert first.poll().events == ()
        second = _engine(provider, clock, store=store)
        assert second.poll().events == ()
        clock.set(_at(10, 31))
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15)), _candle(_at(10, 30))]
        assert _timestamps(second.poll()) == [_at(10, 15)]

    def test_warm_start_seeds_without_emitting(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15))]
        clock = FakeClock(_at(10, 16))
        engine = _engine(provider, clock)
        result = engine.poll()
        assert result.status == CandlePollStatus.CANDLE_ALREADY_PROCESSED
        assert result.events == ()
        assert engine.snapshot()["last_processed"] == _at(10, 0)

    def test_deterministic_fake_clock(self) -> None:
        clock = FakeClock(_at(10, 0))
        clock.advance(timedelta(minutes=15))
        assert clock.now_utc() == _at(10, 15)
        clock.set(_at(11, 0))
        assert clock.now_utc() == _at(11, 0)

    def test_data_unavailable(self) -> None:
        provider = FakeTradingDataProvider()
        provider.unavailable = True
        clock = FakeClock(_at(10, 16))
        engine = _engine(provider, clock, cursor=_at(10, 0))
        assert engine.poll().status == CandlePollStatus.DATA_UNAVAILABLE

    def test_graceful_shutdown(self) -> None:
        provider = FakeTradingDataProvider()
        provider.candles = [_candle(_at(10, 0))]
        clock = FakeClock(_at(10, 16))
        engine = _engine(provider, clock, cursor=_at(9, 45))
        stop = threading.Event()
        thread = threading.Thread(
            target=run_polling_loop,
            args=(engine, 0.05),
            kwargs={"stop_event": stop},
            daemon=True,
        )
        thread.start()
        stop.set()
        thread.join(timeout=2)
        assert not thread.is_alive()


class TestIntegrationFakeProvider:
    def test_closed_events_ten_fifteen_and_ten_forty_five_once(self) -> None:
        provider = FakeTradingDataProvider()
        clock = FakeClock(_at(10, 10))
        engine = _engine(provider, clock)
        emitted: list[datetime] = []

        provider.candles = [_candle(_at(10, 0))]
        emitted.extend(_timestamps(engine.poll()))

        clock.set(_at(10, 16))
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15))]
        emitted.extend(_timestamps(engine.poll()))

        clock.set(_at(10, 31))
        provider.candles = [_candle(_at(10, 0)), _candle(_at(10, 15)), _candle(_at(10, 30))]
        emitted.extend(_timestamps(engine.poll()))
        emitted.extend(_timestamps(engine.poll()))

        clock.set(_at(10, 40))
        emitted.extend(_timestamps(engine.poll()))

        clock.set(_at(11, 1))
        # Fake feed for spec §30: 10:30 was only observed while forming.
        provider.candles = [
            _candle(_at(10, 15)),
            _candle(_at(10, 45)),
            _candle(_at(11, 0)),
        ]
        emitted.extend(_timestamps(engine.poll()))
        emitted.extend(_timestamps(engine.poll()))

        assert emitted == [_at(10, 15), _at(10, 45)]


class TestSafetyBoundary:
    def test_candle_engine_has_no_trading_or_strategy(self) -> None:
        from exness_bot.candle_engine import engine as engine_mod
        from exness_bot.candle_engine import loop as loop_mod

        combined = inspect.getsource(engine_mod) + inspect.getsource(loop_mod)
        for forbidden in (
            "order_send",
            "TRADE_ACTION_DEAL",
            "TRADE_ACTION_PENDING",
            "TRADE_ACTION_SLTP",
            "TRADE_ACTION_REMOVE",
            "EmaRsiAtrStrategy",
        ):
            assert forbidden not in combined

