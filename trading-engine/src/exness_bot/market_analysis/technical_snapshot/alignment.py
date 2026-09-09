"""Deterministic MTF alignment summary — facts only, no win probability."""

from __future__ import annotations

from exness_bot.market_analysis.technical_snapshot.models import (
    MtfAlignmentState,
    MtfSummary,
)

_BULLISH = {"UPTREND", "BULLISH"}
_BEARISH = {"DOWNTREND", "BEARISH"}
_NEUTRAL = {"RANGE", "NEUTRAL", "UNKNOWN", "UNDETERMINED"}


def _normalize_bias(label: str | None) -> str:
    if label is None:
        return "INSUFFICIENT"
    u = label.upper()
    if u in _BULLISH or u == "UPTREND":
        return "BULLISH"
    if u in _BEARISH or u == "DOWNTREND":
        return "BEARISH"
    if u in _NEUTRAL:
        return "NEUTRAL"
    if u in {"INSUFFICIENT", "INSUFFICIENT_DATA"}:
        return "INSUFFICIENT"
    return "NEUTRAL"


def summarize_mtf_alignment(per_tf_trend: dict[str, str | None]) -> MtfSummary:
    """Rules:

    - primary_bias = M15 mapped bias (or INSUFFICIENT)
    - confirmation = H1 vs M15: ALIGNED / CONFLICTING / NEUTRAL / INSUFFICIENT_DATA
    - higher_timeframe_context = H4+D1 combined vs primary
    - alignment overall enum from those components
    """
    mapped = {tf: _normalize_bias(v) for tf, v in per_tf_trend.items()}
    m15 = mapped.get("M15", "INSUFFICIENT")
    h1 = mapped.get("H1", "INSUFFICIENT")
    h4 = mapped.get("H4", "INSUFFICIENT")
    d1 = mapped.get("D1", "INSUFFICIENT")

    primary = m15 if m15 != "INSUFFICIENT" else "NEUTRAL"

    if "INSUFFICIENT" in {m15, h1} and m15 == "INSUFFICIENT":
        confirmation = MtfAlignmentState.INSUFFICIENT_DATA.value
    elif h1 == "INSUFFICIENT" or h1 == "NEUTRAL" or m15 == "NEUTRAL":
        confirmation = MtfAlignmentState.NEUTRAL.value
    elif h1 == m15:
        confirmation = MtfAlignmentState.ALIGNED.value
    else:
        confirmation = MtfAlignmentState.CONFLICTING.value

    higher = [b for b in (h4, d1) if b != "INSUFFICIENT"]
    if not higher:
        htf = MtfAlignmentState.INSUFFICIENT_DATA.value
    else:
        bull = sum(1 for b in higher if b == "BULLISH")
        bear = sum(1 for b in higher if b == "BEARISH")
        if bull and bear:
            htf = MtfAlignmentState.MIXED.value
        elif (bull and primary == "BULLISH") or (bear and primary == "BEARISH"):
            htf = MtfAlignmentState.ALIGNED.value
        elif bull or bear:
            if primary in {"BULLISH", "BEARISH"} and (
                (bull and primary == "BEARISH") or (bear and primary == "BULLISH")
            ):
                htf = MtfAlignmentState.CONFLICTING.value
            else:
                htf = MtfAlignmentState.MIXED.value
        else:
            htf = MtfAlignmentState.NEUTRAL.value

    # Overall
    if m15 == "INSUFFICIENT":
        overall = MtfAlignmentState.INSUFFICIENT_DATA
    elif (
        confirmation == MtfAlignmentState.ALIGNED.value
        and htf == MtfAlignmentState.ALIGNED.value
    ):
        overall = MtfAlignmentState.ALIGNED
    elif (
        confirmation == MtfAlignmentState.CONFLICTING.value
        or htf == MtfAlignmentState.CONFLICTING.value
    ):
        overall = MtfAlignmentState.CONFLICTING
    elif (
        htf == MtfAlignmentState.MIXED.value
        or confirmation == MtfAlignmentState.NEUTRAL.value
    ):
        overall = (
            MtfAlignmentState.MIXED
            if htf == MtfAlignmentState.MIXED.value
            else MtfAlignmentState.PARTIALLY_ALIGNED
        )
    else:
        overall = MtfAlignmentState.PARTIALLY_ALIGNED

    notes: list[str] = []
    if confirmation == MtfAlignmentState.ALIGNED.value:
        notes.append("H1 confirmation aligns with M15 primary bias.")
    elif confirmation == MtfAlignmentState.CONFLICTING.value:
        notes.append("H1 confirmation conflicts with M15 primary bias.")
    if htf == MtfAlignmentState.MIXED.value:
        notes.append("H4/D1 higher-timeframe context is mixed.")
    elif htf == MtfAlignmentState.CONFLICTING.value:
        notes.append("H4/D1 higher-timeframe context conflicts with M15.")

    return MtfSummary(
        primary_bias=primary if primary != "INSUFFICIENT" else "NEUTRAL",
        confirmation=confirmation,
        higher_timeframe_context=htf,
        alignment=overall.value,
        per_timeframe_trend={k: mapped.get(k, "INSUFFICIENT") for k in ("M15", "H1", "H4", "D1")},
        notes=notes,
    )
