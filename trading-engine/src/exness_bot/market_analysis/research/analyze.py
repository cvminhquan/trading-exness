"""Build v1/v2 TF scores from closed candle windows (research-only)."""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.mtf_service import (
    DEFAULT_TF_WEIGHTS,
    MTF_LONG_THRESHOLD,
    MTF_SHORT_THRESHOLD,
)
from exness_bot.market_analysis.research.aggregate_v2 import (
    AggregateV2Result,
    TfScoreInput,
    aggregate_v2,
)
from exness_bot.market_analysis.research.freeze import DEFAULT_V2_CONFIG, V2FrozenConfig
from exness_bot.market_analysis.research.historical import resample_from_m15
from exness_bot.market_analysis.research.scoring_v2 import (
    ScoreBreakdownV2,
    compute_timeframe_score_v2,
)
from exness_bot.market_analysis.scoring import ScoreBreakdown
from exness_bot.market_analysis.structure import classify_structure, label_swings
from exness_bot.market_analysis.swings import detect_confirmed_swings
from exness_bot.market_analysis.timeframe_analyzer import analyze_timeframe


@dataclass(frozen=True)
class AggregateV1Result:
    weighted_score: float | None
    direction: str
    confidence: float
    h4_d1_conflict: bool
    tf_scores: dict[str, float]


def analyze_score_v2_from_candles(
    candles: list[Candle],
    *,
    timeframe: Timeframe,
    config: V2FrozenConfig = DEFAULT_V2_CONFIG,
    min_bars: int = 60,
) -> tuple[ScoreBreakdownV2 | None, str]:
    """Return (score, status). Reuses analyze_timeframe features; replaces scorer."""
    base = analyze_timeframe(candles, timeframe=timeframe, min_bars=min_bars)
    if base.status == "INSUFFICIENT" or base.close is None:
        return None, "INSUFFICIENT"

    swings = detect_confirmed_swings(candles, left=2, right=2)
    labeled = label_swings(swings)
    structure = classify_structure(labeled)
    closes = [float(c.close) for c in candles]
    apply_impulse = timeframe == Timeframe.M15
    score = compute_timeframe_score_v2(
        trend=base.trend,
        structure_snapshot=structure,
        rsi=base.rsi14,
        macd_momentum=base.macd_momentum,
        close=base.close,
        support=base.nearest_support,
        resistance=base.nearest_resistance,
        atr=base.atr14,
        volume_state=base.volume.state,
        closes=closes,
        apply_impulse=apply_impulse,
        config=config,
    )
    return score, base.status


def aggregate_v1_from_scores(
    tf_scores: dict[str, ScoreBreakdown | None],
    *,
    weights: dict[str, float] | None = None,
) -> AggregateV1Result:
    """Mirror production `_aggregate` semantics for research comparison."""
    wmap = weights or dict(DEFAULT_TF_WEIGHTS)
    weighted = 0.0
    conf_acc = 0.0
    w_sum = 0.0
    directions: dict[str, str] = {}
    scores_out: dict[str, float] = {}

    for tf, score in tf_scores.items():
        if score is None:
            continue
        w = float(wmap.get(tf, 0.0))
        weighted += w * score.total_score
        conf_acc += w * score.confidence
        w_sum += w
        directions[tf] = score.direction
        scores_out[tf] = score.total_score

    if w_sum <= 0:
        return AggregateV1Result(None, "WAIT", 0.0, False, scores_out)

    total = weighted / w_sum
    conf = conf_acc / w_sum
    h4 = directions.get("H4")
    d1 = directions.get("D1")
    h4_d1 = bool(h4 and d1 and h4 != d1 and "NEUTRAL" not in {h4, d1})
    if h4_d1:
        return AggregateV1Result(
            round(total, 2), "WAIT", round(conf * 0.6, 2), True, scores_out
        )
    if total >= MTF_LONG_THRESHOLD:
        direction = "LONG"
    elif total <= MTF_SHORT_THRESHOLD:
        direction = "SHORT"
    else:
        direction = "WAIT"
    return AggregateV1Result(round(total, 2), direction, round(conf, 2), False, scores_out)


def evaluate_mtf_window(
    m15: list[Candle],
    *,
    symbol: str = "XAUUSD",
    config: V2FrozenConfig = DEFAULT_V2_CONFIG,
    min_bars: int = 60,
    lookback: int = 250,
) -> tuple[AggregateV1Result, AggregateV2Result, float | None]:
    """Score v1 vs v2 on a closed M15 window. Returns (v1, v2, m15_atr)."""
    window = m15[-lookback:] if len(m15) > lookback else m15
    frames = {
        "M15": window,
        "H1": resample_from_m15(window, Timeframe.H1, symbol=symbol),
        "H4": resample_from_m15(window, Timeframe.H4, symbol=symbol),
        "D1": resample_from_m15(window, Timeframe.D1, symbol=symbol),
    }
    v1_scores: dict[str, ScoreBreakdown | None] = {}
    v2_inputs: list[TfScoreInput] = []
    m15_atr: float | None = None
    for name, tf in [
        ("M15", Timeframe.M15),
        ("H1", Timeframe.H1),
        ("H4", Timeframe.H4),
        ("D1", Timeframe.D1),
    ]:
        candles = frames[name]
        tf_min = min_bars if tf == Timeframe.M15 else max(20, min_bars // 4)
        if len(candles) < tf_min:
            v1_scores[name] = None
            v2_inputs.append(TfScoreInput(name, None, "INSUFFICIENT"))
            continue
        a = analyze_timeframe(candles, timeframe=tf, min_bars=tf_min)
        v1_scores[name] = a.score if a.status != "INSUFFICIENT" else None
        if tf == Timeframe.M15 and a.atr14 is not None:
            m15_atr = float(a.atr14)
        if a.status == "INSUFFICIENT" or a.close is None:
            v2_inputs.append(TfScoreInput(name, None, "INSUFFICIENT"))
            continue
        swings = detect_confirmed_swings(candles, left=2, right=2)
        labeled = label_swings(swings)
        structure = classify_structure(labeled)
        closes = [float(c.close) for c in candles]
        s2 = compute_timeframe_score_v2(
            trend=a.trend,
            structure_snapshot=structure,
            rsi=a.rsi14,
            macd_momentum=a.macd_momentum,
            close=a.close,
            support=a.nearest_support,
            resistance=a.nearest_resistance,
            atr=a.atr14,
            volume_state=a.volume.state,
            closes=closes,
            apply_impulse=(tf == Timeframe.M15),
            config=config,
        )
        v2_inputs.append(TfScoreInput(name, s2, a.status))

    return (
        aggregate_v1_from_scores(v1_scores),
        aggregate_v2(v2_inputs, config=config),
        m15_atr,
    )
