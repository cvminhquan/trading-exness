"""PHASE 16.2.4A — coverage, gaps, outcomes, verdict gate (research-only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.research.compare import _decide_verdict
from exness_bot.market_analysis.research.coverage import (
    LEGACY_SILENT_STEP,
    WARMUP_BARS,
    build_coverage_report,
    explain_legacy_coverage,
)
from exness_bot.market_analysis.research.freeze import (
    DEFAULT_V2_CONFIG,
    assert_freeze_matches_16_2_4,
)
from exness_bot.market_analysis.research.gaps import classify_m15_gaps
from exness_bot.market_analysis.research.outcomes import (
    HORIZON_BARS,
    simulate_trade,
    summarize_trades,
)


def _bar(
    i: int,
    *,
    start: datetime,
    o: float,
    h: float,
    low: float,
    c: float,
) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=start + timedelta(minutes=15 * i),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=1.0,
        spread=10,
        tick_volume=1.0,
        real_volume=0.0,
    )


def test_frozen_v2_snapshot_matches_16_2_4a_spec() -> None:
    assert_freeze_matches_16_2_4(DEFAULT_V2_CONFIG)
    cfg = DEFAULT_V2_CONFIG
    assert cfg.tf_weights["M15"] == 0.50
    assert cfg.tf_weights["H1"] == 0.30
    assert cfg.tf_weights["H4"] == 0.15
    assert cfg.tf_weights["D1"] == 0.05
    assert cfg.weight_impulse == 0.20
    assert cfg.long_threshold == 20
    assert cfg.short_threshold == -20
    assert cfg.structure_conflict_dampen == 0.35
    assert cfg.impulse_tanh_scale == 1.5
    assert cfg.impulse_w1 == 0.50
    assert cfg.impulse_w3 == 0.30
    assert cfg.impulse_w4 == 0.20
    assert cfg.higher_tf_strong_conflict_enabled is False


def test_legacy_coverage_explains_735_on_35973() -> None:
    legacy = explain_legacy_coverage(35_973)
    assert legacy.TOTAL_M15_BARS == 35_973
    assert legacy.WARMUP_EXCLUDED == 250
    assert legacy.eval_step == LEGACY_SILENT_STEP == 48
    assert len(range(250, 35_973, 48)) == legacy.FINAL_EVALUATED
    assert legacy.FINAL_EVALUATED == 745
    assert legacy.SAMPLING_EXCLUDED == (35_973 - 250) - 745
    # accounting invariant (first-exclusion style)
    accounted = (
        legacy.WARMUP_EXCLUDED
        + legacy.MTF_ALIGNMENT_EXCLUDED
        + legacy.DATA_QUALITY_EXCLUDED
        + legacy.SAMPLING_EXCLUDED
        + legacy.OTHER_EXCLUDED
        + legacy.FINAL_EVALUATED
    )
    assert accounted == legacy.TOTAL_M15_BARS


def test_step1_coverage_no_silent_sampling() -> None:
    total = 1_000
    evaluated = len(range(WARMUP_BARS, total, 1))
    report = build_coverage_report(total, eval_step=1, final_evaluated=evaluated)
    assert report.SAMPLING_EXCLUDED == 0
    assert evaluated == report.FINAL_EVALUATED
    assert report.eval_step == 1


def test_weekend_gap_expected_vs_midweek_unexpected() -> None:
    # Heuristic (documented): Fri/Mon → expected; mid-week delta>4h → unexpected
    start = datetime(2025, 3, 7, 12, 0, tzinfo=UTC)  # Friday
    m15 = [_bar(0, start=start, o=2000, h=2001, low=1999, c=2000)]
    m15.append(_bar(1, start=start, o=2000, h=2001, low=1999, c=2000.5))
    weekend_next = start + timedelta(days=3)  # Monday
    m15.append(
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            timestamp=weekend_next,
            open=2001,
            high=2002,
            low=2000,
            close=2001,
            volume=1.0,
            spread=10,
            tick_volume=1.0,
            real_volume=0.0,
        )
    )
    # Mid-week hole > 4h (Tue → +6h)
    tue = datetime(2025, 3, 11, 12, 0, tzinfo=UTC)
    m15.append(
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            timestamp=tue,
            open=2001,
            high=2002,
            low=2000,
            close=2001,
            volume=1.0,
            spread=10,
            tick_volume=1.0,
            real_volume=0.0,
        )
    )
    m15.append(
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            timestamp=tue + timedelta(hours=6),
            open=2002,
            high=2003,
            low=2001,
            close=2002,
            volume=1.0,
            spread=10,
            tick_volume=1.0,
            real_volume=0.0,
        )
    )
    report = classify_m15_gaps(m15)
    assert report.expected_market_gaps >= 1
    assert report.unexpected_active_session_gaps >= 1
    assert report.duplicate_count == 0


def test_simulate_trade_tp_long_and_sl_first_collision() -> None:
    start = datetime(2025, 1, 6, 0, 0, tzinfo=UTC)
    # signal at 0; ATR=10 → SL dist=15, TP dist=30
    bars = [_bar(0, start=start, o=100, h=101, low=99, c=100)]
    # TP hit on next bar
    bars.append(_bar(1, start=start, o=100, h=140, low=99, c=130))
    trade = simulate_trade(bars, signal_index=0, direction="LONG", atr=10.0, source="v2")
    assert trade is not None
    assert trade.exit_reason == "TP"
    assert trade.exit_r == 2.0

    # same-bar SL+TP → SL first (conservative)
    bars2 = [_bar(0, start=start, o=100, h=101, low=99, c=100)]
    bars2.append(_bar(1, start=start, o=100, h=200, low=50, c=100))
    trade2 = simulate_trade(bars2, signal_index=0, direction="LONG", atr=10.0, source="v1")
    assert trade2 is not None
    assert trade2.exit_reason == "SL"
    assert trade2.exit_r == -1.0
    assert trade2.whipsaw is True


def test_summarize_trades_false_signal_and_drawdown() -> None:
    start = datetime(2025, 1, 6, 0, 0, tzinfo=UTC)
    # Build a path that SL then another TP
    m15 = [_bar(i, start=start, o=100, h=101, low=99, c=100) for i in range(20)]
    # force SL on bar 1 for first signal
    m15[1] = _bar(1, start=start, o=100, h=100, low=50, c=80)
    t1 = simulate_trade(m15, signal_index=0, direction="LONG", atr=10.0, source="v1")
    assert t1 is not None
    # second trade: set a rising path from index 5
    for i in range(6, 15):
        m15[i] = _bar(i, start=start, o=100 + i, h=150, low=100, c=120 + i)
    t2 = simulate_trade(m15, signal_index=5, direction="LONG", atr=10.0, source="v1")
    assert t2 is not None
    stats = summarize_trades([t1, t2])
    assert stats.trade_count == 2
    assert stats.false_signal_rate is not None
    assert stats.max_drawdown_R is not None
    assert stats.max_drawdown_R >= 0
    _ = HORIZON_BARS  # documented assumption stays imported


def test_verdict_blocked_when_drawdown_worsens() -> None:
    historical = {
        "available": True,
        "holdout_ran": True,
        "coverage": {"eval_step": 1, "SAMPLING_EXCLUDED": 0},
        "holdout": {
            "outcomes_v1": {
                "expectancy_R": 0.01,
                "profit_factor": 1.0,
                "whipsaw_rate": 0.2,
                "max_drawdown_R": 33.0,
                "trade_count": 100,
            },
            "outcomes_v2": {
                "expectancy_R": 0.05,
                "profit_factor": 1.08,
                "whipsaw_rate": 0.23,
                "max_drawdown_R": 58.0,
                "trade_count": 100,
            },
            "v2_lead_short_while_v1_wait": {"count": 10, "expectancy_R": 0.3},
        },
    }
    interpretation = {"A_latency_reduced": True}
    assert (
        _decide_verdict(
            historical=historical,
            interpretation=interpretation,
            gaps_quality="WARN",
        )
        == "PROMISING_V2_REQUIRES_MORE_DATA"
    )


def test_verdict_outperforms_when_gates_pass() -> None:
    historical = {
        "available": True,
        "holdout_ran": True,
        "coverage": {"eval_step": 1, "SAMPLING_EXCLUDED": 0},
        "holdout": {
            "outcomes_v1": {
                "expectancy_R": 0.01,
                "profit_factor": 1.0,
                "whipsaw_rate": 0.2,
                "max_drawdown_R": 30.0,
                "trade_count": 100,
            },
            "outcomes_v2": {
                "expectancy_R": 0.05,
                "profit_factor": 1.1,
                "whipsaw_rate": 0.21,
                "max_drawdown_R": 32.0,
                "trade_count": 100,
            },
            "v2_lead_short_while_v1_wait": {"count": 10, "expectancy_R": 0.2},
        },
    }
    interpretation = {"A_latency_reduced": True}
    assert (
        _decide_verdict(
            historical=historical,
            interpretation=interpretation,
            gaps_quality="OK",
        )
        == "V2_OUTPERFORMS_ON_HOLDOUT"
    )
