"""M15-first aggregation with separated direction / context / blockers."""

from __future__ import annotations

from dataclasses import dataclass

from exness_bot.market_analysis.research.freeze import DEFAULT_V2_CONFIG, V2FrozenConfig
from exness_bot.market_analysis.research.scoring_v2 import ScoreBreakdownV2


@dataclass(frozen=True)
class AggregateV2Result:
    weighted_score: float | None
    direction: str  # LONG | SHORT | WAIT
    confidence: float
    context_warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    m15_impulse: float | None
    tf_scores: dict[str, float]
    tf_directions: dict[str, str]


@dataclass
class TfScoreInput:
    timeframe: str
    score: ScoreBreakdownV2 | None
    status: str = "LIVE"


def aggregate_v2(
    tf_inputs: list[TfScoreInput],
    *,
    config: V2FrozenConfig = DEFAULT_V2_CONFIG,
) -> AggregateV2Result:
    weights = dict(config.tf_weights)
    weighted = 0.0
    w_sum = 0.0
    conf_acc = 0.0
    tf_scores: dict[str, float] = {}
    tf_dirs: dict[str, str] = {}
    m15_impulse: float | None = None
    warnings: list[str] = []
    blockers: list[str] = []

    for item in tf_inputs:
        if item.score is None or item.status == "INSUFFICIENT":
            warnings.append(f"TF_{item.timeframe}_INSUFFICIENT")
            continue
        w = float(weights.get(item.timeframe, 0.0))
        weighted += w * item.score.total_score
        conf_acc += w * item.score.confidence
        w_sum += w
        tf_scores[item.timeframe] = item.score.total_score
        tf_dirs[item.timeframe] = item.score.direction
        if item.timeframe == "M15":
            m15_impulse = item.score.impulse_score

    if w_sum <= 0:
        return AggregateV2Result(
            weighted_score=None,
            direction="WAIT",
            confidence=0.0,
            context_warnings=tuple(warnings),
            blockers=("NO_TF_DATA",),
            m15_impulse=None,
            tf_scores=tf_scores,
            tf_directions=tf_dirs,
        )

    score = round(weighted / w_sum, 2)
    confidence = round(conf_acc / w_sum, 2)

    m15_dir = tf_dirs.get("M15", "NEUTRAL")
    h1_dir = tf_dirs.get("H1", "NEUTRAL")
    h4_dir = tf_dirs.get("H4", "NEUTRAL")
    d1_dir = tf_dirs.get("D1", "NEUTRAL")

    # Context warnings — NOT automatic veto
    if h4_dir != "NEUTRAL" and m15_dir != "NEUTRAL" and h4_dir != m15_dir:
        warnings.append("CONTEXT_H4_DISAGREES_M15")
    if d1_dir != "NEUTRAL" and m15_dir != "NEUTRAL" and d1_dir != m15_dir:
        warnings.append("CONTEXT_D1_DISAGREES_M15")
    if h1_dir != "NEUTRAL" and m15_dir != "NEUTRAL" and h1_dir != m15_dir:
        warnings.append("CONTEXT_H1_DISAGREES_M15")
    if h4_dir != "NEUTRAL" and d1_dir != "NEUTRAL" and h4_dir != d1_dir:
        warnings.append("CONTEXT_H4_D1_MIXED")

    # Explicit optional blocker (default OFF)
    if config.higher_tf_strong_conflict_enabled and (
        m15_dir != "NEUTRAL"
        and h4_dir != "NEUTRAL"
        and d1_dir != "NEUTRAL"
        and h4_dir == d1_dir
        and h4_dir != m15_dir
        and abs(tf_scores.get("M15", 0.0)) < 50.0
    ):
        blockers.append("HIGHER_TF_STRONG_CONFLICT")

    if blockers:
        direction = "WAIT"
    elif score >= config.long_threshold:
        direction = "LONG"
    elif score <= config.short_threshold:
        direction = "SHORT"
    else:
        direction = "WAIT"

    return AggregateV2Result(
        weighted_score=score,
        direction=direction,
        confidence=confidence,
        context_warnings=tuple(dict.fromkeys(warnings)),
        blockers=tuple(blockers),
        m15_impulse=m15_impulse,
        tf_scores=tf_scores,
        tf_directions=tf_dirs,
    )
