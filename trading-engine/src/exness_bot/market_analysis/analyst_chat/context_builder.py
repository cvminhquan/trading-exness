"""Build authoritative MarketAnalystContext from canonical backend layers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.analyst_chat.models import (
    SCHEMA_VERSION,
    MarketAnalystContext,
    SourceRef,
)
from exness_bot.market_analysis.external_context.fingerprint import (
    technical_fingerprint,
)
from exness_bot.market_analysis.synthesis.fingerprint import (
    external_fingerprint,
    synthesis_fingerprint,
)

SnapshotLoader = Callable[[str], dict[str, Any]]
ExternalLoader = Callable[[str], dict[str, Any]]
SynthesisLoader = Callable[[str], dict[str, Any]]


def _compact_technical(snapshot: dict[str, Any]) -> dict[str, Any]:
    bot = snapshot.get("bot_analysis") or {}
    mtf = snapshot.get("mtf_summary") or {}
    tfs = snapshot.get("timeframes") or {}
    out_tfs: dict[str, Any] = {}
    for tf in ("M15", "H1", "H4", "D1"):
        block = tfs.get(tf) or {}
        out_tfs[tf] = {
            "role": block.get("role"),
            "trend": block.get("trend"),
            "structure": block.get("structure"),
            "last_closed_candle_timestamp": block.get(
                "last_closed_candle_timestamp"
            ),
            "nearest_support": block.get("nearest_support"),
            "nearest_resistance": block.get("nearest_resistance"),
            "wick": block.get("wick"),
            "indicators": block.get("indicators")
            if isinstance(block.get("indicators"), dict)
            else None,
        }
    return {
        "current_price": snapshot.get("current_price"),
        "generated_at": snapshot.get("generated_at"),
        "freshness": snapshot.get("freshness"),
        "bot_signal": bot.get("signal"),
        "bot_strategy": bot.get("production_strategy") or "mtf_technical_v1",
        "setup_state": bot.get("setup_state"),
        "execution_status": bot.get("execution_status"),
        "mtf_score": bot.get("mtf_score"),
        "mtf_alignment": mtf.get("alignment"),
        "primary_bias": mtf.get("primary_bias"),
        "timeframes": out_tfs,
    }


def _compact_external(external: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": external.get("status"),
        "external_bias": external.get("external_bias"),
        "evidence_strength": external.get("evidence_strength"),
        "alignment_with_technical": external.get("alignment_with_technical"),
        "event_risk": external.get("event_risk"),
        "supporting_factors": list(external.get("supporting_factors") or [])[:5],
        "conflicting_factors": list(external.get("conflicting_factors") or [])[:5],
        "market_drivers": list(
            external.get("market_drivers") or external.get("top_market_drivers") or []
        )[:5],
        "important_events": list(external.get("important_events") or [])[:5],
        "freshness": external.get("freshness"),
        "unknowns": list(external.get("unknowns") or [])[:5],
    }


def _compact_synthesis(synthesis: dict[str, Any]) -> dict[str, Any]:
    syn = synthesis.get("synthesis") or {}
    return {
        "status": synthesis.get("status"),
        "state": syn.get("state") or synthesis.get("synthesis_state"),
        "summary": syn.get("summary") or "",
        "technical_explanation": syn.get("technical_explanation") or "",
        "external_explanation": syn.get("external_explanation") or "",
        "alignment_explanation": syn.get("alignment_explanation") or "",
        "risk_explanation": syn.get("risk_explanation") or "",
        "uncertainties": list(syn.get("uncertainties") or [])[:6],
        "what_to_watch": list(syn.get("what_to_watch") or [])[:6],
        "ai_metadata": synthesis.get("ai_metadata") or {},
    }


def _extract_sources(external: dict[str, Any]) -> list[SourceRef]:
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
                freshness=s.get("freshness"),
            )
        )
    return out


class MarketAnalystContextBuilder:
    def __init__(
        self,
        settings: Settings,
        *,
        snapshot_loader: SnapshotLoader | None = None,
        external_loader: ExternalLoader | None = None,
        synthesis_loader: SynthesisLoader | None = None,
        data_source: Any | None = None,
    ) -> None:
        self._settings = settings
        self._snapshot_loader = snapshot_loader
        self._external_loader = external_loader
        self._synthesis_loader = synthesis_loader
        self._data_source = data_source

    def _load_snapshot(self, symbol: str) -> dict[str, Any]:
        if self._snapshot_loader is not None:
            return self._snapshot_loader(symbol)
        from exness_bot.market_analysis.technical_snapshot import (
            TechnicalSnapshotBuilder,
        )

        if self._data_source is None:
            raise RuntimeError("No snapshot_loader or data_source")
        return (
            TechnicalSnapshotBuilder(self._settings, self._data_source)
            .build(symbol)
            .to_compact_context()
        )

    def _load_external(self, symbol: str) -> dict[str, Any]:
        if self._external_loader is not None:
            return self._external_loader(symbol)
        from exness_bot.market_analysis.external_context import ExternalContextService

        return ExternalContextService(
            self._settings, data_source=self._data_source
        ).get_context(symbol, force_refresh=False, compact=False)

    def _load_synthesis(self, symbol: str) -> dict[str, Any]:
        if self._synthesis_loader is not None:
            return self._synthesis_loader(symbol)
        from exness_bot.market_analysis.synthesis import MarketSynthesisService

        return MarketSynthesisService(
            self._settings, data_source=self._data_source
        ).get_synthesis(symbol, force_refresh=False, compact=False)

    def build(self, symbol: str) -> MarketAnalystContext:
        canonical = symbol.strip().upper() or "XAUUSD"
        now = datetime.now(tz=UTC).isoformat()
        try:
            snapshot = self._load_snapshot(canonical)
            tech_ok = True
        except Exception:
            snapshot = {}
            tech_ok = False
        try:
            external = self._load_external(canonical)
        except Exception:
            external = {"status": "UNAVAILABLE", "sources": []}
        try:
            synthesis = self._load_synthesis(canonical)
        except Exception:
            synthesis = {"status": "UNAVAILABLE", "synthesis": {}}

        tech_fp = (
            technical_fingerprint(
                symbol=canonical,
                schema_version=str(snapshot.get("schema_version") or "1.0"),
                snapshot=snapshot,
            )
            if tech_ok
            else "none"
        )
        ext_fp = external_fingerprint(external)
        syn_fp = synthesis_fingerprint(
            technical_fp=tech_fp,
            external_fp=ext_fp,
            provider="analyst",
            model="context",
        )
        ext_status = str(external.get("status") or "UNAVAILABLE").upper()
        syn_status = str(synthesis.get("status") or "UNAVAILABLE").upper()
        if not tech_ok and ext_status in {"DISABLED", "UNAVAILABLE"}:
            context_status = "UNAVAILABLE"
        elif not tech_ok:
            context_status = "PARTIAL"
        elif ext_status in {"DISABLED", "UNAVAILABLE"}:
            context_status = "TECHNICAL_ONLY"
        elif syn_status in {"PARTIAL", "STALE"} or ext_status in {
            "PARTIAL",
            "STALE",
            "INSUFFICIENT_EVIDENCE",
        }:
            context_status = "PARTIAL"
        else:
            context_status = "AVAILABLE"

        return MarketAnalystContext(
            schema_version=SCHEMA_VERSION,
            symbol=canonical,
            generated_at=now,
            technical_fingerprint=tech_fp,
            external_fingerprint=ext_fp,
            synthesis_fingerprint=syn_fp,
            technical=_compact_technical(snapshot) if tech_ok else {},
            external=_compact_external(external),
            synthesis=_compact_synthesis(synthesis),
            sources=_extract_sources(external),
            freshness={
                "technical": snapshot.get("freshness"),
                "external": external.get("freshness"),
                "synthesis": (synthesis.get("freshness") or {}),
            },
            context_status=context_status,
        )
