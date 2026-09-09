"""MarketSynthesisService — hybrid deterministic + optional AI narrative."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.synthesis.cache import SynthesisCache
from exness_bot.market_analysis.synthesis.compact import build_prompt_payload
from exness_bot.market_analysis.synthesis.fake_provider import (
    FakeMarketSynthesisProvider,
)
from exness_bot.market_analysis.synthesis.fingerprint import (
    external_fingerprint,
    synthesis_fingerprint,
    tech_fp_from_snapshot,
)
from exness_bot.market_analysis.synthesis.gemini_provider import (
    GeminiMarketSynthesisProvider,
)
from exness_bot.market_analysis.synthesis.models import (
    RULE_VERSION,
    SCHEMA_VERSION,
    AiMetadata,
    CacheMeta,
    MarketSynthesis,
    SynthesisState,
    SynthesisStatus,
)
from exness_bot.market_analysis.synthesis.provider_base import (
    MarketSynthesisPromptInput,
    MarketSynthesisProvider,
)
from exness_bot.market_analysis.synthesis.rules import (
    build_deterministic_narrative,
    build_external_view,
    build_facts,
    build_technical_view,
    extract_sources,
    resolve_synthesis_state,
    resolve_synthesis_status,
)
from exness_bot.market_analysis.synthesis.validator import validate_narrative

logger = structlog.get_logger(__name__)

SnapshotLoader = Callable[[str], dict[str, Any]]
ExternalLoader = Callable[[str], dict[str, Any]]


def default_synthesis_data_root() -> Path:
    cwd = Path.cwd()
    candidate = cwd / "data" / "market_synthesis"
    if (cwd / "data").exists() or candidate.parent.exists():
        return candidate
    engine_root = Path(__file__).resolve().parents[4]
    return engine_root / "data" / "market_synthesis"


class MarketSynthesisService:
    def __init__(
        self,
        settings: Settings,
        *,
        snapshot_loader: SnapshotLoader | None = None,
        external_loader: ExternalLoader | None = None,
        data_source: Any | None = None,
        provider: MarketSynthesisProvider | None = None,
        cache: SynthesisCache | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._data_source = data_source
        self._snapshot_loader = snapshot_loader
        self._external_loader = external_loader
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._cache = cache or SynthesisCache(
            root=default_synthesis_data_root(),
            ttl_seconds=int(
                getattr(settings, "ai_market_synthesis_cache_ttl_seconds", 600)
            ),
        )
        self._provider = provider or self._build_default_provider()

    def _build_default_provider(self) -> MarketSynthesisProvider:
        name = str(
            getattr(self._settings, "ai_market_synthesis_provider", "gemini")
        ).lower()
        model = str(
            getattr(
                self._settings,
                "ai_market_synthesis_model",
                "gemini-2.5-flash",
            )
        )
        if name == "fake":
            return FakeMarketSynthesisProvider(model=model)
        key = str(getattr(self._settings, "gemini_api_key", "") or "")
        timeout = float(
            getattr(self._settings, "ai_market_synthesis_timeout_seconds", 30)
        )
        return GeminiMarketSynthesisProvider(
            api_key=key, model=model, timeout_seconds=timeout
        )

    def _load_snapshot(self, symbol: str) -> dict[str, Any]:
        if self._snapshot_loader is not None:
            return self._snapshot_loader(symbol)
        if self._data_source is None:
            raise RuntimeError("No snapshot_loader or data_source")
        from exness_bot.market_analysis.technical_snapshot import (
            TechnicalSnapshotBuilder,
        )

        snap = TechnicalSnapshotBuilder(self._settings, self._data_source).build(
            symbol
        )
        return snap.to_compact_context()

    def _load_external(self, symbol: str) -> dict[str, Any]:
        if self._external_loader is not None:
            return self._external_loader(symbol)
        from exness_bot.market_analysis.external_context import ExternalContextService

        return ExternalContextService(
            self._settings, data_source=self._data_source
        ).get_context(symbol, force_refresh=False, compact=False)

    def get_synthesis(
        self,
        symbol: str | None = None,
        *,
        force_refresh: bool = False,
        compact: bool = False,
    ) -> dict[str, Any]:
        canonical = (symbol or self._settings.symbol).strip().upper() or "XAUUSD"
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        ai_enabled = bool(
            getattr(self._settings, "ai_market_synthesis_enabled", False)
        )
        provider_name = getattr(self._provider, "name", "unknown")
        model = str(
            getattr(
                self._settings,
                "ai_market_synthesis_model",
                getattr(self._provider, "model", None) or "unknown",
            )
        )

        try:
            snapshot = self._load_snapshot(canonical)
            technical_ok = True
        except Exception as exc:
            logger.warning(
                "market_synthesis_snapshot_unavailable",
                error=type(exc).__name__,
                symbol=canonical,
            )
            snapshot = {}
            technical_ok = False

        try:
            external = self._load_external(canonical)
        except Exception as exc:
            logger.warning(
                "market_synthesis_external_unavailable",
                error=type(exc).__name__,
                symbol=canonical,
            )
            external = {
                "status": "UNAVAILABLE",
                "external_bias": "INSUFFICIENT_EVIDENCE",
                "evidence_strength": "INSUFFICIENT",
                "alignment_with_technical": "INSUFFICIENT_DATA",
                "event_risk": "UNKNOWN",
                "sources": [],
                "claims": [],
                "supporting_factors": [],
                "conflicting_factors": [],
                "market_drivers": [],
                "important_events": [],
                "freshness": "UNDATED",
            }

        if not technical_ok and str(external.get("status") or "").upper() in {
            "DISABLED",
            "UNAVAILABLE",
            "",
        }:
            result = MarketSynthesis(
                schema_version=SCHEMA_VERSION,
                symbol=canonical,
                generated_at=now.isoformat(),
                status=SynthesisStatus.UNAVAILABLE.value,
                technical_snapshot_timestamp=None,
                external_context_timestamp=external.get("generated_at"),
                technical_fingerprint=None,
                external_fingerprint=external_fingerprint(external),
                synthesis_fingerprint=None,
                rule_version=RULE_VERSION,
                technical_view={},
                external_view=build_external_view(external),
                synthesis_state="INSUFFICIENT_CONTEXT",
                narrative=build_deterministic_narrative(
                    symbol=canonical,
                    technical_view={"primary_bias": "UNKNOWN", "bot_signal": "WAIT"},
                    external_view=build_external_view(external),
                    state=SynthesisState.INSUFFICIENT_CONTEXT,
                ),
                facts=[],
                sources=extract_sources(external),
                freshness={"technical": "UNAVAILABLE", "external": external.get("status")},
                data_quality={"technical_ok": False},
                ai_metadata=AiMetadata(
                    enabled=ai_enabled,
                    provider=provider_name,
                    model=model,
                    used=False,
                    fallback_used=True,
                ),
                cache=CacheMeta(hit=False, age_seconds=None, expires_at=None),
            )
            return result.to_compact_context() if compact else result.to_dict()

        tech_fp = (
            tech_fp_from_snapshot(canonical, snapshot) if technical_ok else "none"
        )
        ext_fp = external_fingerprint(external)
        syn_fp = synthesis_fingerprint(
            technical_fp=tech_fp,
            external_fp=ext_fp,
            provider=provider_name if ai_enabled else "deterministic",
            model=model if ai_enabled else "none",
        )

        if not force_refresh:
            cached, age, expires = self._cache.get(
                symbol=canonical,
                provider=provider_name if ai_enabled else "deterministic",
                model=model if ai_enabled else "none",
                fingerprint=syn_fp,
                now=now,
            )
            if cached is not None:
                out = dict(cached)
                out["cache"] = CacheMeta(
                    hit=True,
                    age_seconds=None if age is None else round(age, 3),
                    expires_at=expires,
                    fingerprint=syn_fp,
                ).to_dict()
                logger.info("market_synthesis_cache_hit", symbol=canonical)
                if compact:
                    # Rebuild compact from full payload fields
                    syn = out.get("synthesis") or {}
                    return {
                        "symbol": out.get("symbol"),
                        "generated_at": out.get("generated_at"),
                        "status": out.get("status"),
                        "synthesis_state": syn.get("state"),
                        "technical_primary_bias": (out.get("technical_view") or {}).get(
                            "primary_bias"
                        ),
                        "bot_signal": (out.get("technical_view") or {}).get(
                            "bot_signal"
                        ),
                        "mtf_alignment": (out.get("technical_view") or {}).get(
                            "mtf_alignment"
                        ),
                        "external_bias": (out.get("external_view") or {}).get(
                            "external_bias"
                        ),
                        "external_alignment": (out.get("external_view") or {}).get(
                            "alignment_with_technical"
                        ),
                        "event_risk": (out.get("external_view") or {}).get(
                            "event_risk"
                        ),
                        "top_supporting_factors": (
                            out.get("external_view") or {}
                        ).get("supporting_factors")
                        or [],
                        "top_conflicting_factors": (
                            out.get("external_view") or {}
                        ).get("conflicting_factors")
                        or [],
                        "uncertainties": syn.get("uncertainties") or [],
                        "what_to_watch": syn.get("what_to_watch") or [],
                        "summary": syn.get("summary"),
                        "source_refs": [
                            {
                                "source_id": s.get("source_id"),
                                "title": s.get("title"),
                                "domain": s.get("domain"),
                            }
                            for s in (out.get("sources") or [])[:8]
                            if isinstance(s, dict)
                        ],
                        "ai_metadata": out.get("ai_metadata"),
                        "cache": out.get("cache"),
                    }
                return out

        technical_view = build_technical_view(snapshot) if technical_ok else {}
        external_view = build_external_view(external)
        freshness_block = snapshot.get("freshness") or {}
        technical_stale = (
            isinstance(freshness_block, dict)
            and str(freshness_block.get("status") or "").upper() == "STALE"
        ) or (
            isinstance(freshness_block, str)
            and freshness_block.upper() == "STALE"
        )
        status = resolve_synthesis_status(
            technical_ok=technical_ok,
            technical_stale=technical_stale,
            external=external,
        )
        state = resolve_synthesis_state(
            technical_view=technical_view or {"primary_bias": "UNKNOWN"},
            external_view=external_view,
        )
        fallback = build_deterministic_narrative(
            symbol=canonical,
            technical_view=technical_view or {"primary_bias": "UNKNOWN"},
            external_view=external_view,
            state=state,
        )
        sources = extract_sources(external)
        facts = build_facts(
            technical_view=technical_view or {},
            external_view=external_view,
            state=state,
        )

        ai_used = False
        fallback_used = True
        latency_ms: float | None = None
        error_type: str | None = None
        narrative = fallback

        if ai_enabled:
            allowed_ids = {s.source_id for s in sources}
            prompt_payload = build_prompt_payload(
                symbol=canonical,
                technical_view=technical_view or {},
                external_view=external_view,
                state=state,
                sources=[s.to_dict() for s in sources],
                claims=list(external.get("claims") or []),
            )
            request = MarketSynthesisPromptInput(
                symbol=canonical,
                payload=prompt_payload,
                utc_now_iso=now.isoformat(),
            )
            try:
                provider_result = self._provider.generate_explanation(request)
            except Exception as exc:
                provider_result = None
                error_type = type(exc).__name__
                logger.warning(
                    "market_synthesis_provider_crash",
                    error=error_type,
                    symbol=canonical,
                )

            if provider_result is not None:
                latency_ms = provider_result.latency_ms
                if provider_result.ok and provider_result.narrative is not None:
                    validated, verr = validate_narrative(
                        provider_result.narrative,
                        allowed_source_ids=allowed_ids,
                    )
                    if validated is not None:
                        narrative = validated
                        ai_used = True
                        fallback_used = False
                    else:
                        error_type = verr or "validation_failed"
                        fallback_used = True
                else:
                    error_type = provider_result.error_type or "provider_failed"
                    fallback_used = True

        result = MarketSynthesis(
            schema_version=SCHEMA_VERSION,
            symbol=canonical,
            generated_at=now.isoformat(),
            status=status,
            technical_snapshot_timestamp=snapshot.get("generated_at"),
            external_context_timestamp=external.get("generated_at"),
            technical_fingerprint=tech_fp,
            external_fingerprint=ext_fp,
            synthesis_fingerprint=syn_fp,
            rule_version=RULE_VERSION,
            technical_view=technical_view,
            external_view=external_view,
            synthesis_state=state.value,
            narrative=narrative,
            facts=facts,
            sources=sources,
            freshness={
                "technical": freshness_block
                if isinstance(freshness_block, (dict, str))
                else None,
                "external": external.get("freshness"),
            },
            data_quality={
                "technical_ok": technical_ok,
                "external_status": external.get("status"),
                "source_count": len(sources),
                "ai_used": ai_used,
                "fallback_used": fallback_used,
            },
            ai_metadata=AiMetadata(
                enabled=ai_enabled,
                provider=provider_name,
                model=model,
                used=ai_used,
                fallback_used=fallback_used,
                latency_ms=latency_ms,
                error_type=error_type,
            ),
            cache=CacheMeta(
                hit=False,
                age_seconds=0.0,
                expires_at=None,
                fingerprint=syn_fp,
            ),
        )
        payload = result.to_dict()
        entry = self._cache.put(
            symbol=canonical,
            provider=provider_name if ai_enabled else "deterministic",
            model=model if ai_enabled else "none",
            fingerprint=syn_fp,
            payload=payload,
            now=now,
        )
        payload["cache"] = CacheMeta(
            hit=False,
            age_seconds=0.0,
            expires_at=entry.expires_at.isoformat(),
            fingerprint=syn_fp,
        ).to_dict()
        logger.info(
            "market_synthesis_refreshed",
            symbol=canonical,
            status=status,
            state=state.value,
            ai_used=ai_used,
            fallback_used=fallback_used,
        )
        return result.to_compact_context() if compact else payload
