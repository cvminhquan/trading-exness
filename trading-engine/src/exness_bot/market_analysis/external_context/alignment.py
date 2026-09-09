"""Alignment between external bias and M15 primary technical trend.

Uses M15 only as primary technical reference (not H4/D1 override).
Descriptive only — never mutates scores or execution.
"""

from __future__ import annotations

from typing import Any

from exness_bot.market_analysis.external_context.models import (
    AlignmentWithTechnical,
    ExternalBias,
)


def m15_technical_bias(snapshot: dict[str, Any]) -> str:
    tfs = snapshot.get("timeframes") or {}
    m15 = tfs.get("M15") or {}
    trend = str(m15.get("trend") or "").upper()
    if trend in {"BULLISH", "UPTREND"}:
        return "BULLISH"
    if trend in {"BEARISH", "DOWNTREND"}:
        return "BEARISH"
    if trend in {"NEUTRAL", "RANGE", "UNKNOWN", ""}:
        return "NEUTRAL"
    return "NEUTRAL"


def align_external_with_technical(
    *,
    external_bias: ExternalBias | str,
    snapshot: dict[str, Any],
) -> AlignmentWithTechnical:
    bias = (
        external_bias
        if isinstance(external_bias, ExternalBias)
        else ExternalBias(str(external_bias))
    )
    if bias == ExternalBias.INSUFFICIENT_EVIDENCE:
        return AlignmentWithTechnical.INSUFFICIENT_DATA

    tech = m15_technical_bias(snapshot)
    if tech == "NEUTRAL":
        if bias in {ExternalBias.MIXED, ExternalBias.NEUTRAL}:
            return AlignmentWithTechnical.NEUTRAL
        return AlignmentWithTechnical.MIXED

    if bias == ExternalBias.MIXED:
        return AlignmentWithTechnical.MIXED
    if bias == ExternalBias.NEUTRAL:
        return AlignmentWithTechnical.NEUTRAL

    ext_bull = bias == ExternalBias.BULLISH_FOR_GOLD
    tech_bull = tech == "BULLISH"
    if ext_bull == tech_bull:
        return AlignmentWithTechnical.SUPPORT
    return AlignmentWithTechnical.CONFLICT
