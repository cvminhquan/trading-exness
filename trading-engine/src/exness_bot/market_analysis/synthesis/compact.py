"""Compact prompt payload for AI — no secrets, no raw grounding dump."""

from __future__ import annotations

from typing import Any

from exness_bot.market_analysis.synthesis.models import SynthesisState


def build_prompt_payload(
    *,
    symbol: str,
    technical_view: dict[str, Any],
    external_view: dict[str, Any],
    state: SynthesisState,
    sources: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "current_price": technical_view.get("current_price"),
        "deterministic_state": state.value,
        "technical": {
            "primary_bias": technical_view.get("primary_bias"),
            "bot_signal": technical_view.get("bot_signal"),
            "bot_strategy": technical_view.get("bot_strategy"),
            "setup_state": technical_view.get("setup_state"),
            "mtf_alignment": technical_view.get("mtf_alignment"),
            "timeframes": technical_view.get("timeframes"),
            "wick_rejection": technical_view.get("wick_rejection"),
            "nearest_support": technical_view.get("nearest_support"),
            "nearest_resistance": technical_view.get("nearest_resistance"),
            "impulse_summary": technical_view.get("impulse_summary"),
        },
        "external": {
            "status": external_view.get("status"),
            "external_bias": external_view.get("external_bias"),
            "evidence_strength": external_view.get("evidence_strength"),
            "alignment_with_technical": external_view.get("alignment_with_technical"),
            "event_risk": external_view.get("event_risk"),
            "top_drivers": external_view.get("top_drivers"),
            "important_events": external_view.get("important_events"),
            "supporting_factors": external_view.get("supporting_factors"),
            "conflicting_factors": external_view.get("conflicting_factors"),
            "freshness": external_view.get("freshness"),
            "source_count": external_view.get("source_count"),
            "provider_chips": external_view.get("provider_chips") or [],
        },
        "claims": [
            {
                "claim_id": c.get("claim_id"),
                "claim_type": c.get("claim_type"),
                "text": str(c.get("text") or "")[:400],
                "source_ids": c.get("source_ids") or [],
            }
            for c in claims[:12]
            if isinstance(c, dict)
        ],
        "source_summaries": [
            {
                "source_id": s.get("source_id"),
                "title": s.get("title"),
                "domain": s.get("domain"),
                "freshness": s.get("freshness"),
            }
            for s in sources[:12]
            if isinstance(s, dict)
        ],
    }
