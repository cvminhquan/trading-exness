"""Normalize + validate ProviderGroundedResult → ExternalMarketContext."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from exness_bot.market_analysis.external_context.alignment import (
    align_external_with_technical,
)
from exness_bot.market_analysis.external_context.freshness import (
    classify_external_freshness,
)
from exness_bot.market_analysis.external_context.models import (
    SCHEMA_VERSION,
    CacheMeta,
    ClaimType,
    ContextStatus,
    DirectionForGold,
    EventRiskLevel,
    EvidenceStrength,
    ExternalBias,
    ExternalClaim,
    ExternalFreshness,
    ExternalMarketContext,
    ExternalSource,
    ImportantEvent,
    MarketDriver,
)
from exness_bot.market_analysis.external_context.provider_base import (
    ProviderGroundedResult,
)
from exness_bot.market_analysis.external_context.sources import (
    classify_source_type,
    dedupe_urls,
    domain_of,
    normalize_url,
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _enum_or(default: str, value: str | None, allowed: set[str]) -> str:
    if value is None:
        return default
    v = str(value).strip().upper()
    return v if v in allowed else default


def normalize_provider_result(
    *,
    result: ProviderGroundedResult,
    symbol: str,
    snapshot: dict[str, Any],
    search_plan: dict[str, Any],
    technical_fingerprint: str,
    technical_snapshot_timestamp: str | None,
    cache: CacheMeta,
    now: datetime,
) -> ExternalMarketContext:
    retrieved_at = now.astimezone(UTC).isoformat()

    # Sources
    sources: list[ExternalSource] = []
    url_to_id: dict[str, str] = {}
    for i, ref in enumerate(result.sources, start=1):
        url = normalize_url(ref.url)
        if url is None:
            continue
        if url in url_to_id:
            continue
        sid = f"src_{i}"
        url_to_id[url] = sid
        pub = _parse_dt(ref.published_at)
        freshness = classify_external_freshness(pub, now=now)
        domain = domain_of(url)
        sources.append(
            ExternalSource(
                source_id=sid,
                title=(ref.title or domain)[:300],
                url=url,
                domain=domain,
                published_at=None if pub is None else pub.isoformat(),
                retrieved_at=retrieved_at,
                freshness=freshness.value,
                source_type=classify_source_type(domain).value,
                grounding_provider=result.provider,
                topic=ref.topic,
            )
        )

    def map_urls(urls: list[str]) -> list[str]:
        ids: list[str] = []
        for u in dedupe_urls(urls):
            sid = url_to_id.get(u)
            if sid:
                ids.append(sid)
        return ids

    claims: list[ExternalClaim] = []
    for i, c in enumerate(result.claims, start=1):
        sids = map_urls(c.source_urls)
        supported = bool(c.supported and sids)
        claims.append(
            ExternalClaim(
                claim_id=f"claim_{i}",
                category=str(c.category)[:64],
                claim_type=_enum_or(
                    ClaimType.COMMENTARY.value,
                    c.claim_type,
                    {x.value for x in ClaimType},
                ),
                text=c.text[:1000],
                source_ids=sids,
                supported=supported,
                direction_for_gold=_enum_or(
                    DirectionForGold.UNKNOWN.value,
                    c.direction_for_gold,
                    {x.value for x in DirectionForGold},
                )
                if c.direction_for_gold
                else None,
                freshness=None,
            )
        )

    drivers: list[MarketDriver] = []
    for d in result.drivers:
        drivers.append(
            MarketDriver(
                driver=str(d.driver)[:64],
                direction_for_gold=_enum_or(
                    DirectionForGold.UNKNOWN.value,
                    d.direction_for_gold,
                    {x.value for x in DirectionForGold},
                ),
                summary=d.summary[:500],
                evidence_strength=_enum_or(
                    EvidenceStrength.WEAK.value,
                    d.evidence_strength,
                    {x.value for x in EvidenceStrength},
                ),
                source_ids=map_urls(d.source_urls),
            )
        )

    events: list[ImportantEvent] = []
    for e in result.events:
        events.append(
            ImportantEvent(
                event_name=e.event_name[:200],
                event_type=e.event_type[:64],
                importance=_enum_or(
                    EventRiskLevel.UNKNOWN.value,
                    e.importance,
                    {x.value for x in EventRiskLevel},
                ),
                status=str(e.status or "UNKNOWN")[:32],
                direction_known=bool(e.direction_known),
                scheduled_at=e.scheduled_at if _parse_dt(e.scheduled_at) else None,
                note=e.note,
                source_ids=map_urls(e.source_urls),
            )
        )

    bias = _enum_or(
        ExternalBias.INSUFFICIENT_EVIDENCE.value,
        result.external_bias,
        {x.value for x in ExternalBias},
    )
    # Invalid provider enum already remapped; still catch garbage from malformed
    try:
        bias_enum = ExternalBias(bias)
    except ValueError:
        bias_enum = ExternalBias.INSUFFICIENT_EVIDENCE
        bias = bias_enum.value

    strength = _enum_or(
        EvidenceStrength.INSUFFICIENT.value,
        result.evidence_strength,
        {x.value for x in EvidenceStrength},
    )
    event_risk = _enum_or(
        EventRiskLevel.UNKNOWN.value,
        result.event_risk,
        {x.value for x in EventRiskLevel},
    )

    alignment = align_external_with_technical(
        external_bias=bias_enum, snapshot=snapshot
    )

    if not result.ok:
        status = _enum_or(
            ContextStatus.UNAVAILABLE.value,
            result.status_hint,
            {x.value for x in ContextStatus},
        )
    elif not sources and claims:
        status = ContextStatus.INSUFFICIENT_EVIDENCE.value
        strength = EvidenceStrength.INSUFFICIENT.value
    elif result.status_hint == "PARTIAL":
        status = ContextStatus.PARTIAL.value
    elif not sources:
        status = ContextStatus.INSUFFICIENT_EVIDENCE.value
        strength = EvidenceStrength.INSUFFICIENT.value
    else:
        status = ContextStatus.AVAILABLE.value

    # Overall context freshness from newest dated source
    dated = [s for s in sources if s.freshness != ExternalFreshness.UNDATED.value]
    if not dated:
        overall_fresh = ExternalFreshness.UNDATED.value
    else:
        # Prefer most "current" label among sources
        order = [
            ExternalFreshness.BREAKING.value,
            ExternalFreshness.RECENT.value,
            ExternalFreshness.CURRENT.value,
            ExternalFreshness.STALE.value,
        ]
        overall_fresh = ExternalFreshness.STALE.value
        for label in order:
            if any(s.freshness == label for s in dated):
                overall_fresh = label
                break

    return ExternalMarketContext(
        schema_version=SCHEMA_VERSION,
        symbol=symbol.strip().upper(),
        generated_at=retrieved_at,
        status=status,
        technical_snapshot_timestamp=technical_snapshot_timestamp,
        technical_fingerprint=technical_fingerprint,
        provider=result.provider,
        provider_model=result.model,
        external_bias=bias,
        evidence_strength=strength,
        alignment_with_technical=alignment.value,
        event_risk=event_risk,
        market_drivers=drivers,
        important_events=events,
        supporting_factors=list(result.supporting_factors)[:10],
        conflicting_factors=list(result.conflicting_factors)[:10],
        unknowns=list(result.unknowns)[:10],
        claims=claims,
        sources=sources,
        search_plan=search_plan,
        search_queries=list(result.search_queries)[:20],
        freshness=overall_fresh,
        data_quality={
            "source_count": len(sources),
            "claim_count": len(claims),
            "supported_claim_count": sum(1 for c in claims if c.supported),
            "provider_ok": result.ok,
            "provider_error": result.error,
            "latency_ms": result.latency_ms,
        },
        cache=cache,
    )


def disabled_context(
    *,
    symbol: str,
    reason: str,
    fingerprint: str | None = None,
    now: datetime | None = None,
) -> ExternalMarketContext:
    now_utc = now or datetime.now(tz=UTC)
    return ExternalMarketContext(
        schema_version=SCHEMA_VERSION,
        symbol=symbol.strip().upper(),
        generated_at=now_utc.isoformat(),
        status=ContextStatus.DISABLED.value,
        technical_snapshot_timestamp=None,
        technical_fingerprint=fingerprint,
        provider="none",
        provider_model=None,
        external_bias=ExternalBias.INSUFFICIENT_EVIDENCE.value,
        evidence_strength=EvidenceStrength.INSUFFICIENT.value,
        alignment_with_technical="INSUFFICIENT_DATA",
        event_risk=EventRiskLevel.UNKNOWN.value,
        market_drivers=[],
        important_events=[],
        supporting_factors=[],
        conflicting_factors=[],
        unknowns=[reason],
        claims=[],
        sources=[],
        search_plan={},
        search_queries=[],
        freshness=ExternalFreshness.UNDATED.value,
        data_quality={"reason": reason},
        cache=CacheMeta(hit=False, age_seconds=None, expires_at=None),
    )
