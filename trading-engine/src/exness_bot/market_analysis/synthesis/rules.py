"""Deterministic synthesis rules — state, views, fallback narrative.

AI never chooses SynthesisState. Precedence (RULE_VERSION 1.0):

1. Insufficient technical primary bias → INSUFFICIENT_CONTEXT
2. event_risk == HIGH → HIGH_EVENT_RISK
   (alignment still exposed separately in external_view)
3. Technical directional + SUPPORT (+ strong/moderate evidence)
   → TECHNICAL_EXTERNAL_ALIGNED
4. Technical directional + CONFLICT (+ strong/moderate)
   → TECHNICAL_EXTERNAL_CONFLICT
5. Technical directional + SUPPORT + weak/insufficient evidence
   → EXTERNAL_SUPPORT_WEAK
6. Technical directional + CONFLICT + weak/insufficient evidence
   → EXTERNAL_CONFLICT_WEAK
7. Technical directional + MIXED / external MIXED
   → TECHNICAL_DOMINANT_EXTERNAL_MIXED
8. Technical neutral + external directional
   → TECHNICAL_NEUTRAL_EXTERNAL_DIRECTIONAL
9. Technical directional + external neutral / insufficient
   → TECHNICAL_DIRECTIONAL_EXTERNAL_NEUTRAL
10. Else → INSUFFICIENT_CONTEXT
"""

from __future__ import annotations

from typing import Any

from exness_bot.market_analysis.synthesis.models import (
    FactOrigin,
    MarketSynthesisNarrative,
    SourceRef,
    SynthesisFact,
    SynthesisState,
    SynthesisStatus,
)

_WEAK_EVIDENCE = frozenset({"WEAK", "INSUFFICIENT"})
_DIRECTIONAL_TECH = frozenset({"BULLISH", "BEARISH"})
_DIRECTIONAL_EXT = frozenset({"BULLISH_FOR_GOLD", "BEARISH_FOR_GOLD"})
_EXTERNAL_OK = frozenset({"AVAILABLE", "PARTIAL", "STALE", "INSUFFICIENT_EVIDENCE"})


def _m15_bias(snapshot: dict[str, Any]) -> str:
    tfs = snapshot.get("timeframes") or {}
    m15 = tfs.get("M15") or {}
    trend = str(m15.get("trend") or "").upper()
    if trend in {"BULLISH", "UPTREND"}:
        return "BULLISH"
    if trend in {"BEARISH", "DOWNTREND"}:
        return "BEARISH"
    if trend in {"NEUTRAL", "RANGE", "UNKNOWN", "", "INSUFFICIENT"}:
        return "NEUTRAL"
    return "UNKNOWN"


def _tf_block(snapshot: dict[str, Any], tf: str) -> dict[str, Any]:
    tfs = snapshot.get("timeframes") or {}
    block = tfs.get(tf) or {}
    return {
        "trend": block.get("trend"),
        "structure": block.get("structure"),
        "last_closed_candle_timestamp": block.get("last_closed_candle_timestamp"),
    }


