"""Phase 11.5 live paper session — wired pipeline with FakeClock, no real MT5."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.candle_engine.engine import CandleEngine
from exness_bot.candle_engine.events import CandlePollStatus
from exness_bot.candle_engine.state import (
    CandleCursor,
    FileCandleStateStore,
    InMemoryCandleStateStore,
)
from exness_bot.config.settings import Settings
from exness_bot.data.models import (
    DataSourceMode,
    ProviderConnectionStatus,
    ProviderSnapshot,
    TradeHistoryQuery,
    TradeHistoryResult,
)
from exness_bot.domain.clock import FakeClock
from exness_bot.domain.enums import SignalDirection, Timeframe
from exness_bot.domain.models import AccountInfo, Candle, IndicatorSnapshot, Position, Tick
from exness_bot.paper_execution.loop import process_closed_candles
from exness_bot.paper_execution.models import RejectionCode
from exness_bot.paper_execution.pricing import simulate_entry_fill
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.paper_execution.state import FilePaperStateStore, InMemoryPaperStateStore
from exness_bot.risk.manager import RiskManager
from exness_bot.signal_engine.engine import SignalEngine
from exness_bot.signal_engine.models import SignalKind
from exness_bot.signal_engine.state import (
    FileSignalStateStore,
    InMemorySignalStateStore,
    SignalCursor,
)
from exness_bot.strategy.ema_rsi_atr import STRATEGY_NAME, EmaRsiAtrStrategy
from tests.fixtures.risk_data import make_xauusd_symbol

SYMBOL = "XAUUSD"
TF = Timeframe.M15
STRATEGY = STRATEGY_NAME


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 29, hour, minute, second, tzinfo=UTC)


def _candle(stamp: datetime, *, close: float = 2350.0) -> Candle:
    return Candle(
        symbol=SYMBOL,
        timeframe=TF,
        timestamp=stamp,
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=100.0,
        spread=20,
        tick_volume=100.0,
        real_volume=0.0,
    )


def _series(start: datetime, count: int, *, close0: float = 2348.0) -> list[Candle]:
    return [
        _candle(start + timedelta(minutes=15 * i), close=close0 + i * 0.2) for i in range(count)
    ]


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


def _broker_position(ticket: int) -> Position:
    return Position(
        ticket=ticket,
        symbol=SYMBOL,
        volume=1.0,
        direction=SignalDirection.SHORT,
        open_price=4566.0,
        current_price=4456.0,
        open_time=_at(0, 0),
    )


class FakeLiveProvider:
    """Read-only fake MT5 feed. Positions are never mutated by paper."""

    def __init__(self) -> None:
        self.candles: list[Candle] = []
        self.broker_positions: tuple[Position, ...] = (
            _broker_position(101),
            _broker_position(102),
            _broker_position(103),
        )
        self.tick = Tick(
            symbol=SYMBOL,
            bid=2350.10,
            ask=2350.30,
            last=2350.20,
            volume=0.0,
            timestamp=_at(10, 15),
        )

    @property
    def data_source(self) -> DataSourceMode:
        return DataSourceMode.MT5

    def requires_live_broker(self) -> bool:
        return True

    def get_snapshot(self) -> ProviderSnapshot:
        return ProviderSnapshot(
            connection_status=ProviderConnectionStatus.CONNECTED,
            data_source=DataSourceMode.MT5,
            account=AccountInfo(
                login=1,
                balance=8000.0,
                equity=40000.0,
                margin=0.0,
                free_margin=40000.0,
                leverage=200,
                trade_mode="demo",
            ),
            positions=self.broker_positions,
            updated_at=_at(10, 15),
            broker_server="Exness-MT5Trial17",
        )

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        del symbol
        return self.tick

    def get_trade_history(self, query: TradeHistoryQuery) -> TradeHistoryResult:
        del query
        return TradeHistoryResult(trades=(), total=0, updated_at=_at(10, 15))

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[Candle] | None:
        del symbol, timeframe, count
        return list(self.candles)


def _candle_engine(
    provider: FakeLiveProvider,
    clock: FakeClock,
    *,
    cursor: datetime,
    store: InMemoryCandleStateStore | FileCandleStateStore | None = None,
) -> CandleEngine:
    resolved = store or InMemoryCandleStateStore(
        CandleCursor(symbol=SYMBOL, timeframe=TF.value, last_processed_timestamp=cursor)
    )
    return CandleEngine(
        provider,
        resolved,
        symbol=SYMBOL,
        timeframe=TF,
        history_count=32,
        clock=clock,
        source="MT5",
    )


def _signal_engine(
    clock: FakeClock,
    *,
    store: InMemorySignalStateStore | FileSignalStateStore | None = None,
    compute_snapshot: object | None = _buy_snapshot,
) -> SignalEngine:
    settings = Settings()
    resolved = store or InMemorySignalStateStore(
        SignalCursor(
            symbol=SYMBOL,
            timeframe=TF.value,
            strategy=STRATEGY,
            last_processed_timestamp=None,
        )
    )
    return SignalEngine(
        store=resolved,
        strategy=EmaRsiAtrStrategy(settings),
        symbol=SYMBOL,
        timeframe=TF,
        warmup_bars=4,
        clock=clock,
        source="TEST",
        compute_snapshot=compute_snapshot,
    )


def _execution(
    clock: FakeClock,
    *,
    store: InMemoryPaperStateStore | FilePaperStateStore | None = None,
) -> ExecutionService:
    settings = Settings()
    return ExecutionService(
        risk_manager=RiskManager(settings),
        store=store or InMemoryPaperStateStore(),
        settings=settings,
        config=BacktestConfig.from_settings(settings),
        symbol_info=make_xauusd_symbol(),
        clock=clock,
    )


def _warmup_history() -> list[Candle]:
    return _series(_at(8, 45), 5)


class TestLivePipelineClosedCandleOnly:
    def test_live_pipeline_uses_closed_candle_only(self) -> None:
        provider = FakeLiveProvider()
        clock = FakeClock(_at(10, 14, 59))
        provider.candles = [_candle(_at(9, 45)), _candle(_at(10, 0), close=9999.0)]
        candles = _candle_engine(provider, clock, cursor=_at(9, 45))
        signals = _signal_engine(clock)
        paper = _execution(clock)
        signals.warmup(_warmup_history(), now=_at(10, 0))

        forming = candles.poll()
        assert forming.status in {
            CandlePollStatus.NO_CLOSED_CANDLE,
            CandlePollStatus.CANDLE_ALREADY_PROCESSED,
        }
        assert forming.events == ()
        process_closed_candles(forming.events, signals, paper)
        assert paper.open_positions() == ()
        assert paper.session().execution_count == 0

        clock.set(_at(10, 15, 0))
        provider.candles = [
            _candle(_at(9, 45)),
            _candle(_at(10, 0), close=2350.0),
            _candle(_at(10, 15), close=9999.0),
        ]
        closed = candles.poll()
        assert closed.status == CandlePollStatus.CANDLE_PROCESSED
        assert len(closed.events) == 1
        event = closed.events[0]
        assert event.candle.timestamp == _at(10, 0)
        assert event.detected_at == _at(10, 15, 0)
        assert event.detected_at != event.candle.timestamp
        assert event.candle.close == 2350.0


class TestLivePipelineNoLookahead:
    def test_live_pipeline_no_lookahead(self) -> None:
        provider = FakeLiveProvider()
        clock = FakeClock(_at(10, 15, 0))
        forming_close = 9999.0
        provider.candles = [
            _candle(_at(9, 45)),
            _candle(_at(10, 0), close=2350.0),
            _candle(_at(10, 15), close=forming_close),
        ]
        candles = _candle_engine(provider, clock, cursor=_at(9, 45))
        signals = _signal_engine(clock)
        paper = _execution(clock)
        signals.warmup(_warmup_history(), now=_at(10, 0))
        poll = candles.poll()
        assert poll.events[0].candle.close != forming_close
        process_closed_candles(poll.events, signals, paper)
        stamps = [item.timestamp for item in signals.history]
        assert max(stamps) == _at(10, 0)
        assert all(stamp <= _at(10, 0) for stamp in stamps)
        assert all(item.close != forming_close for item in signals.history)


class TestLivePipelineSignalToPaper:
    def test_live_pipeline_signal_to_paper(self) -> None:
        provider = FakeLiveProvider()
        clock = FakeClock(_at(10, 15, 0))
        provider.candles = [_candle(_at(9, 45)), _candle(_at(10, 0), close=2350.0)]
        candles = _candle_engine(provider, clock, cursor=_at(9, 45))
        signals = _signal_engine(clock)
        paper = _execution(clock)
        signals.warmup(_warmup_history(), now=_at(10, 0))
        poll = candles.poll()
        process_closed_candles(poll.events, signals, paper)
        assert signals.last_result is not None
        assert signals.last_result.signal == SignalKind.BUY
        assert signals.last_result.actionable is True
        assert signals.last_result.strategy == STRATEGY
        assert "ema_rsi_atr_v1" in signals.last_result.idempotency_key
        positions = paper.open_positions()
        assert len(positions) == 1
        fill = positions[0].entry_price
        expected = simulate_entry_fill(
            side=SignalDirection.LONG,
            symbol=make_xauusd_symbol(),
            config=BacktestConfig.from_settings(Settings()),
        )
        assert fill == expected.fill_price
        assert fill != poll.events[0].candle.close
        paper.mark_to_market(make_xauusd_symbol(bid=2351.0, ask=2351.4))
        marked = paper.open_positions()[0]
        assert marked.current_price == 2351.0
        account = paper.account_state()
        assert account.equity == round(account.balance + account.unrealized_pnl, 2)
        assert account.balance != 8000.0


class TestLivePipelineRiskRejection:
    def test_live_pipeline_risk_rejection(self) -> None:
        provider = FakeLiveProvider()
        clock = FakeClock(_at(10, 15, 0))
        provider.candles = [_candle(_at(9, 45)), _candle(_at(10, 0), close=2350.0)]
        candles = _candle_engine(provider, clock, cursor=_at(9, 45))
        signals = _signal_engine(clock)
        paper = _execution(clock)
        signals.warmup(_warmup_history(), now=_at(10, 0))
        first = candles.poll()
        process_closed_candles(first.events, signals, paper)
        assert len(paper.open_positions()) == 1

        clock.set(_at(10, 30, 0))
        provider.candles = [
            _candle(_at(10, 0), close=2350.0),
            _candle(_at(10, 15), close=2351.0),
            _candle(_at(10, 30), close=2352.0),
        ]
        second = candles.poll()
        process_closed_candles(second.events, signals, paper)
        assert len(paper.open_positions()) == 1
        assert paper.session().rejected_count == 1
        assert paper.rejections()[-1].code == RejectionCode.MAX_OPEN_POSITIONS


class TestLivePipelineIdempotentPoll:
    def test_live_pipeline_duplicate_poll_is_idempotent(self) -> None:
        provider = FakeLiveProvider()
        clock = FakeClock(_at(10, 15, 0))
        provider.candles = [_candle(_at(9, 45)), _candle(_at(10, 0), close=2350.0)]
        candles = _candle_engine(provider, clock, cursor=_at(9, 45))
        signals = _signal_engine(clock)
        paper = _execution(clock)
        signals.warmup(_warmup_history(), now=_at(10, 0))
        first = candles.poll()
        process_closed_candles(first.events, signals, paper)
        pos_id = paper.open_positions()[0].position_id
        second = candles.poll()
        assert second.status == CandlePollStatus.CANDLE_ALREADY_PROCESSED
        assert second.events == ()
        process_closed_candles(second.events, signals, paper)
        third = candles.poll()
        process_closed_candles(third.events, signals, paper)
        assert len(paper.open_positions()) == 1
        assert paper.open_positions()[0].position_id == pos_id
        assert paper.session().execution_count == 1


class TestLivePipelineRestart:
    def test_live_pipeline_restart_preserves_state(self, tmp_path: Path) -> None:
        provider = FakeLiveProvider()
        clock = FakeClock(_at(10, 15, 0))
        provider.candles = [_candle(_at(9, 45)), _candle(_at(10, 0), close=2350.0)]
        candle_store = FileCandleStateStore(
            tmp_path / "candle.json",
            symbol=SYMBOL,
            timeframe=TF.value,
        )
        candle_store.save(
            CandleCursor(symbol=SYMBOL, timeframe=TF.value, last_processed_timestamp=_at(9, 45))
        )
        signal_store = FileSignalStateStore(
            tmp_path / "signal.json",
            symbol=SYMBOL,
            timeframe=TF.value,
            strategy=STRATEGY,
        )
        paper_store = FilePaperStateStore(tmp_path / "paper.json")
        candles = _candle_engine(provider, clock, cursor=_at(9, 45), store=candle_store)
        signals = _signal_engine(clock, store=signal_store)
        paper = _execution(clock, store=paper_store)
        signals.warmup(_warmup_history(), now=_at(10, 0))
        poll = candles.poll()
        process_closed_candles(poll.events, signals, paper)
        session_id = paper.session().session_id
        pos_id = paper.open_positions()[0].position_id
        cash = paper.account_state().balance

        restarted_candles = _candle_engine(provider, clock, cursor=_at(9, 45), store=candle_store)
        restarted_signals = _signal_engine(clock, store=signal_store)
        restarted_paper = _execution(clock, store=paper_store)
        restarted_signals.warmup([*_warmup_history(), _candle(_at(10, 0))], now=_at(10, 15))
        replay = restarted_candles.poll()
        process_closed_candles(replay.events, restarted_signals, restarted_paper)
        assert replay.events == ()
        assert restarted_paper.session().session_id == session_id
        assert restarted_paper.open_positions()[0].position_id == pos_id
        assert restarted_paper.account_state().balance == cash
        assert restarted_paper.session().execution_count == 1


class TestLivePipelineBrokerSafety:
    def test_live_pipeline_does_not_touch_broker_positions(self) -> None:
        provider = FakeLiveProvider()
        before = tuple(item.ticket for item in provider.get_snapshot().positions)
        clock = FakeClock(_at(10, 15, 0))
        provider.candles = [_candle(_at(9, 45)), _candle(_at(10, 0), close=2350.0)]
        candles = _candle_engine(provider, clock, cursor=_at(9, 45))
        signals = _signal_engine(clock)
        paper = _execution(clock)
        signals.warmup(_warmup_history(), now=_at(10, 0))
        poll = candles.poll()
        process_closed_candles(poll.events, signals, paper)
        after = tuple(item.ticket for item in provider.get_snapshot().positions)
        assert before == after
        assert len(before) == 3
        assert paper.open_positions()[0].position_id.startswith("paper-")
        assert paper.account_state().balance != provider.get_snapshot().account.balance

        root = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
        forbidden = (
            "order_send",
            "TRADE_ACTION_DEAL",
            "TRADE_ACTION_PENDING",
            "TRADE_ACTION_SLTP",
            "TRADE_ACTION_REMOVE",
            "MT5Adapter",
            "TradingClient",
        )
        for package_name in ("paper_execution", "signal_engine", "candle_engine"):
            for path in (root / package_name).glob("*.py"):
                source = path.read_text(encoding="utf-8")
                for token in forbidden:
                    assert token not in source, f"{package_name}/{path.name} contains {token}"

        routes = (root / "api" / "routes" / "v1.py").read_text(encoding="utf-8")
        assert '"/order"' not in routes
        assert '"/execute"' not in routes
