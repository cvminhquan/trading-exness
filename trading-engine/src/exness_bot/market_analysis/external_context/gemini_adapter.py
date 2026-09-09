"""Gemini grounded-response adapter — shared by live provider and offline replay.

Accepts either google.genai response objects or dict fixtures with the same
shape (candidates[].grounding_metadata.grounding_chunks[].web).

Does NOT fabricate published_at. Does NOT treat model-written URLs as grounded
sources unless they also appear in grounding metadata.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import structlog

from exness_bot.market_analysis.external_context.models import (
    EventRiskLevel,
    EvidenceStrength,
    ExternalBias,
)
from exness_bot.market_analysis.external_context.provider_base import (
    ProviderClaimDraft,
    ProviderDriverDraft,
    ProviderEventDraft,
    ProviderGroundedResult,
    ProviderSourceRef,
)
from exness_bot.market_analysis.external_context.sources import normalize_url

logger = structlog.get_logger(__name__)


def response_from_dict(payload: dict[str, Any]) -> Any:
    """Convert a JSON fixture into an object tree supporting getattr access."""

    def _convert(value: Any) -> Any:
        if isinstance(value, dict):
            return SimpleNamespace(
                **{str(k): _convert(v) for k, v in value.items()}
            )
        if isinstance(value, list):
            return [_convert(v) for v in value]
        return value

    return _convert(payload)


def extract_grounding_sources(response: Any) -> list[ProviderSourceRef]:
    """Extract citations only from grounding_metadata (not free-text URLs)."""
    sources: list[ProviderSourceRef] = []
    seen: set[str] = set()
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return sources
        meta = getattr(candidates[0], "grounding_metadata", None)
        if meta is None:
            return sources
        chunks = getattr(meta, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web is None:
                if isinstance(chunk, dict):
                    web_data = chunk.get("web")
                    if isinstance(web_data, dict):
                        web = SimpleNamespace(**web_data)
                    else:
                        continue
                else:
                    continue
            uri = getattr(web, "uri", None) or getattr(web, "url", None)
            title = getattr(web, "title", None) or ""
            published = getattr(web, "published_at", None) or getattr(
                web, "publication_date", None
            )
            if not uri:
                continue
            norm = normalize_url(str(uri))
            key = norm or str(uri)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                ProviderSourceRef(
                    title=str(title) or str(uri),
                    url=str(uri),
                    published_at=str(published) if published else None,
                )
            )
    except Exception as exc:
        logger.warning("gemini_grounding_extract_failed", error=type(exc).__name__)
    return sources


def extract_search_queries(response: Any) -> list[str]:
    queries: list[str] = []
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return queries
        meta = getattr(candidates[0], "grounding_metadata", None)
        if meta is None:
            return queries
        for attr in ("web_search_queries", "retrieval_queries"):
            vals = getattr(meta, attr, None)
            if vals:
                queries.extend(str(v) for v in vals)
    except Exception:
        return queries
    return queries


def parse_json_payload(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def adapt_gemini_grounded_response(
    response: Any,
    *,
    provider: str = "gemini_google",
    model: str | None = None,
    latency_ms: float | None = None,
) -> ProviderGroundedResult:
    """Map a Gemini-like response into ProviderGroundedResult.

    Canonical sources come ONLY from grounding_metadata chunks.
    Model-emitted source_urls may reference those URLs but cannot invent new ones.
    """
    text = getattr(response, "text", None)
    if text is None and isinstance(response, dict):
        text = response.get("text")
    text = text or ""

    grounded_sources = extract_grounding_sources(response)
    queries = extract_search_queries(response)
    payload = parse_json_payload(text) or {}

    # Index grounding by normalized URL for claim mapping
    source_map: dict[str, ProviderSourceRef] = {}
    for s in grounded_sources:
        key = normalize_url(s.url)
        if key is None:
            # Reject unsafe / non-http schemes early
            continue
        if key not in source_map:
            source_map[key] = ProviderSourceRef(
                title=s.title,
                url=key,
                published_at=s.published_at,
                topic=s.topic,
            )

    def _filter_urls(urls: list[Any]) -> list[str]:
        out: list[str] = []
        for u in urls:
            if not isinstance(u, str):
                continue
            key = normalize_url(u) or u
            if key in source_map:
                out.append(source_map[key].url)
        return out

    claims: list[ProviderClaimDraft] = []
    for claim in payload.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        urls = _filter_urls(list(claim.get("source_urls") or []))
        claims.append(
            ProviderClaimDraft(
                category=str(claim.get("category") or "OTHER"),
                claim_type=str(claim.get("claim_type") or "COMMENTARY"),
                text=str(claim.get("text") or "")[:1000],
                direction_for_gold=claim.get("direction_for_gold"),
                source_urls=urls,
                supported=bool(urls),
            )
        )

    drivers: list[ProviderDriverDraft] = []
    for d in payload.get("drivers") or []:
        if not isinstance(d, dict):
            continue
        drivers.append(
            ProviderDriverDraft(
                driver=str(d.get("driver") or "OTHER"),
                direction_for_gold=str(d.get("direction_for_gold") or "UNKNOWN"),
                summary=str(d.get("summary") or "")[:500],
                evidence_strength=str(
                    d.get("evidence_strength") or EvidenceStrength.WEAK.value
                ),
                source_urls=_filter_urls(list(d.get("source_urls") or [])),
            )
        )

    events: list[ProviderEventDraft] = []
    for e in payload.get("events") or []:
        if not isinstance(e, dict):
            continue
        events.append(
            ProviderEventDraft(
                event_name=str(e.get("event_name") or "UNKNOWN"),
                event_type=str(e.get("event_type") or "OTHER"),
                importance=str(e.get("importance") or EventRiskLevel.UNKNOWN.value),
                status=str(e.get("status") or "UNKNOWN"),
                direction_known=bool(e.get("direction_known", False)),
                scheduled_at=e.get("scheduled_at"),
                note=e.get("note"),
                source_urls=_filter_urls(list(e.get("source_urls") or [])),
            )
        )

    sources = list(source_map.values())
    bias = str(
        payload.get("external_bias") or ExternalBias.INSUFFICIENT_EVIDENCE.value
    )
    strength = str(
        payload.get("evidence_strength") or EvidenceStrength.INSUFFICIENT.value
    )
    event_risk = str(payload.get("event_risk") or EventRiskLevel.UNKNOWN.value)

    status_hint = "AVAILABLE"
    if not sources:
        status_hint = "INSUFFICIENT_EVIDENCE"
        strength = EvidenceStrength.INSUFFICIENT.value
        if not payload:
            status_hint = "PARTIAL"
    elif not payload:
        status_hint = "PARTIAL"

    # Malformed: candidates missing entirely and no text
    candidates = getattr(response, "candidates", None)
    if candidates is None and isinstance(response, dict):
        candidates = response.get("candidates")
    if candidates is None and not text.strip():
        return ProviderGroundedResult(
            provider=provider,
            model=model,
            ok=False,
            status_hint="UNAVAILABLE",
            external_bias=ExternalBias.INSUFFICIENT_EVIDENCE.value,
            evidence_strength=EvidenceStrength.INSUFFICIENT.value,
            event_risk=EventRiskLevel.UNKNOWN.value,
            claims=[],
            drivers=[],
            events=[],
            sources=[],
            supporting_factors=[],
            conflicting_factors=[],
            unknowns=["malformed_response"],
            search_queries=[],
            error="malformed_response",
            latency_ms=latency_ms,
        )

    return ProviderGroundedResult(
        provider=provider,
        model=model,
        ok=True,
        status_hint=status_hint,
        external_bias=bias,
        evidence_strength=strength,
        event_risk=event_risk,
        claims=claims,
        drivers=drivers,
        events=events,
        sources=sources,
        supporting_factors=[
            str(x) for x in (payload.get("supporting_factors") or []) if x
        ][:10],
        conflicting_factors=[
            str(x) for x in (payload.get("conflicting_factors") or []) if x
        ][:10],
        unknowns=[str(x) for x in (payload.get("unknowns") or []) if x][:10],
        search_queries=queries,
        latency_ms=latency_ms,
        raw_text=text[:2000] if text else None,
    )
