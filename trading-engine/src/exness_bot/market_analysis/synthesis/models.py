"""Typed MarketSynthesis — human-facing analysis only (Phase 16.3.3)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "1.0"
RULE_VERSION = "1.0"


class SynthesisStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    TECHNICAL_ONLY = "TECHNICAL_ONLY"
    EXTERNAL_ONLY = "EXTERNAL_ONLY"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class SynthesisState(StrEnum):
    TECHNICAL_EXTERNAL_ALIGNED = "TECHNICAL_EXTERNAL_ALIGNED"
    TECHNICAL_EXTERNAL_CONFLICT = "TECHNICAL_EXTERNAL_CONFLICT"
    TECHNICAL_DOMINANT_EXTERNAL_MIXED = "TECHNICAL_DOMINANT_EXTERNAL_MIXED"
    EXTERNAL_SUPPORT_WEAK = "EXTERNAL_SUPPORT_WEAK"
    EXTERNAL_CONFLICT_WEAK = "EXTERNAL_CONFLICT_WEAK"
    TECHNICAL_NEUTRAL_EXTERNAL_DIRECTIONAL = "TECHNICAL_NEUTRAL_EXTERNAL_DIRECTIONAL"
    TECHNICAL_DIRECTIONAL_EXTERNAL_NEUTRAL = "TECHNICAL_DIRECTIONAL_EXTERNAL_NEUTRAL"
    HIGH_EVENT_RISK = "HIGH_EVENT_RISK"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class FactOrigin(StrEnum):
    TECHNICAL = "TECHNICAL"
    EXTERNAL = "EXTERNAL"
    SYNTHESIS_RULE = "SYNTHESIS_RULE"


def _safe_float(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def _json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, StrEnum):
        return str(obj.value)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, float):
        return _safe_float(obj)
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dataclass_fields__"):
        return _json_safe(asdict(obj))
    return obj


def _as_dict(payload: dict[str, Any]) -> dict[str, Any]:
    result = _json_safe(payload)
    return result if isinstance(result, dict) else {}


@dataclass
class SynthesisFact:
    fact_id: str
    category: str
    text: str
    origin: str
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class SourceRef:
    source_id: str
    title: str
    domain: str
    url: str
    published_at: str | None = None
    retrieved_at: str | None = None
    freshness: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class AiMetadata:
    enabled: bool
    provider: str | None
    model: str | None
    used: bool
    fallback_used: bool
    latency_ms: float | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class CacheMeta:
    hit: bool
    age_seconds: float | None
    expires_at: str | None
    fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class MarketSynthesisNarrative:
    summary: str
    technical_explanation: str
    external_explanation: str
    alignment_explanation: str
    risk_explanation: str
    uncertainties: list[str] = field(default_factory=list)
    what_to_watch: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class MarketSynthesis:
    schema_version: str
    symbol: str
    generated_at: str
    status: str
    technical_snapshot_timestamp: str | None
    external_context_timestamp: str | None
    technical_fingerprint: str | None
    external_fingerprint: str | None
    synthesis_fingerprint: str | None
    rule_version: str
    technical_view: dict[str, Any]
    external_view: dict[str, Any]
    synthesis_state: str
    narrative: MarketSynthesisNarrative
    facts: list[SynthesisFact]
    sources: list[SourceRef]
    freshness: dict[str, Any]
    data_quality: dict[str, Any]
    ai_metadata: AiMetadata
    cache: CacheMeta
    note: str = (
        "MarketSynthesis is human-facing analysis only. "
        "It does not generate or approve trades."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "generated_at": self.generated_at,
            "status": self.status,
            "technical_snapshot_timestamp": self.technical_snapshot_timestamp,
            "external_context_timestamp": self.external_context_timestamp,
            "technical_fingerprint": self.technical_fingerprint,
            "external_fingerprint": self.external_fingerprint,
            "synthesis_fingerprint": self.synthesis_fingerprint,
            "rule_version": self.rule_version,
            "technical_view": _as_dict(self.technical_view),
            "external_view": _as_dict(self.external_view),
            "synthesis": {
                "state": self.synthesis_state,
                **self.narrative.to_dict(),
            },
            "facts": [f.to_dict() for f in self.facts],
            "sources": [s.to_dict() for s in self.sources],
            "freshness": _as_dict(self.freshness),
            "data_quality": _as_dict(self.data_quality),
            "ai_metadata": self.ai_metadata.to_dict(),
            "cache": self.cache.to_dict(),
            "note": self.note,
        }

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "generated_at": self.generated_at,
            "status": self.status,
            "synthesis_state": self.synthesis_state,
            "technical_primary_bias": self.technical_view.get("primary_bias"),
            "bot_signal": self.technical_view.get("bot_signal"),
            "mtf_alignment": self.technical_view.get("mtf_alignment"),
            "external_bias": self.external_view.get("external_bias"),
            "external_alignment": self.external_view.get("alignment_with_technical"),
            "event_risk": self.external_view.get("event_risk"),
            "top_supporting_factors": list(
                self.external_view.get("supporting_factors") or []
            )[:5],
            "top_conflicting_factors": list(
                self.external_view.get("conflicting_factors") or []
            )[:5],
            "uncertainties": list(self.narrative.uncertainties[:6]),
            "what_to_watch": list(self.narrative.what_to_watch[:6]),
            "summary": self.narrative.summary,
            "source_refs": [
                {
                    "source_id": s.source_id,
                    "title": s.title,
                    "domain": s.domain,
                }
                for s in self.sources[:8]
            ],
            "ai_metadata": self.ai_metadata.to_dict(),
            "cache": self.cache.to_dict(),
        }
