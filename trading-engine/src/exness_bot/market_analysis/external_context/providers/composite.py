"""FreeSourcesCompositeProvider — BLS + optional FRED + Fed + RSS → grounded result."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from exness_bot.market_analysis.external_context.macro_normalizer import (
    macro_bias_from_context,
    macro_context_to_dict,
    normalize_macro_items,
)
from exness_bot.market_analysis.external_context.news_normalizer import (
    normalize_news_items,
)
from exness_bot.market_analysis.external_context.provider_base import (
    ExternalIntelligenceRequest,
    ProviderClaimDraft,
    ProviderDriverDraft,
    ProviderEventDraft,
    ProviderGroundedResult,
    ProviderSourceRef,
)
from exness_bot.market_analysis.external_context.providers.base import (
    ExternalDataItem,
    ExternalDataProvider,
    ExternalDataProviderResult,
    ProviderFetchStatus,
    ProviderHealth,
)
from exness_bot.market_analysis.external_context.providers.bls import BlsProvider
from exness_bot.market_analysis.external_context.providers.federal_reserve import (
    FederalReserveProvider,
)
from exness_bot.market_analysis.external_context.providers.fred import FredProvider
from exness_bot.market_analysis.external_context.providers.provider_cache import (
    ProviderResultCache,
)
from exness_bot.market_analysis.external_context.providers.rss import RssProvider
from exness_bot.market_analysis.external_context.sources import normalize_url


def _ttl_for(provider: ExternalDataProvider) -> int:
    return int(getattr(provider, "ttl_seconds", 600))


class FreeSourcesCompositeProvider:
    """Composite free-source provider implementing ExternalIntelligenceProvider."""

    name = "free_sources"

    def __init__(
        self,
        *,
        bls: BlsProvider | None = None,
        fred: FredProvider | None = None,
        federal_reserve: FederalReserveProvider | None = None,
        rss: RssProvider | None = None,
        cache: ProviderResultCache | None = None,
        model_label: str = "free_sources_v1",
    ) -> None:
        self.bls = bls or BlsProvider(enabled=False)
        self.fred = fred or FredProvider(enabled=False)
        self.federal_reserve = federal_reserve or FederalReserveProvider(enabled=False)
        self.rss = rss or RssProvider(enabled=False)
        self._cache = cache or ProviderResultCache()
        self.model = model_label
        self._fetch_counts: dict[str, int] = {
            "bls": 0,
            "fred": 0,
            "federal_reserve": 0,
            "rss": 0,
        }

    def _children(self) -> list[ExternalDataProvider]:
        return [self.bls, self.fred, self.federal_reserve, self.rss]

    def provider_health(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        ref = now or datetime.now(tz=UTC)
        out: list[dict[str, Any]] = []
        for child in self._children():
            h: ProviderHealth = child.health()
            row = h.to_dict()
            row["cache"] = self._cache.status(child.name, now=ref)
            row["ttl_seconds"] = _ttl_for(child)
            row["live_fetch_count"] = self._fetch_counts.get(child.name, 0)
            if child.name == "rss":
                row["feeds"] = list(getattr(child, "feeds", ()))
            out.append(row)
        return out

    def _fetch_child(
        self, child: ExternalDataProvider, *, now: datetime, force: bool = False
    ) -> tuple[ExternalDataProviderResult, bool]:
        if not force:
            cached, hit = self._cache.get(child.name, now=now)
            if hit and cached is not None:
                return cached, True
        result = child.fetch(now=now)
        self._fetch_counts[child.name] = self._fetch_counts.get(child.name, 0) + 1
        # Cache successful and soft-fail states (DISABLED/NOT_CONFIGURED) to avoid hammering
        cacheable = result.status in {
            ProviderFetchStatus.OK.value,
            ProviderFetchStatus.DISABLED.value,
            ProviderFetchStatus.NOT_CONFIGURED.value,
        }
        if cacheable or result.items:
            self._cache.put(
                child.name, result, now=now, ttl_seconds=_ttl_for(child)
            )
        return result, False

    def collect(
        self, *, now: datetime, force_refresh: bool = False
    ) -> dict[str, Any]:
        results: dict[str, ExternalDataProviderResult] = {}
        cache_hits: dict[str, bool] = {}
        for child in self._children():
            res, hit = self._fetch_child(child, now=now, force=force_refresh)
            results[child.name] = res
            cache_hits[child.name] = hit
        return {"results": results, "cache_hits": cache_hits}

    def _to_grounded(
        self,
        *,
        results: dict[str, ExternalDataProviderResult],
        cache_hits: dict[str, bool],
        request: ExternalIntelligenceRequest,
        latency_ms: float,
    ) -> ProviderGroundedResult:
        all_items: list[ExternalDataItem] = []
        for res in results.values():
            all_items.extend(res.items)

        # Deduplicate by canonical URL / series id
        seen_keys: set[str] = set()
        deduped: list[ExternalDataItem] = []
        for item in all_items:
            key = (item.series_id or "") + "|" + (item.canonical_url or item.title)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)

        news_items = [i for i in deduped if i.provider in {"federal_reserve", "rss"}]
        macro_ctx = normalize_macro_items(
            [
                i
                for i in deduped
                if i.provider in {"bls", "fred", "federal_reserve"}
            ]
        )
        news_ctx = normalize_news_items(news_items)
        if news_ctx.geopolitical_hits:
            macro_ctx.geopolitical_context = "ELEVATED"
        elif news_items:
            macro_ctx.geopolitical_context = "QUIET"
        macro_ctx.macro_event_risk = news_ctx.event_risk

        bias = macro_bias_from_context(macro_ctx)
        ok_providers = [
            name
            for name, res in results.items()
            if res.status == ProviderFetchStatus.OK.value and res.items
        ]
        soft_fail = [
            name
            for name, res in results.items()
            if res.status
            in {
                ProviderFetchStatus.DISABLED.value,
                ProviderFetchStatus.NOT_CONFIGURED.value,
            }
        ]
        hard_fail = [
            name
            for name, res in results.items()
            if name not in ok_providers and name not in soft_fail
        ]

        sources: list[ProviderSourceRef] = []
        for item in deduped:
            url = normalize_url(item.canonical_url or "")
            if url is None:
                continue
            sources.append(
                ProviderSourceRef(
                    title=item.title[:300],
                    url=url,
                    published_at=item.published_at,
                    topic=item.category,
                )
            )

        claims: list[ProviderClaimDraft] = []
        for note in macro_ctx.notes[:8]:
            # Attach first matching source URL if any
            urls = [s.url for s in sources[:3]]
            claims.append(
                ProviderClaimDraft(
                    category="US_MACRO",
                    claim_type="FACT",
                    text=note,
                    direction_for_gold=(
                        "BULLISH"
                        if "support" in note.lower()
                        else "BEARISH"
                        if "headwind" in note.lower()
                        else None
                    ),
                    source_urls=urls,
                    supported=bool(urls),
                )
            )
        for item in news_items[:6]:
            url = normalize_url(item.canonical_url or "")
            if url is None:
                continue
            claims.append(
                ProviderClaimDraft(
                    category="FED" if item.provider == "federal_reserve" else "US_MACRO",
                    claim_type="FACT",
                    text=item.title,
                    direction_for_gold=None,
                    source_urls=[url],
                    supported=True,
                )
            )

        drivers: list[ProviderDriverDraft] = []
        dim_map = [
            ("INFLATION", macro_ctx.inflation_context, "inflation"),
            ("EMPLOYMENT", macro_ctx.labor_context, "labor"),
            ("TREASURY_YIELDS", macro_ctx.yield_context, "yield"),
            ("USD", macro_ctx.usd_context, "usd"),
            ("FED_POLICY", macro_ctx.fed_context, "fed"),
        ]
        for driver, state, needle in dim_map:
            if state in {"UNKNOWN"}:
                continue
            note = next((n for n in macro_ctx.notes if needle in n.lower()), state)
            direction = "NEUTRAL"
            if "support" in note.lower() or state in {
                "RISING",
                "FALLING",
                "DOVISH_EVIDENCE",
                "WEAKER",
                "UNEMPLOYMENT_RISING",
                "PAYROLLS_FALLING",
            }:
                # Refine from note language
                if "headwind" in note.lower():
                    direction = "BEARISH"
                elif "support" in note.lower():
                    direction = "BULLISH"
                elif state in {
                    "RISING",
                    "DOVISH_EVIDENCE",
                    "WEAKER",
                    "UNEMPLOYMENT_RISING",
                    "PAYROLLS_FALLING",
                    "FALLING",
                }:
                    # yield FALLING / usd WEAKER / etc. already encoded in notes
                    if driver == "TREASURY_YIELDS" and state == "RISING":
                        direction = "BEARISH"
                    elif driver == "TREASURY_YIELDS" and state == "FALLING":
                        direction = "BULLISH"
                    elif driver == "USD" and state == "STRONGER":
                        direction = "BEARISH"
                    elif driver == "USD" and state == "WEAKER":
                        direction = "BULLISH"
                    elif driver == "FED_POLICY" and state == "HAWKISH_EVIDENCE":
                        direction = "BEARISH"
                    elif (
                        (driver == "FED_POLICY" and state == "DOVISH_EVIDENCE")
                        or (driver == "INFLATION" and state == "RISING")
                    ):
                        direction = "BULLISH"
                    elif driver == "INFLATION" and state == "FALLING":
                        direction = "BEARISH"
                    elif driver == "EMPLOYMENT" and state in {
                        "UNEMPLOYMENT_RISING",
                        "PAYROLLS_FALLING",
                    }:
                        direction = "BULLISH"
                    elif driver == "EMPLOYMENT" and state in {
                        "UNEMPLOYMENT_FALLING",
                        "PAYROLLS_RISING",
                    }:
                        direction = "BEARISH"
            urls = [s.url for s in sources if (s.topic or "") and needle[:3] in (s.topic or "")]
            if not urls:
                urls = [s.url for s in sources[:2]]
            drivers.append(
                ProviderDriverDraft(
                    driver=driver,
                    direction_for_gold=direction,
                    summary=note[:400],
                    evidence_strength="MODERATE" if ok_providers else "WEAK",
                    source_urls=urls,
                )
            )

        events: list[ProviderEventDraft] = []
        for item in news_items[:5]:
            url = normalize_url(item.canonical_url or "")
            events.append(
                ProviderEventDraft(
                    event_name=item.title[:200],
                    event_type="CENTRAL_BANK"
                    if item.provider == "federal_reserve"
                    else "OTHER",
                    importance="MEDIUM",
                    status="OBSERVED",
                    direction_known=False,
                    scheduled_at=item.published_at,
                    note=item.category,
                    source_urls=[url] if url else [],
                )
            )

        supporting: list[str] = [
            n for n in macro_ctx.notes if "support" in n.lower()
        ][:5]
        conflicting: list[str] = [
            n for n in macro_ctx.notes if "headwind" in n.lower()
        ][:5]
        unknowns: list[str] = []
        if hard_fail:
            unknowns.append(f"providers_failed={','.join(hard_fail)}")
        if soft_fail:
            unknowns.append(f"providers_inactive={','.join(soft_fail)}")
        if not sources:
            unknowns.append("no_canonical_sources")

        if not ok_providers:
            return ProviderGroundedResult(
                provider=self.name,
                model=self.model,
                ok=False,
                status_hint="INSUFFICIENT_EVIDENCE",
                external_bias="INSUFFICIENT_EVIDENCE",
                evidence_strength="INSUFFICIENT",
                event_risk=news_ctx.event_risk,
                claims=[],
                drivers=[],
                events=[],
                sources=[],
                supporting_factors=[],
                conflicting_factors=[],
                unknowns=unknowns or ["all_free_providers_unavailable"],
                search_queries=[],
                error="all_free_providers_unavailable",
                latency_ms=latency_ms,
                raw_text=None,
            )

        evidence = "MODERATE" if len(ok_providers) >= 2 else "WEAK"
        status_hint = "PARTIAL" if hard_fail else "AVAILABLE"

        # Embed dimensions in raw_text as compact JSON-ish note for diagnostics
        dims = macro_context_to_dict(macro_ctx)
        dims["ok_providers"] = ok_providers
        dims["cache_hits"] = cache_hits
        dims["request_symbol"] = request.symbol

        return ProviderGroundedResult(
            provider=self.name,
            model=self.model,
            ok=True,
            status_hint=status_hint,
            external_bias=bias,
            evidence_strength=evidence,
            event_risk=news_ctx.event_risk,
            claims=claims,
            drivers=drivers,
            events=events,
            sources=sources,
            supporting_factors=supporting,
            conflicting_factors=conflicting,
            unknowns=unknowns,
            search_queries=[],  # free sources — no Google search queries
            error=None,
            latency_ms=latency_ms,
            raw_text=str(dims),
        )

    def fetch_context(
        self, request: ExternalIntelligenceRequest
    ) -> ProviderGroundedResult:
        now = datetime.now(tz=UTC)
        try:
            now = datetime.fromisoformat(request.utc_now_iso.replace("Z", "+00:00"))
            if now.tzinfo is None:
                now = now.replace(tzinfo=UTC)
        except ValueError:
            now = datetime.now(tz=UTC)

        t0 = time.perf_counter()
        collected = self.collect(now=now, force_refresh=False)
        results: dict[str, ExternalDataProviderResult] = collected["results"]
        cache_hits: dict[str, bool] = collected["cache_hits"]
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return self._to_grounded(
            results=results,
            cache_hits=cache_hits,
            request=request,
            latency_ms=latency_ms,
        )
