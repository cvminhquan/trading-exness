"""ExternalIntelligenceProvider abstraction + DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from exness_bot.market_analysis.external_context.models import ExternalSearchPlan


@dataclass
class ExternalIntelligenceRequest:
    symbol: str
    snapshot: dict[str, Any]
    search_plan: ExternalSearchPlan
    utc_now_iso: str
    technical_fingerprint: str


@dataclass
class ProviderSourceRef:
    title: str
    url: str
    published_at: str | None = None
    topic: str | None = None


@dataclass
class ProviderClaimDraft:
    category: str
    claim_type: str
    text: str
    direction_for_gold: str | None = None
    source_urls: list[str] = field(default_factory=list)
    supported: bool = True


@dataclass
class ProviderDriverDraft:
    driver: str
    direction_for_gold: str
    summary: str
    evidence_strength: str
    source_urls: list[str] = field(default_factory=list)


@dataclass
class ProviderEventDraft:
    event_name: str
    event_type: str
    importance: str
    status: str
    direction_known: bool = False
    scheduled_at: str | None = None
    note: str | None = None
    source_urls: list[str] = field(default_factory=list)


@dataclass
class ProviderGroundedResult:
    provider: str
    model: str | None
    ok: bool
    status_hint: str
    external_bias: str
    evidence_strength: str
    event_risk: str
    claims: list[ProviderClaimDraft]
    drivers: list[ProviderDriverDraft]
    events: list[ProviderEventDraft]
    sources: list[ProviderSourceRef]
    supporting_factors: list[str]
    conflicting_factors: list[str]
    unknowns: list[str]
    search_queries: list[str]
    error: str | None = None
    latency_ms: float | None = None
    raw_text: str | None = None


class ExternalIntelligenceProvider(Protocol):
    name: str

    def fetch_context(
        self, request: ExternalIntelligenceRequest
    ) -> ProviderGroundedResult: ...
