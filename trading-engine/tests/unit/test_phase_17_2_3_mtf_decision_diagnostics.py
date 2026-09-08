"""Phase 17.2.3 — MTF decision diagnostics (observability only)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from exness_bot.market_analysis.mtf_diagnostics import (
    build_mtf_decision_diagnostics,
    derive_decision_reasons,
    format_mtf_decision_summary,
)
from exness_bot.market_analysis.mtf_service import (
    MTF_LONG_THRESHOLD,
    MTF_SHORT_THRESHOLD,
    MtfAggregateTrace,
    MultiTimeframeAnalysis,
    MultiTimeframeAnalysisService,
)
from exness_bot.market_analysis.patterns import PatternSnapshot
from exness_bot.market_analysis.scoring import ScoreBreakdown
from exness_bot.market_analysis.structure import StructureLabel
from exness_bot.market_analysis.timeframe_analyzer import TimeframeAnalysis
from exness_bot.market_analysis.trend import TrendLabel
from exness_bot.market_analysis.volume import VolumeSnapshot

_NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
_WEIGHTS = {"M15": 0.20, "H1": 0.30, "H4": 0.30, "D1": 0.20}


def _score(
    total: float,
    *,
    trend: float | None = None,
    structure: float | None = None,
    momentum: float = 0.0,
    direction: str | None = None,
) -> ScoreBreakdown:
    if direction is None:
        if total >= 25:
            direction = "LONG"
        elif total <= -25:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"
    t = float(total if trend is None else trend)
    s = float(total if structure is None else structure)
    return ScoreBreakdown(
        trend_score=t,
        structure_score=s,
        momentum_score=float(momentum),
        location_score=0.0,
        volume_score=0.0,
        total_score=float(total),
        confidence=70.0,
        direction=direction,
    )


def _tf(
    name: str,
    *,
    total: float,
    structure: StructureLabel = StructureLabel.BULLISH,
    status: str = "LIVE",
    momentum: float = 50.0,
) -> TimeframeAnalysis:
    score = _score(total, momentum=momentum)
    return TimeframeAnalysis(
        timeframe=name,
        candle_timestamp=_NOW,
        close=2341.0,
        trend=TrendLabel.UPTREND if total >= 0 else TrendLabel.DOWNTREND,
        signal=score.direction,
        confidence=70.0,
        score=score,
        ema20=2340.0,
        ema50=2330.0,
        ema200=2300.0,
        rsi14=55.0,
        atr14=5.0,
        macd=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        macd_momentum="BULLISH" if total >= 0 else "BEARISH",
        structure_classification=structure,
        sequence=["HH", "HL"],
        latest_swing_high=2360.0,
        latest_swing_low=2320.0,
        nearest_support=2338.0,
        nearest_resistance=2355.0,
        supports=[2338.0],
        resistances=[2355.0],
        volume=VolumeSnapshot("TICK_VOLUME", 1000, 800, 1.25, "NORMAL"),
        pattern=PatternSnapshot("NONE", 0.0, []),
        status=status,
    )


def _service() -> MultiTimeframeAnalysisService:
    return MultiTimeframeAnalysisService(SimpleNamespace(), SimpleNamespace())  # type: ignore[arg-type]


def _aggregate(tfs: dict[str, TimeframeAnalysis]):
    return _service()._aggregate(tfs, _WEIGHTS)


def _analysis_from_tfs(
    tfs: dict[str, TimeframeAnalysis],
    *,
    final: str,
    conf: float,
    trace: MtfAggregateTrace,
) -> MultiTimeframeAnalysis:
    return MultiTimeframeAnalysis(
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        current_price=2341.0,
        timeframes=tfs,
        final_signal=final,
        confidence_score=conf,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        trend="UPTREND",
        structure_summary="",
        key_supports=[],
        key_resistances=[],
        setup=None,
        sizing=None,
        execution_assessment="NOT_APPLICABLE",
        aggregate_trace=trace,
        tf_weights=dict(_WEIGHTS),
    )


def test_thresholds_unchanged() -> None:
    assert MTF_LONG_THRESHOLD == 20.0
    assert MTF_SHORT_THRESHOLD == -20.0


def test_strong_bullish_long_diagnostics() -> None:
    tfs = {
        "M15": _tf("M15", total=80),
        "H1": _tf("H1", total=80),
        "H4": _tf("H4", total=80),
        "D1": _tf("D1", total=80),
    }
    final, conf, _r, _w, trace = _aggregate(tfs)
    assert final == "LONG"
    assert trace.weighted_score is not None
    assert trace.weighted_score >= MTF_LONG_THRESHOLD
    analysis = _analysis_from_tfs(tfs, final=final, conf=conf, trace=trace)
    diag = build_mtf_decision_diagnostics(analysis, weights=_WEIGHTS, trace=trace)
    assert diag.final_signal == "LONG"
    assert diag.mtf_weighted_score == trace.weighted_score
    assert diag.base_direction == "LONG"
    text = "\n".join(format_mtf_decision_summary(diag))
    assert "FINAL: LONG" in text


def test_strong_bearish_short_diagnostics() -> None:
    tfs = {
        "M15": _tf("M15", total=-80, structure=StructureLabel.BEARISH),
        "H1": _tf("H1", total=-80, structure=StructureLabel.BEARISH),
        "H4": _tf("H4", total=-80, structure=StructureLabel.BEARISH),
        "D1": _tf("D1", total=-80, structure=StructureLabel.BEARISH),
    }
    final, conf, _r, _w, trace = _aggregate(tfs)
    assert final == "SHORT"
    analysis = _analysis_from_tfs(tfs, final=final, conf=conf, trace=trace)
    diag = build_mtf_decision_diagnostics(analysis, weights=_WEIGHTS, trace=trace)
    assert diag.final_signal == "SHORT"
    assert diag.mtf_weighted_score == trace.weighted_score


def test_mixed_wait_diagnostics() -> None:
    tfs = {
        "M15": _tf("M15", total=10, momentum=0.0),
        "H1": _tf("H1", total=5, momentum=0.0),
        "H4": _tf("H4", total=-5, momentum=0.0, structure=StructureLabel.RANGE),
        "D1": _tf("D1", total=0, momentum=0.0, structure=StructureLabel.RANGE),
    }
    final, conf, _r, _w, trace = _aggregate(tfs)
    assert final == "WAIT"
    analysis = _analysis_from_tfs(tfs, final=final, conf=conf, trace=trace)
    diag = build_mtf_decision_diagnostics(analysis, weights=_WEIGHTS, trace=trace)
    assert diag.final_signal == "WAIT"
    assert "SCORE_INSIDE_WAIT_ZONE" in diag.decision_reasons


def test_score_just_below_long_is_wait() -> None:
    # Force exact weighted ≈ 19.9 via uniform TF scores
    tfs = {name: _tf(name, total=19.9) for name in _WEIGHTS}
    final, _c, _r, _w, trace = _aggregate(tfs)
    assert final == "WAIT"
    assert trace.weighted_score is not None
    assert trace.weighted_score < MTF_LONG_THRESHOLD


def test_score_at_long_threshold_is_long() -> None:
    tfs = {name: _tf(name, total=20.0) for name in _WEIGHTS}
    final, _c, _r, _w, trace = _aggregate(tfs)
    assert final == "LONG"
    assert trace.weighted_score == 20.0


def test_score_just_above_short_is_wait() -> None:
    tfs = {name: _tf(name, total=-19.9) for name in _WEIGHTS}
    final, _c, _r, _w, trace = _aggregate(tfs)
    assert final == "WAIT"
    assert trace.weighted_score is not None
    assert trace.weighted_score > MTF_SHORT_THRESHOLD


def test_score_at_short_threshold_is_short() -> None:
    tfs = {name: _tf(name, total=-20.0) for name in _WEIGHTS}
    final, _c, _r, _w, trace = _aggregate(tfs)
    assert final == "SHORT"
    assert trace.weighted_score == -20.0


def test_h4_d1_conflict_visible_and_forces_wait() -> None:
    tfs = {
        "M15": _tf("M15", total=80),
        "H1": _tf("H1", total=80),
        "H4": _tf("H4", total=80),  # LONG
        "D1": _tf("D1", total=-80, structure=StructureLabel.BEARISH),  # SHORT
    }
    final, conf, _r, warnings, trace = _aggregate(tfs)
    assert final == "WAIT"
    assert trace.h4_d1_conflict is True
    assert any(w.code == "HIGHER_TF_CONFLICT" for w in warnings)
    analysis = _analysis_from_tfs(tfs, final=final, conf=conf, trace=trace)
    diag = build_mtf_decision_diagnostics(analysis, weights=_WEIGHTS, trace=trace)
    assert "H4_D1_CONFLICT" in diag.decision_reasons
    # Score itself may still be directional — conflict forced WAIT
    assert diag.final_signal == "WAIT"
    assert diag.mtf_weighted_score == trace.weighted_score


def test_h1_h4_conflict_visible() -> None:
    tfs = {
        "M15": _tf("M15", total=10),
        "H1": _tf("H1", total=80),  # LONG
        "H4": _tf("H4", total=-80, structure=StructureLabel.BEARISH),  # SHORT
        "D1": _tf("D1", total=0, structure=StructureLabel.RANGE),
    }
    final, conf, _r, warnings, trace = _aggregate(tfs)
    assert trace.h1_h4_conflict is True
    assert any(w.code == "H1_H4_CONFLICT" for w in warnings)
    analysis = _analysis_from_tfs(tfs, final=final, conf=conf, trace=trace)
    diag = build_mtf_decision_diagnostics(analysis, weights=_WEIGHTS, trace=trace)
    assert "H1_H4_CONFLICT" in diag.decision_reasons
    assert diag.conflict_penalty == 0.75


def test_diagnostic_score_equals_engine_score() -> None:
    tfs = {
        "M15": _tf("M15", total=40),
        "H1": _tf("H1", total=30),
        "H4": _tf("H4", total=10),
        "D1": _tf("D1", total=-5),
    }
    final, conf, _r, _w, trace = _aggregate(tfs)
    expected = (
        0.20 * 40 + 0.30 * 30 + 0.30 * 10 + 0.20 * (-5)
    ) / 1.0
    assert trace.weighted_score == expected
    analysis = _analysis_from_tfs(tfs, final=final, conf=conf, trace=trace)
    diag = build_mtf_decision_diagnostics(analysis, weights=_WEIGHTS, trace=trace)
    assert diag.mtf_weighted_score == trace.weighted_score == expected
    assert diag.final_signal == final == analysis.final_signal


def test_diagnostics_do_not_mutate_final_signal() -> None:
    tfs = {name: _tf(name, total=12.0) for name in _WEIGHTS}
    final, conf, _r, _w, trace = _aggregate(tfs)
    analysis = _analysis_from_tfs(tfs, final=final, conf=conf, trace=trace)
    before = analysis.final_signal
    _ = build_mtf_decision_diagnostics(analysis, weights=_WEIGHTS, trace=trace)
    _ = derive_decision_reasons(analysis=analysis, trace=trace)
    assert analysis.final_signal == before == "WAIT"


def test_distance_to_thresholds() -> None:
    trace = MtfAggregateTrace(
        weighted_score=12.4,
        base_direction="WAIT",
        final_signal="WAIT",
        confidence=40.0,
        h4_d1_conflict=False,
        h1_h4_conflict=False,
        conflict_penalty=1.0,
    )
    tfs = {name: _tf(name, total=12.4, momentum=0.0) for name in _WEIGHTS}
    analysis = _analysis_from_tfs(tfs, final="WAIT", conf=40.0, trace=trace)
    diag = build_mtf_decision_diagnostics(analysis, weights=_WEIGHTS, trace=trace)
    assert diag.distance_to_long_threshold == 20.0 - 12.4
    assert diag.distance_to_short_threshold == 12.4 - (-20.0)
