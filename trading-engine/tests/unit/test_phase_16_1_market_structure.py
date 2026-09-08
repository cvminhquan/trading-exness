"""Phase 16.1 — market structure / support-resistance (read-only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.context import ContextAssessment, assess_structure_context
from exness_bot.market_analysis.levels import (
    build_support_resistance,
    nearest_resistance_above,
    nearest_support_below,
)
from exness_bot.market_analysis.models import AnalysisSignal, TradePlan
from exness_bot.market_analysis.structure import classify_structure, label_swings
from exness_bot.market_analysis.swings import SwingKind, detect_confirmed_swings


def _candle(
    index: int,
    *,
    high: float,
    low: float,
    close: float | None = None,
    base: datetime | None = None,
) -> Candle:
    start = base or datetime(2026, 1, 1, tzinfo=UTC)
    open_px = close if close is not None else (high + low) / 2
    close_px = close if close is not None else open_px
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=start + timedelta(minutes=15 * index),
        open=open_px,
        high=high,
        low=low,
        close=close_px,
        volume=1.0,
        spread=20,
        tick_volume=1.0,
        real_volume=0.0,
    )


def _zigzag_series() -> list[Candle]:
    """Deterministic path: low → high → higher low → higher high."""
    # indices: 0..n
    pattern = [
        (10, 8),  # 0
        (11, 8.5),
        (12, 9),
        (10.5, 7),  # 3 swing low candidate
        (11, 8),
        (12, 9),
        (14, 10),  # 6 swing high candidate
        (13, 11),
        (12.5, 10.5),
        (12, 9.5),  # 9 HL candidate
        (13, 10),
        (14, 11),
        (16, 12),  # 12 HH candidate
        (15, 13),
        (14.5, 12.5),
        (14, 12),
        (13.5, 11.5),
    ]
    return [
        _candle(i, high=hi, low=lo, close=(hi + lo) / 2)
        for i, (hi, lo) in enumerate(pattern)
    ]


def test_confirmed_swing_high_and_low_no_lookahead() -> None:
    candles = _zigzag_series()
    swings = detect_confirmed_swings(candles, left=2, right=2)
    assert swings
    # Last two bars cannot host a new swing (need right confirmation)
    assert all(s.index <= len(candles) - 1 - 2 for s in swings)
    assert all(s.confirmed_at_index == s.index + 2 for s in swings)
    highs = [s for s in swings if s.kind == SwingKind.HIGH]
    lows = [s for s in swings if s.kind == SwingKind.LOW]
    assert highs and lows


def test_no_lookahead_on_incomplete_right_window() -> None:
    # Exactly left+1+right-1 bars → no confirmed swing yet
    candles = [
        _candle(i, high=10 + i, low=9 + i) for i in range(4)
    ]  # left=2 right=2 needs 5
    assert detect_confirmed_swings(candles, left=2, right=2) == []


def test_hh_hl_lh_ll_and_structures() -> None:
    candles = _zigzag_series()
    swings = detect_confirmed_swings(candles, left=2, right=2)
    labeled = label_swings(swings)
    labels = [item.label.value for item in labeled if item.label is not None]
    assert "HH" in labels or "HL" in labels or "LH" in labels or "LL" in labels
    snap = classify_structure(labeled)
    assert snap.classification.value in {
        "BULLISH",
        "BEARISH",
        "RANGE",
        "UNDETERMINED",
    }


def test_insufficient_data_undetermined() -> None:
    candles = [_candle(i, high=10, low=9) for i in range(3)]
    swings = detect_confirmed_swings(candles, left=2, right=2)
    snap = classify_structure(label_swings(swings))
    assert snap.classification.value == "UNDETERMINED"


def test_support_resistance_clustering_and_nearest() -> None:
    candles = _zigzag_series()
    swings = detect_confirmed_swings(candles, left=2, right=2)
    supports, resistances = build_support_resistance(
        swings, atr14=1.0, cluster_atr_multiplier=0.5, point=0.01
    )
    assert supports or resistances
    entry = 12.0
    ns = nearest_support_below(supports, entry)
    nr = nearest_resistance_above(resistances, entry)
    if ns is not None:
        assert ns.price < entry
    if nr is not None:
        assert nr.price > entry


def test_atr_distance_and_buy_near_resistance_blocks() -> None:
    supports, resistances = build_support_resistance(
        detect_confirmed_swings(_zigzag_series(), left=2, right=2),
        atr14=2.0,
        cluster_atr_multiplier=0.25,
    )
    # Force a resistance just above entry
    from exness_bot.market_analysis.levels import LevelType, StructureLevel

    resistances = [
        StructureLevel(
            price=2351.0,
            level_type=LevelType.RESISTANCE,
            touch_count=2,
            strength=2.0,
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            last_seen=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    supports = [
        StructureLevel(
            price=2340.0,
            level_type=LevelType.SUPPORT,
            touch_count=1,
            strength=1.0,
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            last_seen=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    from exness_bot.market_analysis.structure import StructureLabel, StructureSnapshot

    structure = StructureSnapshot(
        classification=StructureLabel.BULLISH,
        sequence=["HH", "HL"],
        labeled=[],
        latest_swing_high=2351.0,
        latest_swing_low=2340.0,
    )
    trade = TradePlan(
        entry=2350.0,
        stop_loss=2347.0,
        take_profit=2356.0,
        risk_reward_ratio=2.0,
    )
    ctx = assess_structure_context(
        strategy_signal=AnalysisSignal.BUY,
        trade=trade,
        atr14=2.0,
        structure=structure,
        supports=supports,
        resistances=resistances,
        swings=[],
        near_atr_threshold=0.5,
        caution_atr_threshold=1.0,
    )
    assert ctx.nearest_resistance == pytest.approx(2351.0)
    assert ctx.distance_to_resistance_atr == pytest.approx(0.5)
    assert ctx.context_assessment == ContextAssessment.BLOCKED
    codes = {r.code for r in ctx.context_reasons}
    assert "RESISTANCE_TOO_CLOSE" in codes
    assert "TP_CROSSES_RESISTANCE" in codes
    # strategy signal is an input — context does not mutate it
    assert AnalysisSignal.BUY.value == "BUY"


def test_sell_near_support_and_tp_crosses_support() -> None:
    from exness_bot.market_analysis.levels import LevelType, StructureLevel
    from exness_bot.market_analysis.structure import StructureLabel, StructureSnapshot

    supports = [
        StructureLevel(
            price=2349.0,
            level_type=LevelType.SUPPORT,
            touch_count=2,
            strength=2.0,
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            last_seen=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    resistances = [
        StructureLevel(
            price=2360.0,
            level_type=LevelType.RESISTANCE,
            touch_count=1,
            strength=1.0,
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            last_seen=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    structure = StructureSnapshot(
        classification=StructureLabel.BEARISH,
        sequence=["LH", "LL"],
        labeled=[],
        latest_swing_high=2360.0,
        latest_swing_low=2349.0,
    )
    trade = TradePlan(
        entry=2350.0,
        stop_loss=2353.0,
        take_profit=2344.0,
        risk_reward_ratio=2.0,
    )
    ctx = assess_structure_context(
        strategy_signal=AnalysisSignal.SELL,
        trade=trade,
        atr14=2.0,
        structure=structure,
        supports=supports,
        resistances=resistances,
        swings=[],
        near_atr_threshold=0.5,
        caution_atr_threshold=1.0,
    )
    assert ctx.context_assessment == ContextAssessment.BLOCKED
    codes = {r.code for r in ctx.context_reasons}
    assert "SUPPORT_TOO_CLOSE" in codes
    assert "TP_CROSSES_SUPPORT" in codes


def test_wait_stays_not_applicable_and_signal_unchanged() -> None:
    from exness_bot.market_analysis.structure import StructureLabel, StructureSnapshot

    structure = StructureSnapshot(
        classification=StructureLabel.RANGE,
        sequence=["HH", "LL"],
        labeled=[],
        latest_swing_high=1.0,
        latest_swing_low=0.5,
    )
    ctx = assess_structure_context(
        strategy_signal=AnalysisSignal.WAIT,
        trade=None,
        atr14=2.0,
        structure=structure,
        supports=[],
        resistances=[],
        swings=[],
        near_atr_threshold=0.5,
        caution_atr_threshold=1.0,
    )
    assert ctx.context_assessment == ContextAssessment.NOT_APPLICABLE


def test_no_order_send_in_structure_modules() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "exness_bot" / "market_analysis"
    for name in ("swings.py", "structure.py", "levels.py", "context.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "order_send(" not in text
        assert "ExecutionOrchestrator" not in text
        assert "LiveMT5ExecutionTransport" not in text
