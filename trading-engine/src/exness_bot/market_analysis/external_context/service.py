"""ExternalContextService — orchestrates snapshot → plan → provider → cache."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.external_context.cache import ExternalContextCache
from exness_bot.market_analysis.external_context.fake_provider import (
    FakeExternalIntelligenceProvider,
)
from exness_bot.market_analysis.external_context.fingerprint import (
    technical_fingerprint,
)
from exness_bot.market_analysis.external_context.gemini_provider import (
    GeminiGoogleGroundedProvider,
)
from exness_bot.market_analysis.external_context.models import (
    SCHEMA_VERSION,
    CacheMeta,
    ContextStatus,
)
from exness_bot.market_analysis.external_context.normalizer import (
    disabled_context,
    normalize_provider_result,
)
from exness_bot.market_analysis.external_context.planner import plan_search
from exness_bot.market_analysis.external_context.provider_base import (
    ExternalIntelligenceProvider,
    ExternalIntelligenceRequest,
)
from exness_bot.market_analysis.external_context.providers.bls import BlsProvider
from exness_bot.market_analysis.external_context.providers.composite import (
    FreeSourcesCompositeProvider,
)
from exness_bot.market_analysis.external_context.providers.federal_reserve import (
    FederalReserveProvider,
)
from exness_bot.market_analysis.external_context.providers.fred import FredProvider
from exness_bot.market_analysis.external_context.providers.rss import RssProvider
from exness_bot.market_analysis.technical_snapshot import TechnicalSnapshotBuilder

logger = structlog.get_logger(__name__)

SnapshotLoader = Callable[[str], dict[str, Any]]


def default_external_data_root() -> Path:
    cwd = Path.cwd()
    candidate = cwd / "data" / "external_context"
    if (cwd / "data").exists() or candidate.parent.exists():
        return candidate
    engine_root = Path(__file__).resolve().parents[4]
    return engine_root / "data" / "external_context"


class ExternalContextService:
    def __init__(
        self,
        settings: Settings,
        *,
        snapshot_loader: SnapshotLoader | None = None,
        data_source: Any | None = None,
        provider: ExternalIntelligenceProvider | None = None,
        cache: ExternalContextCache | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._data_source = data_source
        self._snapshot_loader = snapshot_loader
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._cache = cache or ExternalContextCache(
            root=default_external_data_root(),
            ttl_seconds=int(
                getattr(settings, "external_intelligence_cache_ttl_seconds", 600)
            ),
        )
        self._provider = provider or self._build_default_provider()

    def _build_free_sources_provider(self) -> FreeSourcesCompositeProvider:
        s = self._settings
        return FreeSourcesCompositeProvider(
            bls=BlsProvider(
                enabled=bool(getattr(s, "bls_enabled", True)),
                api_key=str(getattr(s, "bls_api_key", "") or ""),
            ),
            fred=FredProvider(
                enabled=bool(getattr(s, "fred_enabled", False)),
                api_key=str(getattr(s, "fred_api_key", "") or ""),
            ),
            federal_reserve=FederalReserveProvider(
                enabled=bool(getattr(s, "federal_reserve_enabled", True)),
            ),
            rss=RssProvider(
                enabled=bool(getattr(s, "external_rss_enabled", True)),
            ),
        )

    def _build_default_provider(self) -> ExternalIntelligenceProvider:
        name = str(
            getattr(self._settings, "external_intelligence_provider", "free_sources")
        ).lower()
        if name == "fake":
            return FakeExternalIntelligenceProvider()
        if name in {"free_sources", "free"}:
            return self._build_free_sources_provider()
        if name == "gemini_google":
            model = str(
                getattr(
                    self._settings,
                    "external_intelligence_model",
                    "gemini-2.5-flash",
                )
            )
            key = str(getattr(self._settings, "gemini_api_key", "") or "")
            return GeminiGoogleGroundedProvider(api_key=key, model=model)
        # Unknown provider name — prefer free sources over Gemini
        if bool(getattr(self._settings, "free_external_sources_enabled", True)):
            return self._build_free_sources_provider()
        return FakeExternalIntelligenceProvider()

    def free_sources_provider(self) -> FreeSourcesCompositeProvider | None:
        if isinstance(self._provider, FreeSourcesCompositeProvider):
            return self._provider
        return None

    def _intelligence_enabled(self) -> bool:
        return bool(getattr(self._settings, "external_intelligence_enabled", False))

    def _load_compact_snapshot(self, symbol: str) -> dict[str, Any]:
        if self._snapshot_loader is not None:
            return self._snapshot_loader(symbol)
        if self._data_source is None:
            raise RuntimeError("No snapshot_loader or data_source configured")
        snap = TechnicalSnapshotBuilder(self._settings, self._data_source).build(symbol)
        return snap.to_compact_context()

    def get_context(
        self,
        symbol: str | None = None,
        *,
        force_refresh: bool = False,
        compact: bool = False,
        bypass_enabled_gate: bool = False,
    ) -> dict[str, Any]:
        canonical = (symbol or self._settings.symbol).strip().upper() or "XAUUSD"
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        enabled = self._intelligence_enabled() or bypass_enabled_gate
        if not enabled:
            ctx = disabled_context(
                symbol=canonical,
                reason="EXTERNAL_INTELLIGENCE_ENABLED=false",
                now=now,
            )
            return ctx.to_compact_context() if compact else ctx.to_dict()

        try:
            snapshot = self._load_compact_snapshot(canonical)
        except Exception as exc:
            logger.warning(
                "external_context_snapshot_unavailable",
                error=type(exc).__name__,
                symbol=canonical,
            )
            ctx = disabled_context(
                symbol=canonical,
                reason="technical_snapshot_unavailable",
                now=now,
            )
            ctx.status = ContextStatus.UNAVAILABLE.value
            return ctx.to_compact_context() if compact else ctx.to_dict()

        fingerprint = technical_fingerprint(
            symbol=canonical,
            schema_version=str(snapshot.get("schema_version") or SCHEMA_VERSION),
            snapshot=snapshot,
        )
        provider_name = getattr(self._provider, "name", "unknown")
        if provider_name == "free_sources":
            model = str(getattr(self._provider, "model", "free_sources_v1"))
        else:
            model = str(
                getattr(
                    self._settings,
                    "external_intelligence_model",
                    getattr(self._provider, "model", None) or "unknown",
                )
            )

        if not force_refresh:
            cached, age, expires = self._cache.get(
                symbol=canonical,
                provider=provider_name,
                model=model,
                fingerprint=fingerprint,
                now=now,
            )
            if cached is not None:
                out = dict(cached)
                out["cache"] = CacheMeta(
                    hit=True,
                    age_seconds=None if age is None else round(age, 3),
                    expires_at=expires,
                    fingerprint=fingerprint,
                ).to_dict()
                logger.info(
                    "external_context_cache_hit",
                    symbol=canonical,
                    age_seconds=age,
                )
                try:
                    from exness_bot.market_analysis.integration.metrics import (
                        get_integration_metrics,
                    )

                    get_integration_metrics().inc("external_cache_hits")
                except Exception:  # pragma: no cover
                    pass
                if compact:
                    return {
                        "symbol": out.get("symbol"),
                        "generated_at": out.get("generated_at"),
                        "status": out.get("status"),
                        "external_bias": out.get("external_bias"),
                        "evidence_strength": out.get("evidence_strength"),
                        "alignment_with_technical": out.get("alignment_with_technical"),
                        "event_risk": out.get("event_risk"),
                        "top_market_drivers": (out.get("market_drivers") or [])[:5],
                        "important_events": (out.get("important_events") or [])[:5],
                        "supporting_factors": (out.get("supporting_factors") or [])[:5],
                        "conflicting_factors": (out.get("conflicting_factors") or [])[:5],
                        "source_summaries": [
                            {
                                "source_id": s.get("source_id"),
                                "title": s.get("title"),
                                "domain": s.get("domain"),
                                "freshness": s.get("freshness"),
                            }
                            for s in (out.get("sources") or [])[:8]
                        ],
                        "freshness": out.get("freshness"),
                        "cache": out.get("cache"),
                        "provider_chips": out.get("provider_chips"),
                    }
                return out

        # API key gate for live Gemini grounding only
        if provider_name == "gemini_google" and not str(
            getattr(self._settings, "gemini_api_key", "") or ""
        ).strip():
            ctx = disabled_context(
                symbol=canonical,
                reason="GEMINI_API_KEY missing",
                fingerprint=fingerprint,
                now=now,
            )
            ctx.status = ContextStatus.DISABLED.value
            return ctx.to_compact_context() if compact else ctx.to_dict()

        if provider_name == "gemini_google" and not bool(
            getattr(self._settings, "google_grounding_enabled", False)
        ):
            ctx = disabled_context(
                symbol=canonical,
                reason="GOOGLE_GROUNDING_ENABLED=false",
                fingerprint=fingerprint,
                now=now,
            )
            return ctx.to_compact_context() if compact else ctx.to_dict()

        plan = plan_search(symbol=canonical, snapshot=snapshot, now=now)
        request = ExternalIntelligenceRequest(
            symbol=canonical,
            snapshot=snapshot,
            search_plan=plan,
            utc_now_iso=now.isoformat(),
            technical_fingerprint=fingerprint,
        )
        try:
            from exness_bot.market_analysis.integration.metrics import (
                get_integration_metrics,
            )

            get_integration_metrics().inc("external_cache_misses")
            get_integration_metrics().inc("external_provider_calls")
        except Exception:  # pragma: no cover
            pass
        result = self._provider.fetch_context(request)
        tech_ts = snapshot.get("generated_at")
        context = normalize_provider_result(
            result=result,
            symbol=canonical,
            snapshot=snapshot,
            search_plan=plan.to_dict(),
            technical_fingerprint=fingerprint,
            technical_snapshot_timestamp=str(tech_ts) if tech_ts else None,
            cache=CacheMeta(
                hit=False,
                age_seconds=0.0,
                expires_at=None,
                fingerprint=fingerprint,
            ),
            now=now,
        )
        payload = context.to_dict()
        # Optional provider chips for dashboard (no secrets)
        chips: list[str] = []
        for src in payload.get("sources") or []:
            domain = str(src.get("domain") or "").lower()
            if "bls.gov" in domain and "BLS" not in chips:
                chips.append("BLS")
            if "stlouisfed.org" in domain and "FRED" not in chips:
                chips.append("FRED")
            if "federalreserve.gov" in domain and "FED" not in chips:
                chips.append("FED")
            if (
                "treasury.gov" in domain
                and "RSS" not in chips
                and "FED" not in chips
                and "BLS" not in chips
            ):
                chips.append("RSS")
        if provider_name == "free_sources":
            # Always surface active free providers that contributed
            fs = self.free_sources_provider()
            if fs is not None:
                for row in fs.provider_health(now=now):
                    if row.get("status") == "OK" and row.get("item_count"):
                        label = {
                            "bls": "BLS",
                            "fred": "FRED",
                            "federal_reserve": "FED",
                            "rss": "RSS",
                        }.get(str(row.get("provider")), "")
                        if label and label not in chips:
                            chips.append(label)
        payload["provider_chips"] = chips
        entry = self._cache.put(
            symbol=canonical,
            provider=provider_name,
            model=model,
            fingerprint=fingerprint,
            payload=payload,
            now=now,
        )
        payload["cache"] = CacheMeta(
            hit=False,
            age_seconds=0.0,
            expires_at=entry.expires_at.isoformat(),
            fingerprint=fingerprint,
        ).to_dict()
        logger.info(
            "external_context_refreshed",
            symbol=canonical,
            status=payload.get("status"),
            source_count=len(payload.get("sources") or []),
            provider=provider_name,
        )
        if compact:
            compact_out = context.to_compact_context()
            compact_out["cache"] = payload["cache"]
            compact_out["provider_chips"] = chips
            return compact_out
        return payload
