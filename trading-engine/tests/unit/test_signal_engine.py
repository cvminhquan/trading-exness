"""Deterministic Signal Engine tests — no MT5, no orders."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.candle_engine.events import ClosedCandleEvent, candle_idempotency_key
from exness_bot.config.settings import Settings
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, IndicatorSnapshot
from exness_bot.indicators.calculator import IndicatorCalculator
from exness_bot.market_data.candles import candles_to_dataframe
from exness_bot.signal_engine.engine import SignalEngine
from exness_bot.signal_engine.models import SignalCycleStatus, SignalKind
from exness_bot.signal_engine.state import InMemorySignalStateStore, SignalCursor
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME, EmaRsiAtrStrategy
from tests.fixtures.ohlc_data import make_downtrend_ohlc, make_uptrend_ohlc

SYMBOL = "XAUUSD"
TF = Timeframe.M15
STRATEGY = STRATEGY_NAME


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 29, hour, minute, tzinfo=UTC)


def _candle(
    stamp: datetime,
    *,
    close: float = 2350.0,
    open_px: float | None = None,
    high: float | None = None,
    low: float | None = None,
) -> Candle:
    open_px = close - 0.5 if open_px is None else open_px
    high = max(open_px, close) + 1.0 if high is None else high
    low = min(open_px, close) - 1.0 if low is None else low
    return Candle(
        symbol=SYMBOL,
        timeframe=TF,
        timestamp=stamp,
        open=open_px,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        spread=20,
        tick_volume=100.0,
        real_volume=0.0,
    )


def _series(
    start: datetime,
    count: int,
    *,
    close0: float = 2000.0,
    step: float = 0.4,
) -> list[Candle]:
    return [
        _candle(start + timedelta(minutes=15 * i), close=close0 + i * step) for i in range(count)
    ]


def _event(candle: Candle, *, detected: datetime | None = None) -> ClosedCandleEvent:
    detected = detected or candle.timestamp + timedelta(minutes=15)
    return ClosedCandleEvent(
        candle=candle,
        detected_at=detected,
        source="TEST",
        idempotency_key=candle_idempotency_key(SYMBOL, TF.value, candle.timestamp),
    )


def _engine(
    clock: FakeClock,
    *,
    warmup_bars: int = 4,
    compute_snapshot: object | None = None,
    cursor: datetime | None = None,
    store: InMemorySignalStateStore | None = None,
) -> SignalEngine:
    settings = Settings(SYMBOL=SYMBOL, TIMEFRAME="M15")
    resolved = store or InMemorySignalStateStore(
        SignalCursor(
            symbol=SYMBOL,
            timeframe=TF.value,
            strategy=STRATEGY,
            last_processed_timestamp=cursor,
        )
    )
    return SignalEngine(
        store=resolved,
        strategy=EmaRsiAtrStrategy(settings),
        symbol=SYMBOL,
        timeframe=TF,
        warmup_bars=warmup_bars,
        clock=clock,
        source="TEST",
        compute_snapshot=compute_snapshot,
    )


def _buy_snapshot(bars: object) -> IndicatorSnapshot:
    import pandas as pd

    assert isinstance(bars, pd.DataFrame)
    ts = bars.iloc[-1]["timestamp"]
    return IndicatorSnapshot(
        timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
        ema_20=110.0,
        ema_50=105.0,
        ema_200=100.0,
        rsi_14=60.0,
        atr_14=2.0,
    )


def _sell_snapshot(bars: object) -> IndicatorSnapshot:
    import pandas as pd

    assert isinstance(bars, pd.DataFrame)
    ts = bars.iloc[-1]["timestamp"]
    return IndicatorSnapshot(
        timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
        ema_20=90.0,
        ema_50=95.0,
        ema_200=100.0,
        rsi_14=40.0,
        atr_14=2.0,
    )


class TestWarmupAndHistory:
    def test_insufficient_history(self) -> None:
        clock = FakeClock(_at(12, 0))
        engine = _engine(clock, warmup_bars=200)
        result = engine.warmup(_series(_at(10, 0), 10), now=clock.now_utc())
        assert result.status == SignalCycleStatus.INSUFFICIENT_HISTORY
        assert result.results == ()

    def test_indicator_warmup_emits_zero_signals(self) -> None:
        clock = FakeClock(_at(12, 0))
        engine = _engine(clock, warmup_bars=4)
        candles = _series(_at(10, 0), 5)
        result = engine.warmup(candles, now=clock.now_utc())
        assert result.status == SignalCycleStatus.WARMUP_COMPLETE
        assert result.results == ()

    def test_historical_warmup_produces_no_signals(self) -> None:
        clock = FakeClock(_at(12, 0))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        candles = [
            _candle(_at(10, 0), close=115.0),
            _candle(_at(10, 15), close=115.0),
            _candle(_at(10, 30), close=115.0),
            _candle(_at(10, 45), close=115.0),
            _candle(_at(11, 0), close=115.0),
        ]
        result = engine.warmup(candles, now=clock.now_utc())
        assert result.results == ()
        assert all(item.signal != SignalKind.BUY for item in result.results)


class TestCandleGate:
    def test_forming_candle_rejected(self) -> None:
        clock = FakeClock(_at(10, 10))
        engine = _engine(clock, warmup_bars=1)
        history = [_candle(_at(9, 30), close=115.0), _candle(_at(9, 45), close=115.0)]
        engine.warmup(history, now=_at(10, 0))
        forming = _event(_candle(_at(10, 0), close=115.0), detected=_at(10, 10))
        result = engine.process_events((forming,), now=clock.now_utc())
        assert result.status == SignalCycleStatus.FORMING_REJECTED
        assert result.results == ()

    def test_closed_candle_accepted(self) -> None:
        clock = FakeClock(_at(11, 30))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        history = _series(_at(10, 0), 5)
        engine.warmup(history, now=clock.now_utc())
        nxt = _candle(_at(11, 15), close=115.0)
        result = engine.process_events((_event(nxt),), now=clock.now_utc())
        assert result.status in {
            SignalCycleStatus.SIGNAL_EMITTED,
            SignalCycleStatus.NO_SIGNAL,
        }
        assert len(result.results) == 1
        assert result.results[0].candle_timestamp == _at(11, 15)


class TestSignals:
    def test_buy_signal(self) -> None:
        clock = FakeClock(_at(11, 30))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=115.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        assert result.results[0].signal == SignalKind.BUY
        assert result.results[0].actionable is True
        assert result.results[0].strategy == STRATEGY

    def test_sell_signal(self) -> None:
        clock = FakeClock(_at(11, 30))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_sell_snapshot)
        engine.warmup(_series(_at(10, 0), 5, step=-0.4), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=85.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        assert result.results[0].signal == SignalKind.SELL
        assert result.results[0].actionable is True

    def test_no_signal(self) -> None:
        clock = FakeClock(_at(11, 30))

        def mixed(bars: object) -> IndicatorSnapshot:
            import pandas as pd

            assert isinstance(bars, pd.DataFrame)
            ts = bars.iloc[-1]["timestamp"]
            return IndicatorSnapshot(
                timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                ema_20=105.0,
                ema_50=100.0,
                ema_200=102.0,
                rsi_14=55.0,
                atr_14=2.0,
            )

        engine = _engine(clock, warmup_bars=4, compute_snapshot=mixed)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=100.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        assert result.results[0].signal == SignalKind.NO_SIGNAL
        assert result.results[0].actionable is False


class TestInvalidIndicators:
    def test_invalid_ema(self) -> None:
        clock = FakeClock(_at(11, 30))

        def bad_ema(bars: object) -> IndicatorSnapshot:
            snap = _buy_snapshot(bars)
            return snap.model_copy(update={"ema_20": float("nan")})

        engine = _engine(clock, warmup_bars=4, compute_snapshot=bad_ema)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=115.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        assert result.status == SignalCycleStatus.INVALID_INDICATOR
        assert result.results[0].signal == SignalKind.INVALID
        assert result.results[0].actionable is False

    def test_invalid_rsi(self) -> None:
        clock = FakeClock(_at(11, 30))

        def bad_rsi(bars: object) -> IndicatorSnapshot:
            return _buy_snapshot(bars).model_copy(update={"rsi_14": None})

        engine = _engine(clock, warmup_bars=4, compute_snapshot=bad_rsi)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=115.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        assert result.results[0].signal == SignalKind.INVALID
        assert result.results[0].actionable is False

    def test_invalid_atr(self) -> None:
        clock = FakeClock(_at(11, 30))

        def bad_atr(bars: object) -> IndicatorSnapshot:
            return _buy_snapshot(bars).model_copy(update={"atr_14": None})

        engine = _engine(clock, warmup_bars=4, compute_snapshot=bad_atr)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=115.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        assert result.results[0].signal == SignalKind.INVALID

    def test_nan_handling(self) -> None:
        clock = FakeClock(_at(11, 30))

        def nan_rsi(bars: object) -> IndicatorSnapshot:
            return _buy_snapshot(bars).model_copy(update={"rsi_14": float("nan")})

        engine = _engine(clock, warmup_bars=4, compute_snapshot=nan_rsi)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=115.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        assert result.results[0].signal == SignalKind.INVALID

    def test_infinity_handling(self) -> None:
        clock = FakeClock(_at(11, 30))

        def inf_atr(bars: object) -> IndicatorSnapshot:
            return _buy_snapshot(bars).model_copy(update={"atr_14": math.inf})

        engine = _engine(clock, warmup_bars=4, compute_snapshot=inf_atr)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=115.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        assert result.results[0].signal == SignalKind.INVALID
        assert result.results[0].actionable is False


class TestLookAheadAndIdempotency:
    def test_no_look_ahead(self) -> None:
        clock = FakeClock(_at(11, 30))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        target = _at(11, 15)
        engine.process_events((_event(_candle(target, close=115.0)),), now=clock.now_utc())
        stamps = [item.timestamp for item in engine.history]
        assert max(stamps) == target
        assert all(stamp <= target for stamp in stamps)

    def test_signal_idempotency(self) -> None:
        clock = FakeClock(_at(11, 30))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        event = _event(_candle(_at(11, 15), close=115.0))
        first = engine.process_events((event,), now=clock.now_utc())
        second = engine.process_events((event,), now=clock.now_utc())
        assert len(first.results) == 1
        assert second.status == SignalCycleStatus.ALREADY_PROCESSED
        assert second.results == ()

    def test_repeated_candle(self) -> None:
        clock = FakeClock(_at(11, 30))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        event = _event(_candle(_at(11, 15), close=115.0))
        engine.process_events((event,), now=clock.now_utc())
        again = engine.process_events((event, event), now=clock.now_utc())
        assert again.results == ()

    def test_strategy_version_included_in_idempotency(self) -> None:
        clock = FakeClock(_at(11, 30))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        closed = _event(_candle(_at(11, 15), close=115.0))
        result = engine.process_events((closed,), now=clock.now_utc())
        key = result.results[0].idempotency_key
        assert STRATEGY in key
        assert "XAUUSD" in key
        assert "M15" in key


class TestStartAndCatchup:
    def test_cold_start(self) -> None:
        clock = FakeClock(_at(12, 0))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        result = engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        assert result.status == SignalCycleStatus.WARMUP_COMPLETE
        assert result.results == ()

    def test_warm_start(self, tmp_path: Path) -> None:
        from exness_bot.signal_engine.state import FileSignalStateStore

        clock = FakeClock(_at(12, 0))
        store = FileSignalStateStore(
            tmp_path / "signal.json",
            symbol=SYMBOL,
            timeframe=TF.value,
            strategy=STRATEGY,
        )
        first = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot, store=store)
        first.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        first.process_events(
            (_event(_candle(_at(11, 15), close=115.0)),),
            now=clock.now_utc(),
        )
        second = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot, store=store)
        second.warmup(_series(_at(10, 0), 6), now=clock.now_utc())
        replay = second.process_events(
            (_event(_candle(_at(11, 15), close=115.0)),),
            now=clock.now_utc(),
        )
        assert replay.status == SignalCycleStatus.ALREADY_PROCESSED
        assert replay.results == ()

    def test_missed_candle_catchup_no_burst(self) -> None:
        clock = FakeClock(_at(12, 0))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        missed = (
            _event(_candle(_at(11, 15), close=115.0)),
            _event(_candle(_at(11, 30), close=115.0)),
            _event(_candle(_at(11, 45), close=115.0)),
        )
        result = engine.process_events(missed, now=clock.now_utc())
        actionable = [item for item in result.results if item.actionable]
        assert len(actionable) == 1
        assert actionable[0].candle_timestamp == _at(11, 45)
        assert result.catchup_count == 2

    def test_reconnect_catchup_emits_only_latest(self) -> None:
        clock = FakeClock(_at(12, 0))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        warmed = engine.warmup(
            [
                _candle(_at(9, 15), close=115.0),
                _candle(_at(9, 30), close=115.0),
                _candle(_at(9, 45), close=115.0),
                _candle(_at(10, 0), close=115.0),
                _candle(_at(10, 15), close=115.0),
            ],
            now=clock.now_utc(),
        )
        assert warmed.results == ()
        reconnect = (
            _event(_candle(_at(10, 30), close=115.0)),
            _event(_candle(_at(10, 45), close=115.0)),
            _event(_candle(_at(11, 0), close=115.0)),
        )
        result = engine.process_events(reconnect, now=clock.now_utc())
        assert len(result.results) == 1
        assert result.results[0].candle_timestamp == _at(11, 0)
        assert result.catchup_count == 2
        assert result.results[0].actionable is True

    def test_chronological_processing(self) -> None:
        clock = FakeClock(_at(12, 0))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        engine.warmup(_series(_at(10, 0), 5), now=clock.now_utc())
        reversed_events = (
            _event(_candle(_at(11, 45), close=115.0)),
            _event(_candle(_at(11, 15), close=115.0)),
            _event(_candle(_at(11, 30), close=115.0)),
        )
        result = engine.process_events(reversed_events, now=clock.now_utc())
        assert result.results[0].candle_timestamp == _at(11, 45)
        stamps = [item.timestamp for item in engine.history]
        assert stamps == sorted(stamps)


class TestCriticalScenario:
    def test_warmup_five_bars_then_one_signal_at_1115(self) -> None:
        clock = FakeClock(_at(12, 0))
        engine = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        historical = [
            _candle(_at(10, 0), close=115.0),
            _candle(_at(10, 15), close=115.0),
            _candle(_at(10, 30), close=115.0),
            _candle(_at(10, 45), close=115.0),
            _candle(_at(11, 0), close=115.0),
        ]
        warmed = engine.warmup(historical, now=clock.now_utc())
        assert warmed.results == ()
        live = engine.process_events(
            (_event(_candle(_at(11, 15), close=115.0)),),
            now=clock.now_utc(),
        )
        assert len(live.results) == 1


class TestDeterminismAndConsistency:
    def test_strategy_determinism(self) -> None:
        clock = FakeClock(_at(12, 0))
        a = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        b = _engine(clock, warmup_bars=4, compute_snapshot=_buy_snapshot)
        history = _series(_at(10, 0), 5)
        a.warmup(history, now=clock.now_utc())
        b.warmup(history, now=clock.now_utc())
        event = _event(_candle(_at(11, 15), close=115.0))
        ra = a.process_events((event,), now=clock.now_utc())
        rb = b.process_events((event,), now=clock.now_utc())
        assert ra.results[0].signal == rb.results[0].signal
        assert ra.results[0].reason == rb.results[0].reason
        assert ra.results[0].idempotency_key == rb.results[0].idempotency_key

    def test_indicator_consistency_with_backtest(self) -> None:
        frame = make_uptrend_ohlc(length=220)
        stamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i) for i in range(220)]
        frame = frame.copy()
        frame["timestamp"] = stamps
        full = IndicatorCalculator.compute_all(frame)
        prefix = frame.iloc[:210]
        incremental = IndicatorCalculator.compute(prefix)
        row = full.iloc[209]
        assert incremental.ema_20 is not None
        assert abs(float(row["ema_20"]) - incremental.ema_20) < 1e-9
        assert incremental.rsi_14 is not None
        assert abs(float(row["rsi_14"]) - incremental.rsi_14) < 1e-9
        assert incremental.atr_14 is not None
        assert abs(float(row["atr_14"]) - incremental.atr_14) < 1e-9

    def test_downtrend_frame_matches_live_prefix(self) -> None:
        frame = make_downtrend_ohlc(length=220)
        frame = frame.copy()
        frame["timestamp"] = [
            datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i) for i in range(220)
        ]
        candles: list[Candle] = []
        for _, row in frame.iterrows():
            candles.append(
                _candle(
                    row["timestamp"].to_pydatetime()
                    if hasattr(row["timestamp"], "to_pydatetime")
                    else row["timestamp"],
                    close=float(row["close"]),
                    open_px=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                )
            )
        live_frame = candles_to_dataframe(candles[:210])
        backtest_snap = IndicatorCalculator.compute(frame.iloc[:210])
        live_snap = IndicatorCalculator.compute(live_frame)
        assert backtest_snap.ema_200 is not None and live_snap.ema_200 is not None
        assert abs(backtest_snap.ema_200 - live_snap.ema_200) < 1e-9


class TestSafety:
    def test_source_remains_read_only(self) -> None:
        from exness_bot.signal_engine import engine as engine_mod

        package = Path(engine_mod.__file__).resolve().parent
        forbidden = (
            "order_send",
            "TRADE_ACTION_DEAL",
            "TRADE_ACTION_PENDING",
            "TRADE_ACTION_SLTP",
            "TRADE_ACTION_REMOVE",
            "MT5Adapter",
            "MT5TradingClient",
            "TradingClient",
        )
        for path in package.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                assert token not in source, f"{path.name} contains {token}"
