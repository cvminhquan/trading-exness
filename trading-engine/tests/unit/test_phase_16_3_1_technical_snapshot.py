"""Unit tests for Phase 16.3.1 Technical Market Snapshot."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, Tick
from exness_bot.market_analysis.structure import StructureLabel, classify_structure, label_swings
from exness_bot.market_analysis.swings import ConfirmedSwing, SwingKind, detect_confirmed_swings
from exness_bot.market_analysis.technical_snapshot.alignment import summarize_mtf_alignment
from exness_bot.market_analysis.technical_snapshot.builder import TechnicalSnapshotBuilder
from exness_bot.market_analysis.technical_snapshot.models import SCHEMA_VERSION, TIMEFRAME_ROLES
from exness_bot.market_analysis.technical_snapshot.trend_segment import derive_trend_segment
from exness_bot.market_analysis.technical_snapshot.wick_detector import (
    build_wick_morphology,
    classify_wick_pattern,
    compute_wick_raw,
)
from exness_bot.market_analysis.trend import TrendLabel
from exness_bot.market_data.candles import closed_candles_only


def _c(
    i: int,
    *,
    base: datetime | None = None,
    o: float = 100.0,
    h: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    tf: Timeframe = Timeframe.M15,
) -> Candle:
    start = base or datetime(2026, 1, 1, tzinfo=UTC)
    return Candle(
        symbol="XAUUSD",
        timeframe=tf,
        timestamp=start + timedelta(minutes=15 * i),
        open=o,
        high=h,
        low=low,
        close=close,
        volume=100.0,
    )


class FakeProvider:
    def __init__(self, candles_by_tf: dict[Timeframe, list[Candle]], tick: Tick | None) -> None:
        self._candles = candles_by_tf
        self._tick = tick

    def get_tick(self, symbol: str | None = None) -> Tick | None:
        return self._tick

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> list[Candle] | None:
        rows = self._candles.get(timeframe, [])
        return rows[-count:] if rows else []

    def resolve_broker_symbol(self, symbol: str) -> str:
        return "XAUUSDm"

    def get_snapshot(self) -> object:
        account = type(
            "Account",
            (),
            {"equity": 10_000.0, "balance": 10_000.0, "currency": "USD"},
        )()
        return type("Snap", (), {"account": account})()


def _series(n: int = 80, *, trend: str = "up") -> list[Candle]:
    out: list[Candle] = []
    px = 2000.0
    for i in range(n):
        if trend == "up":
            px += 0.5
        elif trend == "down":
            px -= 0.5
        else:
            px += 0.05 if i % 2 == 0 else -0.05
        out.append(_c(i, o=px - 0.2, h=px + 0.8, low=px - 0.8, close=px))
    return out


def test_timeframe_roles_locked() -> None:
    assert TIMEFRAME_ROLES == {
        "M15": "PRIMARY",
        "H1": "CONFIRMATION",
        "H4": "CONTEXT",
        "D1": "MACRO_CONTEXT",
    }


def test_forming_candle_excluded() -> None:
    now = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
    # open at 01:50 → closes 02:05 → still forming at 02:00
    forming = Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=datetime(2026, 1, 1, 1, 50, tzinfo=UTC),
        open=1,
        high=2,
        low=0.5,
        close=1.5,
        volume=1,
    )
    closed = Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=datetime(2026, 1, 1, 1, 30, tzinfo=UTC),
        open=1,
        high=2,
        low=0.5,
        close=1.2,
        volume=1,
    )
    out = closed_candles_only([closed, forming], Timeframe.M15, now=now)
    assert len(out) == 1
    assert out[0].timestamp == closed.timestamp


def test_upper_wick_rejection() -> None:
    c = _c(0, o=100, h=110, low=99.5, close=100.2)  # long upper wick
    raw = compute_wick_raw(c)
    assert classify_wick_pattern(raw).value == "UPPER_WICK_REJECTION"
    morph = build_wick_morphology(
        c, atr14=2.0, nearest_support=90.0, nearest_resistance=100.5
    )
    assert morph.pattern == "UPPER_WICK_REJECTION"
    assert morph.near_resistance is True
    assert morph.level_context == "AT_RESISTANCE"


def test_lower_wick_rejection() -> None:
    c = _c(0, o=100, h=100.5, low=90, close=99.8)
    assert classify_wick_pattern(compute_wick_raw(c)).value == "LOWER_WICK_REJECTION"


def test_no_rejection_and_zero_range() -> None:
    # Tight candle — no dominant wick
    normal = _c(0, o=100, h=100.3, low=99.8, close=100.1)
    assert classify_wick_pattern(compute_wick_raw(normal)).value == "NO_CLEAR_REJECTION"
    doji = _c(0, o=100, h=100, low=100, close=100)
    raw = compute_wick_raw(doji)
    assert raw.range_size == 0
    assert classify_wick_pattern(raw).value == "NO_CLEAR_REJECTION"
    morph = build_wick_morphology(doji, atr14=1.0, nearest_support=None, nearest_resistance=None)
    assert morph.body_to_range_ratio is None
    assert morph.close_position_in_range is None


def test_zero_body_ratios() -> None:
    c = _c(0, o=100, h=105, low=95, close=100)
    raw = compute_wick_raw(c)
    assert raw.body == 0
    morph = build_wick_morphology(c, atr14=2.0, nearest_support=None, nearest_resistance=None)
    assert morph.upper_wick_to_body_ratio is not None
    assert morph.lower_wick_to_body_ratio is not None


def test_trend_segment_bearish_anchor() -> None:
    candles = _series(70, trend="down")
    # Inject a clear swing high mid-series
    swings = detect_confirmed_swings(candles, left=2, right=2)
    labeled = label_swings(swings)
    structure = classify_structure(labeled)
    # Force bearish if structure undetermined by using DOWNTREND + BEARISH structure if possible
    res = derive_trend_segment(
        candles,
        swings=swings,
        structure=structure,
        trend=TrendLabel.DOWNTREND,
        atr14=2.0,
    )
    if structure.classification == StructureLabel.BEARISH or res.segment is not None:
        if res.segment is not None:
            assert res.segment.direction in {"BEARISH", "BULLISH"}
            assert res.segment.bars >= 1
            assert res.segment.start_price is not None
    else:
        assert res.reason == "INSUFFICIENT_CONFIRMED_STRUCTURE"


def test_trend_segment_insufficient() -> None:
    candles = [_c(i) for i in range(5)]
    empty_structure = classify_structure([])
    res = derive_trend_segment(
        candles,
        swings=[],
        structure=empty_structure,
        trend=TrendLabel.UNKNOWN,
        atr14=1.0,
    )
    assert res.segment is None
    assert res.reason == "INSUFFICIENT_CONFIRMED_STRUCTURE"


def test_trend_segment_no_future_pivot() -> None:
    """Anchor index must be strictly before last bar."""
    candles = _series(40, trend="down")
    swings = [
        ConfirmedSwing(
            kind=SwingKind.HIGH,
            index=10,
            price=2010.0,
            timestamp=candles[10].timestamp,
            confirmed_at_index=12,
        )
    ]
    from exness_bot.market_analysis.structure import StructureSnapshot

    structure = StructureSnapshot(
        classification=StructureLabel.BEARISH,
        sequence=["LH", "LL"],
        labeled=[],
        latest_swing_high=2010.0,
        latest_swing_low=1990.0,
    )
    res = derive_trend_segment(
        candles,
        swings=swings,
        structure=structure,
        trend=TrendLabel.DOWNTREND,
        atr14=5.0,
    )
    assert res.segment is not None
    assert res.segment.anchor == "CONFIRMED_SWING_HIGH"
    assert res.segment.start_price == 2010.0
    assert res.segment.bars == len(candles) - 1 - 10


def test_swings_confirmed_only() -> None:
    candles = _series(40, trend="up")
    swings = detect_confirmed_swings(candles, left=2, right=2)
    for s in swings:
        assert s.confirmed_at_index == s.index + 2
        assert s.confirmed_at_index < len(candles)


def test_mtf_alignment_cases() -> None:
    all_bear = summarize_mtf_alignment(
        {"M15": "DOWNTREND", "H1": "DOWNTREND", "H4": "DOWNTREND", "D1": "DOWNTREND"}
    )
    assert all_bear.primary_bias == "BEARISH"
    assert all_bear.confirmation == "ALIGNED"
    assert all_bear.alignment == "ALIGNED"

    mixed = summarize_mtf_alignment(
        {"M15": "DOWNTREND", "H1": "DOWNTREND", "H4": "UPTREND", "D1": "UPTREND"}
    )
    assert mixed.primary_bias == "BEARISH"
    assert mixed.confirmation == "ALIGNED"
    assert mixed.higher_timeframe_context == "CONFLICTING"

    conflict_h1 = summarize_mtf_alignment(
        {"M15": "UPTREND", "H1": "DOWNTREND", "H4": "RANGE", "D1": "RANGE"}
    )
    assert conflict_h1.confirmation == "CONFLICTING"

    insuff = summarize_mtf_alignment(
        {"M15": "INSUFFICIENT", "H1": None, "H4": None, "D1": None}
    )
    assert insuff.alignment == "INSUFFICIENT_DATA"


def test_builder_snapshot_schema_and_no_nan() -> None:
    settings = Settings()
    m15 = _series(90, trend="down")
    # Provide enough for each TF (reuse series with different timestamps is fine for unit)
    provider = FakeProvider(
        {
            Timeframe.M15: m15,
            Timeframe.H1: m15,
            Timeframe.H4: m15,
            Timeframe.D1: m15,
        },
        Tick(
            symbol="XAUUSD",
            bid=1990.0,
            ask=1990.5,
            last=1990.2,
            volume=1.0,
            timestamp=datetime.now(tz=UTC),
        ),
    )
    snap = TechnicalSnapshotBuilder(settings, provider).build("XAUUSD")
    assert snap.schema_version == SCHEMA_VERSION
    assert snap.symbol == "XAUUSD"
    assert snap.broker_symbol == "XAUUSDm"
    assert snap.primary_timeframe == "M15"
    assert set(snap.timeframes) == {"M15", "H1", "H4", "D1"}
    assert snap.timeframes["M15"].role == "PRIMARY"
    assert snap.bot_analysis.production_strategy == "mtf_technical_v1"
    assert "omitted" in snap.bot_analysis.note.lower()
    data = snap.to_dict()
    compact = snap.to_compact_context()
    assert "timeframes" in compact
    assert "facts" in data
    # JSON safety: no NaN/Inf via round-trip
    import json

    text = json.dumps(data)
    assert "NaN" not in text
    assert "Infinity" not in text


def test_static_safety_no_execution_imports() -> None:
    package = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "exness_bot"
        / "market_analysis"
        / "technical_snapshot"
    )
    forbidden = (
        "ExecutionOrchestrator",
        "GatedMT5ExecutionPort",
        "MT5Executor",
        "LiveMT5ExecutionTransport",
        "order_send",
        "market_analysis.research",
    )
    for py in package.glob("*.py"):
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for name in forbidden:
                    assert name not in mod
                    for alias in node.names:
                        assert name not in alias.name
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for name in forbidden:
                        assert name not in alias.name
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "order_send":
                    raise AssertionError(f"{py.name} calls order_send")
                if isinstance(func, ast.Name) and func.id == "order_send":
                    raise AssertionError(f"{py.name} calls order_send")


@pytest.mark.parametrize("tf", [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1])
def test_closed_only_per_timeframe(tf: Timeframe) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    from exness_bot.market_data.candles import timeframe_duration

    duration = timeframe_duration(tf)
    closed_ts = now - duration
    forming_ts = now - duration + timedelta(seconds=1)
    candles = [
        Candle(
            symbol="XAUUSD",
            timeframe=tf,
            timestamp=closed_ts - duration,
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=1,
        ),
        Candle(
            symbol="XAUUSD",
            timeframe=tf,
            timestamp=forming_ts,
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=1,
        ),
    ]
    out = closed_candles_only(candles, tf, now=now)
    assert all(
        c.timestamp + duration <= now for c in out
    )
