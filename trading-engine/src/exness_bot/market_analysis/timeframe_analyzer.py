"""Per-timeframe closed-candle analysis (reusable for backtest/paper/live read)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.indicators.calculator import IndicatorCalculator
from exness_bot.indicators.ema import calculate_ema
from exness_bot.indicators.macd import macd_snapshot
from exness_bot.market_analysis.levels import (
    build_support_resistance,
    nearest_resistance_above,
    nearest_support_below,
)
from exness_bot.market_analysis.models import AnalysisReason
from exness_bot.market_analysis.patterns import PatternSnapshot, detect_pattern
from exness_bot.market_analysis.scoring import ScoreBreakdown, compute_timeframe_score
from exness_bot.market_analysis.signal import reason
from exness_bot.market_analysis.structure import (
    StructureLabel,
    classify_structure,
    label_swings,
)
from exness_bot.market_analysis.swings import detect_confirmed_swings
from exness_bot.market_analysis.trend import TrendLabel, classify_trend
from exness_bot.market_analysis.volume import VolumeSnapshot, analyze_tick_volume
from exness_bot.market_data.candles import candles_to_dataframe


@dataclass
class TimeframeAnalysis:
    timeframe: str
    candle_timestamp: datetime | None
    close: float | None
    trend: TrendLabel
    signal: str
    confidence: float
    score: ScoreBreakdown | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    rsi14: float | None
    atr14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    macd_momentum: str
    structure_classification: StructureLabel
    sequence: list[str]
    latest_swing_high: float | None
    latest_swing_low: float | None
    nearest_support: float | None
    nearest_resistance: float | None
    supports: list[float]
    resistances: list[float]
    volume: VolumeSnapshot
    pattern: PatternSnapshot
    reasons: list[AnalysisReason] = field(default_factory=list)
    status: str = "LIVE"  # LIVE | STALE | INSUFFICIENT


def analyze_timeframe(
    candles: list[Candle],
    *,
    timeframe: Timeframe,
    swing_left: int = 2,
    swing_right: int = 2,
    cluster_atr_mult: float = 0.25,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    volume_avg: int = 20,
    volume_high: float = 1.5,
    volume_low: float = 0.7,
    point: float = 0.01,
    min_bars: int = 60,
) -> TimeframeAnalysis:
    """Analyze one timeframe from CLOSED candles only (caller must filter)."""
    tf = timeframe.value
    if len(candles) < min_bars:
        return TimeframeAnalysis(
            timeframe=tf,
            candle_timestamp=None,
            close=None,
            trend=TrendLabel.UNKNOWN,
            signal="NEUTRAL",
            confidence=0.0,
            score=None,
            ema20=None,
            ema50=None,
            ema200=None,
            rsi14=None,
            atr14=None,
            macd=None,
            macd_signal=None,
            macd_histogram=None,
            macd_momentum="UNKNOWN",
            structure_classification=StructureLabel.UNDETERMINED,
            sequence=[],
            latest_swing_high=None,
            latest_swing_low=None,
            nearest_support=None,
            nearest_resistance=None,
            supports=[],
            resistances=[],
            volume=VolumeSnapshot("TICK_VOLUME", None, None, None, "UNKNOWN"),
            pattern=PatternSnapshot("NONE", 0.0, ["insufficient_history"]),
            reasons=[
                reason(
                    "INSUFFICIENT_CANDLE_HISTORY",
                    False,
                    f"{tf} needs >= {min_bars} closed candles, got {len(candles)}",
                )
            ],
            status="INSUFFICIENT",
        )

    latest = candles[-1]
    close = float(latest.close)
    bars = candles_to_dataframe(candles)
    snap = IndicatorCalculator.compute(bars)
    close_series = bars["close"].astype(float)
    ema20_series = calculate_ema(close_series, 20)
    ema20_tail = [
        float(x)
        for x in ema20_series.dropna().iloc[-5:].tolist()
        if x == x  # not NaN
    ]

    swings = detect_confirmed_swings(candles, left=swing_left, right=swing_right)
    labeled = label_swings(swings)
    structure = classify_structure(labeled)
    supports_l, resistances_l = build_support_resistance(
        swings,
        atr14=snap.atr_14,
        cluster_atr_multiplier=cluster_atr_mult,
        point=point,
    )
    ns = nearest_support_below(supports_l, close)
    nr = nearest_resistance_above(resistances_l, close)

    trend, _ev = classify_trend(
        close=close,
        ema20=snap.ema_20,
        ema50=snap.ema_50,
        ema200=snap.ema_200,
        ema20_tail=ema20_tail,
        structure=structure.classification,
    )

    macd = macd_snapshot(
        close_series, fast=macd_fast, slow=macd_slow, signal_period=macd_signal
    )
    volume = analyze_tick_volume(
        candles,
        average_period=volume_avg,
        high_ratio=volume_high,
        low_ratio=volume_low,
    )
    prior_close = float(candles[-2].close) if len(candles) >= 2 else None
    pattern = detect_pattern(
        trend=trend,
        structure=structure.classification,
        close=close,
        nearest_support=None if ns is None else ns.price,
        nearest_resistance=None if nr is None else nr.price,
        atr14=snap.atr_14,
        volume_state=volume.state,
        prior_close=prior_close,
    )

    score = compute_timeframe_score(
        trend=trend,
        structure=structure.classification,
        rsi=snap.rsi_14,
        macd_momentum=macd.momentum,
        close=close,
        support=None if ns is None else ns.price,
        resistance=None if nr is None else nr.price,
        atr=snap.atr_14,
        volume_state=volume.state,
    )

    reasons = [
        reason("TREND", trend != TrendLabel.UNKNOWN, f"Trend is {trend.value}"),
        reason(
            "STRUCTURE",
            structure.classification != StructureLabel.UNDETERMINED,
            f"Structure is {structure.classification.value}",
        ),
        reason(
            "SCORE_DIRECTION",
            score.direction != "NEUTRAL",
            f"Score {score.total_score:+.1f} → {score.direction}",
        ),
    ]

    return TimeframeAnalysis(
        timeframe=tf,
        candle_timestamp=latest.timestamp,
        close=close,
        trend=trend,
        signal=score.direction,
        confidence=score.confidence,
        score=score,
        ema20=snap.ema_20,
        ema50=snap.ema_50,
        ema200=snap.ema_200,
        rsi14=snap.rsi_14,
        atr14=snap.atr_14,
        macd=macd.macd,
        macd_signal=macd.signal,
        macd_histogram=macd.histogram,
        macd_momentum=macd.momentum,
        structure_classification=structure.classification,
        sequence=list(structure.sequence),
        latest_swing_high=structure.latest_swing_high,
        latest_swing_low=structure.latest_swing_low,
        nearest_support=None if ns is None else ns.price,
        nearest_resistance=None if nr is None else nr.price,
        supports=[level.price for level in supports_l[-5:]],
        resistances=[level.price for level in resistances_l[:5]],
        volume=volume,
        pattern=pattern,
        reasons=reasons,
        status="LIVE",
    )
