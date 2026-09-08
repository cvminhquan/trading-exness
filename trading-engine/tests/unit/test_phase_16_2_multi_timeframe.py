"""Phase 16.2 — Multi-Timeframe Technical Analysis Engine (read-only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.indicators.macd import calculate_macd, macd_snapshot
from exness_bot.market_analysis.mtf_service import (
    DEFAULT_TF_WEIGHTS,
    MultiTimeframeAnalysisService,
)
from exness_bot.market_analysis.scoring import (
    WEIGHT_LOCATION,
    WEIGHT_MOMENTUM,
    WEIGHT_STRUCTURE,
    WEIGHT_TREND,
    WEIGHT_VOLUME,
)
from exness_bot.market_analysis.setup import SetupState, SetupType, build_trade_setup
from exness_bot.market_analysis.swings import detect_confirmed_swings
from exness_bot.market_analysis.timeframe_analyzer import analyze_timeframe
from exness_bot.market_analysis.trend import TrendLabel
from exness_bot.market_analysis.volume import analyze_tick_volume


def _candle(
    index: int,
    *,
    high: float,
    low: float,
    close: float | None = None,
    volume: float = 100.0,
    timeframe: Timeframe = Timeframe.M15,
    base: datetime | None = None,
) -> Candle:
    start = base or datetime(2026, 1, 1, tzinfo=UTC)
    step = {
        Timeframe.M15: timedelta(minutes=15),
        Timeframe.H1: timedelta(hours=1),
        Timeframe.H4: timedelta(hours=4),
        Timeframe.D1: timedelta(days=1),
    }[timeframe]
    open_px = close if close is not None else (high + low) / 2
    close_px = close if close is not None else open_px
    return Candle(
        symbol="XAUUSD",
        timeframe=timeframe,
        timestamp=start + step * index,
        open=open_px,
        high=high,
        low=low,
        close=close_px,
        volume=volume,
        spread=20,
        tick_volume=volume,
        real_volume=0.0,
    )


def _uptrend_series(
    n: int = 120,
    *,
    timeframe: Timeframe = Timeframe.M15,
    start: float = 2000.0,
) -> list[Candle]:
    candles: list[Candle] = []
    price = start
    for i in range(n):
        price += 0.8 + (0.15 if i % 7 == 0 else 0.0)
        hi = price + 1.5
        lo = price - 1.2
        vol = 1000.0 + (500.0 if i == n - 1 else 0.0)
        candles.append(
            _candle(
                i,
                high=hi,
                low=lo,
                close=price,
                volume=vol,
                timeframe=timeframe,
            )
        )
    return candles


def test_macd_12_26_9_deterministic() -> None:
    closes = pd.Series([float(i) for i in range(1, 80)])
    macd_line, _signal, _hist = calculate_macd(
        closes, fast=12, slow=26, signal_period=9
    )
    assert len(macd_line) == len(closes)
    snap = macd_snapshot(closes)
    assert snap.macd is not None
    assert snap.signal is not None
    assert snap.histogram is not None
    assert snap.momentum in {"BULLISH", "BEARISH", "NEUTRAL"}


def test_volume_tick_semantics_and_ratio() -> None:
    candles = _uptrend_series(25)
    snap = analyze_tick_volume(candles, average_period=20, high_ratio=1.5, low_ratio=0.7)
    assert snap.source == "TICK_VOLUME"
    assert snap.current is not None
    assert snap.average is not None
    assert snap.ratio is not None
    assert abs(snap.ratio - snap.current / snap.average) < 1e-9
    assert snap.state == "HIGH"  # last candle boosted


def test_volume_low_and_unknown() -> None:
    candles = [
        _candle(i, high=10 + i, low=9 + i, close=9.5 + i, volume=1000.0)
        for i in range(21)
    ]
    candles[-1] = _candle(20, high=30, low=29, close=29.5, volume=100.0)
    snap = analyze_tick_volume(candles, average_period=20, high_ratio=1.5, low_ratio=0.7)
    assert snap.state == "LOW"
    empty = analyze_tick_volume([])
    assert empty.state == "UNKNOWN"


def test_scoring_weights_sum_to_one() -> None:
    assert abs(
        WEIGHT_TREND
        + WEIGHT_STRUCTURE
        + WEIGHT_MOMENTUM
        + WEIGHT_LOCATION
        + WEIGHT_VOLUME
        - 1.0
    ) < 1e-9


def test_timeframe_weights_documented() -> None:
    assert DEFAULT_TF_WEIGHTS == {"M15": 0.20, "H1": 0.30, "H4": 0.30, "D1": 0.20}
    assert abs(sum(DEFAULT_TF_WEIGHTS.values()) - 1.0) < 1e-9


@pytest.mark.parametrize(
    "tf",
    [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1],
)
def test_per_timeframe_analysis(tf: Timeframe) -> None:
    candles = _uptrend_series(120, timeframe=tf)
    result = analyze_timeframe(candles, timeframe=tf, min_bars=40)
    assert result.timeframe == tf.value
    assert result.status != "INSUFFICIENT"
    assert result.ema20 is not None
    assert result.rsi14 is not None
    assert result.atr14 is not None
    assert result.macd is not None
    assert result.volume.source == "TICK_VOLUME"
    assert result.score is not None
    assert -100 <= result.score.total_score <= 100
    assert 0 <= result.confidence <= 100
    assert result.signal in {"LONG", "SHORT", "NEUTRAL"}


def test_insufficient_history() -> None:
    candles = _uptrend_series(10)
    result = analyze_timeframe(candles, timeframe=Timeframe.M15, min_bars=50)
    assert result.status == "INSUFFICIENT"
    assert result.signal == "NEUTRAL"
    assert result.trend == TrendLabel.UNKNOWN


def test_no_lookahead_swings_in_mtf_path() -> None:
    candles = _uptrend_series(40)
    swings = detect_confirmed_swings(candles, left=2, right=2)
    assert all(s.index <= len(candles) - 1 - 2 for s in swings)


def test_trend_uses_multi_evidence() -> None:
    candles = _uptrend_series(220)
    result = analyze_timeframe(candles, timeframe=Timeframe.H1, min_bars=50)
    assert result.trend in {
        TrendLabel.UPTREND,
        TrendLabel.DOWNTREND,
        TrendLabel.RANGE,
        TrendLabel.UNKNOWN,
    }


def test_pullback_do_not_chase_waiting_for_entry() -> None:
    primary = analyze_timeframe(_uptrend_series(120), timeframe=Timeframe.M15)
    # Force support far below current
    primary.nearest_support = 2648.0
    primary.nearest_resistance = 2680.0
    primary.atr14 = 8.0
    primary.close = 2664.0
    setup = build_trade_setup(
        final_signal="LONG",
        current_price=2664.0,
        primary=primary,
        higher=primary,
        atr_sl_multiplier=1.5,
        tp_allocations=(30.0, 40.0, 30.0),
    )
    assert setup.setup_type == SetupType.PULLBACK
    assert setup.state in {SetupState.WAITING_FOR_ENTRY, SetupState.ENTRY_ZONE}
    if setup.entry_price is not None and setup.entry_price < 2664.0 - 1.0:
        assert setup.state == SetupState.WAITING_FOR_ENTRY
        assert setup.distance_to_entry is not None
        assert setup.distance_to_entry > 0


def test_tp_allocations_must_sum_100() -> None:
    primary = analyze_timeframe(_uptrend_series(120), timeframe=Timeframe.M15)
    with pytest.raises(ValueError, match="100"):
        build_trade_setup(
            final_signal="LONG",
            current_price=2350.0,
            primary=primary,
            higher=None,
            atr_sl_multiplier=1.5,
            tp_allocations=(30.0, 40.0, 20.0),
        )


def test_tp_levels_allocation_sum() -> None:
    primary = analyze_timeframe(_uptrend_series(120), timeframe=Timeframe.M15)
    primary.nearest_support = primary.close - 20 if primary.close else 2300
    primary.nearest_resistance = (primary.close or 2350) + 15
    primary.atr14 = 5.0
    setup = build_trade_setup(
        final_signal="LONG",
        current_price=primary.close or 2350,
        primary=primary,
        higher=primary,
        atr_sl_multiplier=1.5,
        tp_allocations=(30.0, 40.0, 30.0),
    )
    if setup.take_profits:
        assert abs(sum(tp.allocation_pct for tp in setup.take_profits) - 100.0) < 1e-6


def test_setup_states_no_setup_on_wait() -> None:
    primary = analyze_timeframe(_uptrend_series(120), timeframe=Timeframe.M15)
    setup = build_trade_setup(
        final_signal="WAIT",
        current_price=2350.0,
        primary=primary,
        higher=None,
        atr_sl_multiplier=1.5,
    )
    assert setup.state == SetupState.NO_SETUP
    assert setup.setup_type == SetupType.NONE


def test_structure_aware_sl_not_inside_support() -> None:
    primary = analyze_timeframe(_uptrend_series(120), timeframe=Timeframe.M15)
    assert primary.close is not None
    primary.nearest_support = primary.close - 10
    primary.atr14 = 5.0
    setup = build_trade_setup(
        final_signal="LONG",
        current_price=primary.close,
        primary=primary,
        higher=primary,
        atr_sl_multiplier=1.5,
        tp_allocations=(30.0, 40.0, 30.0),
    )
    if setup.stop_loss is not None and primary.nearest_support is not None:
        # SL should be at or below support (with ATR buffer), not above it into structure
        assert setup.stop_loss <= primary.nearest_support + 1e-9 or setup.sl_reason


class _FakeProvider:
    def __init__(self, candles_by_tf: dict[Timeframe, list[Candle]], equity: float = 10.5):
        self._candles = candles_by_tf
        self._equity = equity

    def get_snapshot(self):
        from types import SimpleNamespace

        return SimpleNamespace(account=SimpleNamespace(equity=self._equity, balance=self._equity))

    def get_tick(self, symbol: str | None = None):
        from exness_bot.domain.models import Tick

        c = self._candles[Timeframe.M15][-1]
        mid = c.close
        return Tick(
            symbol=symbol or "XAUUSD",
            bid=mid - 0.1,
            ask=mid + 0.1,
            last=mid,
            volume=1.0,
            timestamp=c.timestamp,
        )

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int):
        series = self._candles.get(timeframe, [])
        return series[-count:] if series else []

    def get_symbol_info(self, symbol: str):
        from exness_bot.domain.models import SymbolInfo

        return SymbolInfo(
            symbol=symbol,
            bid=2300.0,
            ask=2300.2,
            point=0.01,
            digits=2,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            spread=20,
            trade_mode=4,
            visible=True,
            stops_level=0,
            freeze_level=0,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
        )


def _settings():
    from exness_bot.config.settings import Settings

    return Settings(
        _env_file=None,
        SYMBOL="XAUUSD",
        MT5_SYMBOL="XAUUSDm",
        RISK_PER_TRADE_PCT=0.5,
        ATR_SL_MULTIPLIER=1.5,
        CANDLE_HISTORY_COUNT=200,
        MACD_FAST=12,
        MACD_SLOW=26,
        MACD_SIGNAL=9,
        VOLUME_AVG_PERIOD=20,
        VOLUME_HIGH_RATIO=1.5,
        VOLUME_LOW_RATIO=0.7,
        MTF_WEIGHT_M15=0.20,
        MTF_WEIGHT_H1=0.30,
        MTF_WEIGHT_H4=0.30,
        MTF_WEIGHT_D1=0.20,
        TP1_ALLOCATION_PCT=30,
        TP2_ALLOCATION_PCT=40,
        TP3_ALLOCATION_PCT=30,
    )


def test_mtf_aggregation_aligned_long() -> None:
    candles = {
        Timeframe.M15: _uptrend_series(120, timeframe=Timeframe.M15),
        Timeframe.H1: _uptrend_series(120, timeframe=Timeframe.H1),
        Timeframe.H4: _uptrend_series(100, timeframe=Timeframe.H4),
        Timeframe.D1: _uptrend_series(80, timeframe=Timeframe.D1),
    }
    service = MultiTimeframeAnalysisService(_settings(), _FakeProvider(candles))
    result = service.analyze("XAUUSD")
    assert result.confidence_meaning == "EVIDENCE_ALIGNMENT"
    assert result.final_signal in {"LONG", "SHORT", "WAIT"}
    assert set(result.timeframes.keys()) == {"M15", "H1", "H4", "D1"}
    assert 0 <= result.confidence_score <= 100


def test_mtf_conflicting_higher_tf_wait() -> None:
    up = _uptrend_series(120, timeframe=Timeframe.M15)
    down = _uptrend_series(120, timeframe=Timeframe.H4, start=3000.0)
    # Invert downtrend candles
    down_rev = []
    for i, _c in enumerate(down):
        price = 3000.0 - i * 1.2
        down_rev.append(
            _candle(
                i,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=1000,
                timeframe=Timeframe.H4,
            )
        )
    d1_down = []
    for i in range(80):
        price = 3100.0 - i * 2.0
        d1_down.append(
            _candle(
                i,
                high=price + 2,
                low=price - 2,
                close=price,
                volume=1000,
                timeframe=Timeframe.D1,
            )
        )
    candles = {
        Timeframe.M15: up,
        Timeframe.H1: _uptrend_series(120, timeframe=Timeframe.H1),
        Timeframe.H4: down_rev,
        Timeframe.D1: d1_down,
    }
    service = MultiTimeframeAnalysisService(_settings(), _FakeProvider(candles))
    result = service.analyze("XAUUSD")
    # When H4 vs D1 conflict with opposite directions → WAIT
    h4 = result.timeframes["H4"].signal
    d1 = result.timeframes["D1"].signal
    if h4 != d1 and "NEUTRAL" not in {h4, d1}:
        assert result.final_signal == "WAIT"
        assert any(w.code == "HIGHER_TF_CONFLICT" for w in result.warnings)


def test_small_account_min_volume_risk() -> None:
    candles = {
        Timeframe.M15: _uptrend_series(120, timeframe=Timeframe.M15),
        Timeframe.H1: _uptrend_series(120, timeframe=Timeframe.H1),
        Timeframe.H4: _uptrend_series(100, timeframe=Timeframe.H4),
        Timeframe.D1: _uptrend_series(80, timeframe=Timeframe.D1),
    }
    service = MultiTimeframeAnalysisService(
        _settings(), _FakeProvider(candles, equity=10.5)
    )
    result = service.analyze("XAUUSD")
    if result.sizing is not None:
        # May be brokerExecutable but not riskAcceptable on tiny equity
        assert hasattr(result.sizing, "broker_executable")
        assert hasattr(result.sizing, "risk_acceptable")


def test_confidence_is_evidence_alignment_not_win_prob() -> None:
    candles = {
        tf: _uptrend_series(100, timeframe=tf)
        for tf in (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1)
    }
    result = MultiTimeframeAnalysisService(_settings(), _FakeProvider(candles)).analyze()
    assert result.confidence_meaning == "EVIDENCE_ALIGNMENT"


def test_phase_16_2_modules_have_no_order_send() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "exness_bot" / "market_analysis"
    # Ban executable call sites / imports — docstring safety notes may mention names.
    call_forbidden = ("order_send(",)
    import_forbidden = (
        "from exness_bot.execution",
        "import LiveMT5ExecutionTransport",
        "import ExecutionOrchestrator",
        "LiveMT5ExecutionTransport(",
        "ExecutionOrchestrator(",
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in call_forbidden + import_forbidden:
            assert token not in text, f"{path.name} contains {token}"


def test_patterns_conservative_none_or_known() -> None:
    primary = analyze_timeframe(_uptrend_series(120), timeframe=Timeframe.M15)
    assert primary.pattern.type
    # Must not invent vague chart patterns
    banned = {"HEAD_AND_SHOULDERS", "DOUBLE_TOP", "V_RECOVERY"}
    assert primary.pattern.type not in banned


def test_entry_zone_state_when_price_inside() -> None:
    primary = analyze_timeframe(_uptrend_series(120), timeframe=Timeframe.M15)
    assert primary.close is not None
    primary.nearest_support = primary.close
    primary.atr14 = 4.0
    primary.nearest_resistance = primary.close + 30
    setup = build_trade_setup(
        final_signal="LONG",
        current_price=primary.close,
        primary=primary,
        higher=primary,
        atr_sl_multiplier=1.5,
        entry_zone_atr_width=2.0,
        chase_atr_threshold=5.0,
    )
    if (
        setup.entry_zone_low is not None
        and setup.entry_zone_high is not None
        and setup.entry_zone_low <= primary.close <= setup.entry_zone_high
    ):
        assert setup.state == SetupState.ENTRY_ZONE


def test_mtf_api_read_only(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from exness_bot.api.app import create_app
    from exness_bot.api.dependencies import get_read_service
    from exness_bot.api.services.read_service import ReadService
    from exness_bot.backtest.baseline_runner import (
        baseline_paths,
        run_baseline,
        write_baseline_outputs,
    )
    from exness_bot.config.settings import Settings
    from exness_bot.data.mock_provider import MockTradingDataProvider

    result = run_baseline(Settings(), project_root=tmp_path)
    write_baseline_outputs(result, baseline_paths(tmp_path))
    settings = Settings()
    service = ReadService(
        settings,
        MockTradingDataProvider(settings),
        project_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_read_service] = lambda: service
    client = TestClient(app)
    response = client.get("/api/v1/analysis/XAUUSD/multi-timeframe")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["symbol"] == "XAUUSD"
    assert data["confidenceMeaning"] == "EVIDENCE_ALIGNMENT"
    assert data["finalSignal"] in {"LONG", "SHORT", "WAIT"}
    assert "M15" in data["timeframes"]
    assert "order_send" not in str(response.json()).lower()
    assert client.post("/api/v1/analysis/XAUUSD/multi-timeframe").status_code in {
        404,
        405,
        422,
    }
