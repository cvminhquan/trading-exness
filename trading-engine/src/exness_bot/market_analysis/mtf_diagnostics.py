"""Phase 17.2.3 — read-only MTF decision diagnostics (observability only).

Reuses the exact aggregate values produced by MultiTimeframeAnalysisService.
Does not recompute a parallel scoring engine or mutate strategy rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exness_bot.market_analysis.mtf_service import (
        MtfAggregateTrace,
        MultiTimeframeAnalysis,
    )

from exness_bot.market_analysis.timeframe_analyzer import TimeframeAnalysis

TF_ORDER = ("M15", "H1", "H4", "D1")


@dataclass(frozen=True)
class TimeframeDecisionSlice:
    timeframe: str
    data_state: str
    last_closed_candle: datetime | None
    close: float | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    rsi14: float | None
    atr14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    structure: str
    nearest_support: float | None
    nearest_resistance: float | None
    trend_score: float | None
    structure_score: float | None
    momentum_score: float | None
    location_score: float | None
    volume_score: float | None
    raw_score: float | None
    weight: float
    weighted_contribution: float | None


@dataclass(frozen=True)
class MtfDecisionDiagnostics:
    """Snapshot of the engine decision — display only."""

    slices: tuple[TimeframeDecisionSlice, ...]
    m15_score: float | None
    h1_score: float | None
    h4_score: float | None
    d1_score: float | None
    mtf_weighted_score: float | None
    long_threshold: float
    short_threshold: float
    base_direction: str
    h1_h4_conflict: bool
    h4_d1_conflict: bool
    conflict_penalty: float
    final_signal: str
    confidence: float
    confidence_meaning: str
    decision_reasons: tuple[str, ...]
    distance_to_long_threshold: float | None
    distance_to_short_threshold: float | None


def _structure_label(analysis: TimeframeAnalysis) -> str:
    raw = analysis.structure_classification
    return str(getattr(raw, "value", raw))


def _slice_for_tf(
    *,
    name: str,
    analysis: TimeframeAnalysis | None,
    weight: float,
) -> TimeframeDecisionSlice:
    if analysis is None:
        return TimeframeDecisionSlice(
            timeframe=name,
            data_state="UNAVAILABLE",
            last_closed_candle=None,
            close=None,
            ema20=None,
            ema50=None,
            ema200=None,
            rsi14=None,
            atr14=None,
            macd=None,
            macd_signal=None,
            macd_histogram=None,
            structure="UNDETERMINED",
            nearest_support=None,
            nearest_resistance=None,
            trend_score=None,
            structure_score=None,
            momentum_score=None,
            location_score=None,
            volume_score=None,
            raw_score=None,
            weight=weight,
            weighted_contribution=None,
        )
    score = analysis.score
    raw = None if score is None else float(score.total_score)
    contrib = None if raw is None else float(weight) * raw
    return TimeframeDecisionSlice(
        timeframe=name,
        data_state=str(analysis.status),
        last_closed_candle=analysis.candle_timestamp,
        close=analysis.close,
        ema20=analysis.ema20,
        ema50=analysis.ema50,
        ema200=analysis.ema200,
        rsi14=analysis.rsi14,
        atr14=analysis.atr14,
        macd=analysis.macd,
        macd_signal=analysis.macd_signal,
        macd_histogram=analysis.macd_histogram,
        structure=_structure_label(analysis),
        nearest_support=analysis.nearest_support,
        nearest_resistance=analysis.nearest_resistance,
        trend_score=None if score is None else float(score.trend_score),
        structure_score=None if score is None else float(score.structure_score),
        momentum_score=None if score is None else float(score.momentum_score),
        location_score=None if score is None else float(score.location_score),
        volume_score=None if score is None else float(score.volume_score),
        raw_score=raw,
        weight=float(weight),
        weighted_contribution=contrib,
    )


def derive_decision_reasons(
    *,
    analysis: MultiTimeframeAnalysis,
    trace: MtfAggregateTrace,
) -> tuple[str, ...]:
    """Human-readable WHY codes from engine evidence only."""
    reasons: list[str] = []
    if trace.h4_d1_conflict:
        reasons.append("H4_D1_CONFLICT")
    if trace.h1_h4_conflict:
        reasons.append("H1_H4_CONFLICT")

    score = trace.weighted_score
    if (
        score is not None
        and trace.final_signal == "WAIT"
        and not trace.h4_d1_conflict
        and trace.short_threshold < score < trace.long_threshold
    ):
        reasons.append("SCORE_INSIDE_WAIT_ZONE")

    trend_vals = [
        float(tf.score.trend_score)
        for tf in analysis.timeframes.values()
        if tf.score is not None
    ]
    if trend_vals and abs(sum(trend_vals) / len(trend_vals)) < 40.0:
        reasons.append("TREND_EVIDENCE_WEAK")

    structures = {
        _structure_label(tf)
        for tf in analysis.timeframes.values()
        if tf.status != "INSUFFICIENT"
    }
    bull_bear = {"BULLISH", "BEARISH"} & structures
    if len(bull_bear) >= 2 or ("RANGE" in structures and bull_bear):
        reasons.append("STRUCTURE_MIXED")

    mom_vals = [
        float(tf.score.momentum_score)
        for tf in analysis.timeframes.values()
        if tf.score is not None
    ]
    if mom_vals and abs(sum(mom_vals) / len(mom_vals)) < 25.0:
        reasons.append("MOMENTUM_NEUTRAL")

    if trace.final_signal == "WAIT":
        dirs = {
            tf.signal
            for tf in analysis.timeframes.values()
            if tf.score is not None and tf.signal != "NEUTRAL"
        }
        if len(dirs) != 1:
            reasons.append("NO_DIRECTIONAL_ALIGNMENT")

    return tuple(dict.fromkeys(reasons))


def build_mtf_decision_diagnostics(
    analysis: MultiTimeframeAnalysis,
    *,
    weights: dict[str, float],
    trace: MtfAggregateTrace,
) -> MtfDecisionDiagnostics:
    """Assemble diagnostics from closed-candle analysis + exact aggregate trace."""
    slices = tuple(
        _slice_for_tf(
            name=name,
            analysis=analysis.timeframes.get(name),
            weight=float(weights.get(name, 0.0)),
        )
        for name in TF_ORDER
    )
    by_name = {s.timeframe: s.raw_score for s in slices}
    score = trace.weighted_score
    dist_long = None if score is None else float(trace.long_threshold) - float(score)
    dist_short = None if score is None else float(score) - float(trace.short_threshold)

    return MtfDecisionDiagnostics(
        slices=slices,
        m15_score=by_name.get("M15"),
        h1_score=by_name.get("H1"),
        h4_score=by_name.get("H4"),
        d1_score=by_name.get("D1"),
        mtf_weighted_score=score,
        long_threshold=float(trace.long_threshold),
        short_threshold=float(trace.short_threshold),
        base_direction=trace.base_direction,
        h1_h4_conflict=trace.h1_h4_conflict,
        h4_d1_conflict=trace.h4_d1_conflict,
        conflict_penalty=float(trace.conflict_penalty),
        final_signal=trace.final_signal,
        confidence=float(trace.confidence),
        confidence_meaning=analysis.confidence_meaning or "EVIDENCE_ALIGNMENT",
        decision_reasons=derive_decision_reasons(analysis=analysis, trace=trace),
        distance_to_long_threshold=dist_long,
        distance_to_short_threshold=dist_short,
    )



def _fmt_num(value: float | None, *, signed: bool = False, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if signed:
        return f"{value:+.{digits}f}"
    return f"{value:.{digits}f}"


def format_mtf_decision_summary(diag: MtfDecisionDiagnostics) -> list[str]:
    """Compact MTF block for watcher full reports."""
    why = diag.decision_reasons or ("—",)
    return [
        "MTF DECISION",
        "--------------------------------",
        f"M15: {_fmt_num(diag.m15_score, signed=True)}",
        f"H1 : {_fmt_num(diag.h1_score, signed=True)}",
        f"H4 : {_fmt_num(diag.h4_score, signed=True)}",
        f"D1 : {_fmt_num(diag.d1_score, signed=True)}",
        "",
        f"WEIGHTED: {_fmt_num(diag.mtf_weighted_score, signed=True)}",
        (
            f"THRESHOLDS: SHORT <= {diag.short_threshold:g} | "
            f"LONG >= {diag.long_threshold:g}"
        ),
        f"BASE_DIRECTION: {diag.base_direction}",
        f"H1_H4_CONFLICT: {'YES' if diag.h1_h4_conflict else 'NO'}",
        f"H4_D1_CONFLICT: {'YES' if diag.h4_d1_conflict else 'NO'}",
        f"CONFLICT_PENALTY: {diag.conflict_penalty:g}",
        f"DISTANCE_TO_LONG_THRESHOLD: {_fmt_num(diag.distance_to_long_threshold)}",
        f"DISTANCE_TO_SHORT_THRESHOLD: {_fmt_num(diag.distance_to_short_threshold)}",
        "",
        f"FINAL: {diag.final_signal}",
        f"CONFIDENCE: {_fmt_num(diag.confidence)}",
        f"CONFIDENCE_MEANING: {diag.confidence_meaning}",
        "WHY:",
        *[f"- {code}" for code in why],
        "--------------------------------",
    ]


def format_mtf_verbose_timeframes(diag: MtfDecisionDiagnostics) -> list[str]:
    """Full per-TF indicator / component dump (--verbose-analysis)."""
    lines: list[str] = ["MTF TIMEFRAMES (CLOSED CANDLES)", "--------------------------------"]
    for s in diag.slices:
        candle = (
            s.last_closed_candle.isoformat() if s.last_closed_candle is not None else "N/A"
        )
        lines.extend(
            [
                f"TIMEFRAME: {s.timeframe}",
                f"DATA_STATE: {s.data_state}",
                f"LAST_CLOSED_CANDLE: {candle}",
                f"CLOSE: {_fmt_num(s.close)}",
                f"EMA20: {_fmt_num(s.ema20)}",
                f"EMA50: {_fmt_num(s.ema50)}",
                f"EMA200: {_fmt_num(s.ema200)}",
                f"RSI14: {_fmt_num(s.rsi14)}",
                f"ATR14: {_fmt_num(s.atr14)}",
                f"MACD: {_fmt_num(s.macd)}",
                f"MACD_SIGNAL: {_fmt_num(s.macd_signal)}",
                f"MACD_HISTOGRAM: {_fmt_num(s.macd_histogram)}",
                f"STRUCTURE: {s.structure}",
                f"NEAREST_SUPPORT: {_fmt_num(s.nearest_support)}",
                f"NEAREST_RESISTANCE: {_fmt_num(s.nearest_resistance)}",
                f"TREND_SCORE: {_fmt_num(s.trend_score, signed=True)}",
                f"STRUCTURE_SCORE: {_fmt_num(s.structure_score, signed=True)}",
                f"MOMENTUM_SCORE: {_fmt_num(s.momentum_score, signed=True)}",
                f"LOCATION_SCORE: {_fmt_num(s.location_score, signed=True)}",
                f"VOLUME_SCORE: {_fmt_num(s.volume_score, signed=True)}",
                f"TIMEFRAME_RAW_SCORE: {_fmt_num(s.raw_score, signed=True)}",
                f"TIMEFRAME_WEIGHT: {s.weight:g}",
                f"WEIGHTED_CONTRIBUTION: {_fmt_num(s.weighted_contribution, signed=True)}",
                "--------------------------------",
            ]
        )
    lines.extend(
        [
            f"M15_SCORE: {_fmt_num(diag.m15_score, signed=True)}",
            f"H1_SCORE: {_fmt_num(diag.h1_score, signed=True)}",
            f"H4_SCORE: {_fmt_num(diag.h4_score, signed=True)}",
            f"D1_SCORE: {_fmt_num(diag.d1_score, signed=True)}",
            f"MTF_WEIGHTED_SCORE: {_fmt_num(diag.mtf_weighted_score, signed=True)}",
            f"LONG_THRESHOLD: {diag.long_threshold:g}",
            f"SHORT_THRESHOLD: {diag.short_threshold:g}",
            f"DECISION_REASONS: {', '.join(diag.decision_reasons) or '—'}",
        ]
    )
    return lines