def build_technical_view(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize from TechnicalMarketSnapshot — never recalculate."""
    bot = snapshot.get("bot_analysis") or {}
    mtf = snapshot.get("mtf_summary") or {}
    m15 = (snapshot.get("timeframes") or {}).get("M15") or {}
    wick = m15.get("wick") or {}
    impulse = m15.get("descriptive_impulse") or {}
    return {
        "primary_timeframe": "M15",
        "primary_bias": _m15_bias(snapshot),
        "bot_signal": bot.get("signal"),
        "bot_strategy": bot.get("production_strategy") or "mtf_technical_v1",
        "setup_state": bot.get("setup_state"),
        "execution_status": bot.get("execution_status"),
        "mtf_alignment": mtf.get("alignment"),
        "timeframes": {
            "M15": _tf_block(snapshot, "M15"),
            "H1": _tf_block(snapshot, "H1"),
            "H4": _tf_block(snapshot, "H4"),
            "D1": _tf_block(snapshot, "D1"),
        },
        "nearest_support": m15.get("nearest_support"),
        "nearest_resistance": m15.get("nearest_resistance"),
        "wick_rejection": wick.get("pattern"),
        "impulse_summary": impulse,
        "current_price": snapshot.get("current_price"),
    }


def build_external_view(external: dict[str, Any] | None) -> dict[str, Any]:
    if not external:
        return {
            "status": "UNAVAILABLE",
            "external_bias": "INSUFFICIENT_EVIDENCE",
            "evidence_strength": "INSUFFICIENT",
            "alignment_with_technical": "INSUFFICIENT_DATA",
            "event_risk": "UNKNOWN",
            "top_drivers": [],
            "important_events": [],
            "supporting_factors": [],
            "conflicting_factors": [],
            "source_count": 0,
            "freshness": "UNDATED",
            "provider_chips": [],
        }
    drivers = external.get("market_drivers") or external.get("top_market_drivers") or []
    chips = external.get("provider_chips")
    if not isinstance(chips, list):
        chips = []
    return {
        "status": external.get("status"),
        "external_bias": external.get("external_bias"),
        "evidence_strength": external.get("evidence_strength"),
        "alignment_with_technical": external.get("alignment_with_technical"),
        "event_risk": external.get("event_risk"),
        "top_drivers": list(drivers)[:5],
        "important_events": list(external.get("important_events") or [])[:5],
        "supporting_factors": list(external.get("supporting_factors") or [])[:5],
        "conflicting_factors": list(external.get("conflicting_factors") or [])[:5],
        "source_count": len(external.get("sources") or []),
        "freshness": external.get("freshness"),
        "provider_chips": [str(c) for c in chips if c],
    }


def resolve_synthesis_status(
    *,
    technical_ok: bool,
    technical_stale: bool,
    external: dict[str, Any] | None,
) -> str:
    ext_status = str((external or {}).get("status") or "UNAVAILABLE").upper()
    external_usable = ext_status in _EXTERNAL_OK or ext_status == "AVAILABLE"
    external_present = external is not None and ext_status not in {
        "DISABLED",
        "UNAVAILABLE",
        "",
    }

    if not technical_ok and not external_present:
        return SynthesisStatus.UNAVAILABLE.value
    if not technical_ok and external_present:
        return SynthesisStatus.EXTERNAL_ONLY.value
    if technical_ok and not external_present:
        return SynthesisStatus.TECHNICAL_ONLY.value
    if technical_stale:
        return SynthesisStatus.STALE.value
    if technical_ok and external_usable:
        if ext_status in {"PARTIAL", "STALE", "INSUFFICIENT_EVIDENCE"}:
            return SynthesisStatus.PARTIAL.value
        return SynthesisStatus.AVAILABLE.value
    if technical_ok:
        return SynthesisStatus.TECHNICAL_ONLY.value
    return SynthesisStatus.UNAVAILABLE.value


def resolve_synthesis_state(
    *,
    technical_view: dict[str, Any],
    external_view: dict[str, Any],
) -> SynthesisState:
    tech = str(technical_view.get("primary_bias") or "UNKNOWN").upper()
    ext_bias = str(external_view.get("external_bias") or "INSUFFICIENT_EVIDENCE").upper()
    alignment = str(
        external_view.get("alignment_with_technical") or "INSUFFICIENT_DATA"
    ).upper()
    strength = str(external_view.get("evidence_strength") or "INSUFFICIENT").upper()
    event_risk = str(external_view.get("event_risk") or "UNKNOWN").upper()
    ext_status = str(external_view.get("status") or "UNAVAILABLE").upper()

    if tech in {"UNKNOWN", ""} and not technical_view.get("bot_signal"):
        return SynthesisState.INSUFFICIENT_CONTEXT

    # High event risk wins state label; alignment remains in external_view.
    if event_risk == "HIGH" and tech in _DIRECTIONAL_TECH:
        return SynthesisState.HIGH_EVENT_RISK

    if ext_status in {"DISABLED", "UNAVAILABLE"} or ext_bias == "INSUFFICIENT_EVIDENCE":
        if tech in _DIRECTIONAL_TECH:
            return SynthesisState.TECHNICAL_DIRECTIONAL_EXTERNAL_NEUTRAL
        return SynthesisState.INSUFFICIENT_CONTEXT

    if tech == "NEUTRAL" and ext_bias in _DIRECTIONAL_EXT:
        return SynthesisState.TECHNICAL_NEUTRAL_EXTERNAL_DIRECTIONAL

    if tech in _DIRECTIONAL_TECH:
        if alignment == "MIXED" or ext_bias == "MIXED":
            return SynthesisState.TECHNICAL_DOMINANT_EXTERNAL_MIXED
        if alignment == "SUPPORT":
            if strength in _WEAK_EVIDENCE:
                return SynthesisState.EXTERNAL_SUPPORT_WEAK
            return SynthesisState.TECHNICAL_EXTERNAL_ALIGNED
        if alignment == "CONFLICT":
            if strength in _WEAK_EVIDENCE:
                return SynthesisState.EXTERNAL_CONFLICT_WEAK
            return SynthesisState.TECHNICAL_EXTERNAL_CONFLICT
        if alignment in {"NEUTRAL", "INSUFFICIENT_DATA"} or ext_bias in {
            "NEUTRAL",
            "INSUFFICIENT_EVIDENCE",
        }:
            return SynthesisState.TECHNICAL_DIRECTIONAL_EXTERNAL_NEUTRAL

    return SynthesisState.INSUFFICIENT_CONTEXT


def _htf_summary(technical_view: dict[str, Any]) -> str:
    tfs = technical_view.get("timeframes") or {}
    parts: list[str] = []
    for tf in ("H1", "H4", "D1"):
        trend = (tfs.get(tf) or {}).get("trend")
        if trend:
            parts.append(f"{tf} {trend}")
    if not parts:
        return "Higher-timeframe context is limited."
    return "Higher timeframes: " + ", ".join(parts) + "."


def build_deterministic_narrative(
    *,
    symbol: str,
    technical_view: dict[str, Any],
    external_view: dict[str, Any],
    state: SynthesisState,
) -> MarketSynthesisNarrative:
    tech_bias = str(technical_view.get("primary_bias") or "UNKNOWN")
    bot_signal = str(technical_view.get("bot_signal") or "WAIT")
    mtf = str(technical_view.get("mtf_alignment") or "UNKNOWN")
    ext_bias = str(external_view.get("external_bias") or "INSUFFICIENT_EVIDENCE")
    alignment = str(
        external_view.get("alignment_with_technical") or "INSUFFICIENT_DATA"
    )
    event_risk = str(external_view.get("event_risk") or "UNKNOWN")
    htf = _htf_summary(technical_view)
    supports = list(external_view.get("supporting_factors") or [])
    conflicts = list(external_view.get("conflicting_factors") or [])

    if state == SynthesisState.TECHNICAL_EXTERNAL_ALIGNED:
        summary = (
            f"{symbol}: technical and external context are currently aligned. "
            f"M15 is {tech_bias}; external evidence is {ext_bias}. {htf} "
            f"Event risk is {event_risk}."
        )
        alignment_explanation = (
            f"M15 {tech_bias} aligns with external {ext_bias} "
            f"(alignment={alignment})."
        )
    elif state == SynthesisState.TECHNICAL_EXTERNAL_CONFLICT:
        summary = (
            f"{symbol}: M15 technical direction is {tech_bias}, while external "
            f"context is {ext_bias}, creating a conflict. {htf} "
            f"Event risk is {event_risk}."
        )
        alignment_explanation = (
            f"M15 is {tech_bias}, but external context leans {ext_bias}, "
            "so external evidence currently conflicts with the primary "
            "technical timeframe."
        )
    elif state == SynthesisState.HIGH_EVENT_RISK:
        summary = (
            f"{symbol}: event risk is HIGH while M15 is {tech_bias} and "
            f"external bias is {ext_bias} (alignment={alignment}). {htf}"
        )
        alignment_explanation = (
            f"Alignment remains {alignment}; elevated event risk does not "
            "imply a directional prediction."
        )
    elif state == SynthesisState.TECHNICAL_DOMINANT_EXTERNAL_MIXED:
        summary = (
            f"{symbol}: M15 is {tech_bias} while external evidence is mixed. "
            f"{htf} Event risk is {event_risk}."
        )
        alignment_explanation = (
            "External drivers pull in more than one direction; M15 remains "
            "the primary technical reference."
        )
    elif state == SynthesisState.TECHNICAL_NEUTRAL_EXTERNAL_DIRECTIONAL:
        summary = (
            f"{symbol}: M15 is neutral while external context is directional "
            f"({ext_bias}). {htf} Event risk is {event_risk}."
        )
        alignment_explanation = (
            "Technical primary is neutral; external evidence is directional "
            "but does not overwrite M15."
        )
    elif state == SynthesisState.TECHNICAL_DIRECTIONAL_EXTERNAL_NEUTRAL:
        summary = (
            f"{symbol}: M15 is {tech_bias}; external context is neutral or "
            f"unavailable. {htf} Event risk is {event_risk}."
        )
        alignment_explanation = (
            "Technical direction stands without clear external confirmation "
            "or conflict."
        )
    elif state == SynthesisState.EXTERNAL_SUPPORT_WEAK:
        summary = (
            f"{symbol}: external evidence weakly supports M15 {tech_bias}. "
            f"{htf} Event risk is {event_risk}."
        )
        alignment_explanation = (
            f"Alignment is SUPPORT but evidence strength is weak "
            f"({external_view.get('evidence_strength')})."
        )
    elif state == SynthesisState.EXTERNAL_CONFLICT_WEAK:
        summary = (
            f"{symbol}: weak external evidence conflicts with M15 {tech_bias}. "
            f"{htf} Event risk is {event_risk}."
        )
        alignment_explanation = (
            "Alignment is CONFLICT but evidence strength is weak."
        )
    else:
        summary = (
            f"{symbol}: insufficient context for a clear technical/external "
            "synthesis."
        )
        alignment_explanation = "Insufficient technical or external context."

    technical_explanation = (
        f"Primary M15 bias is {tech_bias}. Production bot signal is "
        f"{bot_signal} ({technical_view.get('bot_strategy')}). "
        f"MTF alignment is {mtf}. {htf}"
    )
    if technical_view.get("wick_rejection"):
        technical_explanation += (
            f" M15 wick pattern: {technical_view.get('wick_rejection')}."
        )

    if str(external_view.get("status") or "").upper() in {
        "DISABLED",
        "UNAVAILABLE",
        "",
    }:
        external_explanation = (
            "Technical analysis is available, but current external context "
            "is unavailable or disabled."
        )
    else:
        external_explanation = (
            f"External bias is {ext_bias} with evidence strength "
            f"{external_view.get('evidence_strength')}. "
            f"Source count: {external_view.get('source_count', 0)}."
        )
        if supports:
            external_explanation += " Supporting: " + "; ".join(supports[:3]) + "."
        if conflicts:
            external_explanation += " Conflicting: " + "; ".join(conflicts[:3]) + "."

    if event_risk == "HIGH":
        risk_explanation = (
            "Event risk is high because a material macro/market event is "
            "flagged as important. This does not predict the outcome."
        )
    elif event_risk == "MEDIUM":
        risk_explanation = (
            "Event risk is medium; near-term scheduled or unfolding events "
            "may increase volatility."
        )
    else:
        risk_explanation = f"Event risk is currently {event_risk}."

    uncertainties: list[str] = []
    tfs = technical_view.get("timeframes") or {}
    m15_t = (tfs.get("M15") or {}).get("trend")
    h4_t = (tfs.get("H4") or {}).get("trend")
    if m15_t and h4_t and str(m15_t).upper() != str(h4_t).upper():
        uncertainties.append("H4 disagrees with M15")
    if alignment == "CONFLICT":
        uncertainties.append("External evidence conflicts with M15")
    if alignment == "MIXED" or ext_bias == "MIXED":
        uncertainties.append("External sources conflict or mixed")
    if str(external_view.get("evidence_strength") or "").upper() in _WEAK_EVIDENCE:
        uncertainties.append("External evidence weak")
    if str(external_view.get("freshness") or "").upper() == "UNDATED":
        uncertainties.append("External sources undated")
    if str(external_view.get("status") or "").upper() in {"DISABLED", "UNAVAILABLE"}:
        uncertainties.append("External context unavailable")
    if not technical_view.get("wick_rejection") or technical_view.get(
        "wick_rejection"
    ) == "NO_CLEAR_REJECTION":
        uncertainties.append("No confirmed rejection wick")

    what_to_watch: list[str] = [
        "Watch whether M15 structure and trend remain consistent with the "
        f"current {tech_bias} bias.",
    ]
    if technical_view.get("nearest_resistance"):
        what_to_watch.append(
            "Watch whether price interacts with the nearest resistance from "
            "the technical snapshot."
        )
    if technical_view.get("nearest_support"):
        what_to_watch.append(
            "Watch whether price interacts with the nearest support from "
            "the technical snapshot."
        )
    if event_risk in {"HIGH", "MEDIUM"}:
        what_to_watch.append(
            "Watch upcoming or ongoing macro events flagged in external context."
        )
    what_to_watch.append(
        "Watch whether H1/H4/D1 remain aligned or conflicting with M15."
    )

    return MarketSynthesisNarrative(
        summary=summary,
        technical_explanation=technical_explanation,
        external_explanation=external_explanation,
        alignment_explanation=alignment_explanation,
        risk_explanation=risk_explanation,
        uncertainties=uncertainties[:8],
        what_to_watch=what_to_watch[:6],
    )


def build_facts(
    *,
    technical_view: dict[str, Any],
    external_view: dict[str, Any],
    state: SynthesisState,
) -> list[SynthesisFact]:
    facts = [
        SynthesisFact(
            fact_id="fact_tech_bias",
            category="TECHNICAL",
            text=f"M15 primary bias is {technical_view.get('primary_bias')}",
            origin=FactOrigin.TECHNICAL.value,
        ),
        SynthesisFact(
            fact_id="fact_bot_signal",
            category="TECHNICAL",
            text=(
                f"Bot signal is {technical_view.get('bot_signal')} "
                f"({technical_view.get('bot_strategy')})"
            ),
            origin=FactOrigin.TECHNICAL.value,
        ),
        SynthesisFact(
            fact_id="fact_ext_bias",
            category="EXTERNAL",
            text=f"External bias is {external_view.get('external_bias')}",
            origin=FactOrigin.EXTERNAL.value,
        ),
        SynthesisFact(
            fact_id="fact_state",
            category="SYNTHESIS",
            text=f"Deterministic synthesis state is {state.value}",
            origin=FactOrigin.SYNTHESIS_RULE.value,
        ),
    ]
    return facts


def extract_sources(external: dict[str, Any] | None) -> list[SourceRef]:
    if not external:
        return []
    out: list[SourceRef] = []
    for s in external.get("sources") or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("source_id") or "").strip()
        url = str(s.get("url") or "").strip()
        if not sid or not url:
            continue
        out.append(
            SourceRef(
                source_id=sid,
                title=str(s.get("title") or sid)[:300],
                domain=str(s.get("domain") or "")[:200],
                url=url,
                published_at=s.get("published_at"),
                retrieved_at=s.get("retrieved_at"),
                freshness=s.get("freshness"),
            )
        )
    return out
