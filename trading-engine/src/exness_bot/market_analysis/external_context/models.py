"""Typed ExternalMarketContext — structured, source-grounded, JSON-safe."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "1.0"


class ExternalBias(StrEnum):
    BULLISH_FOR_GOLD = "BULLISH_FOR_GOLD"
    BEARISH_FOR_GOLD = "BEARISH_FOR_GOLD"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceStrength(StrEnum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    INSUFFICIENT = "INSUFFICIENT"


class AlignmentWithTechnical(StrEnum):
    SUPPORT = "SUPPORT"
    CONFLICT = "CONFLICT"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EventRiskLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ContextStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DISABLED = "DISABLED"
    UNAVAILABLE = "UNAVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ClaimType(StrEnum):
    FACT = "FACT"
    COMMENTARY = "COMMENTARY"
    INFERENCE = "INFERENCE"


class SourceType(StrEnum):
    OFFICIAL = "OFFICIAL"
    MAJOR_NEWS = "MAJOR_NEWS"
    FINANCIAL_NEWS = "FINANCIAL_NEWS"
    MARKET_DATA = "MARKET_DATA"
    COMMENTARY = "COMMENTARY"
    UNKNOWN = "UNKNOWN"


class ExternalFreshness(StrEnum):
    BREAKING = "BREAKING"
    RECENT = "RECENT"
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNDATED = "UNDATED"


class SearchTopic(StrEnum):
    GOLD_MARKET = "GOLD_MARKET"
    USD = "USD"
    TREASURY_YIELDS = "TREASURY_YIELDS"
    FED = "FED"
    US_MACRO = "US_MACRO"
    GEOPOLITICS = "GEOPOLITICS"
    RISK_SENTIMENT = "RISK_SENTIMENT"


class DriverKind(StrEnum):
    USD = "USD"
    TREASURY_YIELDS = "TREASURY_YIELDS"
    FED_POLICY = "FED_POLICY"
    INFLATION = "INFLATION"
    EMPLOYMENT = "EMPLOYMENT"
    GEOPOLITICS = "GEOPOLITICS"
    RISK_SENTIMENT = "RISK_SENTIMENT"
    CENTRAL_BANK_DEMAND = "CENTRAL_BANK_DEMAND"
    GOLD_SPECIFIC = "GOLD_SPECIFIC"
    OTHER = "OTHER"


class DirectionForGold(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


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
class ExternalSource:
    source_id: str
    title: str
    url: str
    domain: str
    retrieved_at: str
    freshness: str
    source_type: str
    published_at: str | None = None
    grounding_provider: str = "gemini_google"
    topic: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class ExternalClaim:
    claim_id: str
    category: str
    claim_type: str
    text: str
    source_ids: list[str]
    supported: bool
    direction_for_gold: str | None = None
    event_time: str | None = None
    published_at: str | None = None
    freshness: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class MarketDriver:
    driver: str
    direction_for_gold: str
    summary: str
    evidence_strength: str
    source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class ImportantEvent:
    event_name: str
    event_type: str
    importance: str
    status: str
    direction_known: bool = False
    scheduled_at: str | None = None
    time_until_event_seconds: float | None = None
    source_ids: list[str] = field(default_factory=list)
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class SearchTopicItem:
    topic: str
    purpose: str
    priority: int

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class ExternalSearchPlan:
    symbol: str
    generated_at: str
    technical_context_summary: str
    search_topics: list[SearchTopicItem]
    time_sensitivity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "generated_at": self.generated_at,
            "technical_context_summary": self.technical_context_summary,
            "search_topics": [t.to_dict() for t in self.search_topics],
            "time_sensitivity": self.time_sensitivity,
        }


@dataclass
class CacheMeta:
    hit: bool
    age_seconds: float | None
    expires_at: str | None
    fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class ExternalMarketContext:
    schema_version: str
    symbol: str
    generated_at: str
    status: str
    technical_snapshot_timestamp: str | None
    technical_fingerprint: str | None
    provider: str
    provider_model: str | None
    external_bias: str
    evidence_strength: str
    alignment_with_technical: str
    event_risk: str
    market_drivers: list[MarketDriver]
    important_events: list[ImportantEvent]
    supporting_factors: list[str]
    conflicting_factors: list[str]
    unknowns: list[str]
    claims: list[ExternalClaim]
    sources: list[ExternalSource]
    search_plan: dict[str, Any]
    search_queries: list[str]
    freshness: str
    data_quality: dict[str, Any]
    cache: CacheMeta
    note: str = (
        "ExternalMarketContext is descriptive context only. "
        "It does not modify or approve trades."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "generated_at": self.generated_at,
            "status": self.status,
            "technical_snapshot_timestamp": self.technical_snapshot_timestamp,
            "technical_fingerprint": self.technical_fingerprint,
            "provider": self.provider,
            "provider_model": self.provider_model,
            "external_bias": self.external_bias,
            "evidence_strength": self.evidence_strength,
            "alignment_with_technical": self.alignment_with_technical,
            "event_risk": self.event_risk,
            "market_drivers": [d.to_dict() for d in self.market_drivers],
            "important_events": [e.to_dict() for e in self.important_events],
            "supporting_factors": list(self.supporting_factors),
            "conflicting_factors": list(self.conflicting_factors),
            "unknowns": list(self.unknowns),
            "claims": [c.to_dict() for c in self.claims],
            "sources": [s.to_dict() for s in self.sources],
            "search_plan": _as_dict(self.search_plan),
            "search_queries": list(self.search_queries),
            "freshness": self.freshness,
            "data_quality": _as_dict(self.data_quality),
            "cache": self.cache.to_dict(),
            "note": self.note,
        }

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "generated_at": self.generated_at,
            "status": self.status,
            "external_bias": self.external_bias,
            "evidence_strength": self.evidence_strength,
            "alignment_with_technical": self.alignment_with_technical,
            "event_risk": self.event_risk,
            "top_market_drivers": [d.to_dict() for d in self.market_drivers[:5]],
            "important_events": [e.to_dict() for e in self.important_events[:5]],
            "supporting_factors": list(self.supporting_factors[:5]),
            "conflicting_factors": list(self.conflicting_factors[:5]),
            "source_summaries": [
                {
                    "source_id": s.source_id,
                    "title": s.title,
                    "domain": s.domain,
                    "freshness": s.freshness,
                }
                for s in self.sources[:8]
            ],
            "freshness": self.freshness,
            "cache": self.cache.to_dict(),
        }
