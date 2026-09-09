"""CLI: python -m exness_bot.market_analysis.external_context <command>."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.external_context.providers.composite import (
    FreeSourcesCompositeProvider,
)
from exness_bot.market_analysis.external_context.service import ExternalContextService


def _build_service(
    settings: Settings, *, force_free: bool = False
) -> ExternalContextService:
    if force_free:
        object.__setattr__(settings, "external_intelligence_provider", "free_sources")
        object.__setattr__(settings, "free_external_sources_enabled", True)
        object.__setattr__(settings, "google_grounding_enabled", False)
    from exness_bot.data.factory import create_trading_data_provider

    provider_data = create_trading_data_provider(settings)
    return ExternalContextService(settings, data_source=provider_data)


def cmd_default(args: argparse.Namespace) -> int:
    settings = Settings()
    if args.provider:
        object.__setattr__(settings, "external_intelligence_provider", args.provider)
        if args.provider == "fake":
            object.__setattr__(settings, "external_intelligence_enabled", True)
    service = _build_service(settings)
    result = service.get_context(
        args.symbol, force_refresh=args.refresh, compact=args.compact
    )
    print(json.dumps(result, indent=2, default=str))
    status = result.get("status")
    print(f"\nstatus={status} promotion_impact=NONE", file=sys.stderr)
    return 0


def cmd_providers(_args: argparse.Namespace) -> int:
    settings = Settings()
    object.__setattr__(settings, "external_intelligence_provider", "free_sources")
    service = _build_service(settings, force_free=True)
    fs = service.free_sources_provider()
    now = datetime.now(tz=UTC)
    rows: list[dict[str, Any]]
    if isinstance(fs, FreeSourcesCompositeProvider):
        rows = fs.provider_health(now=now)
    else:
        rows = [{"provider": "unknown", "detail": "free_sources not active"}]
    # Never print secrets
    for row in rows:
        row.pop("api_key", None)
    print(json.dumps({"providers": rows, "generated_at": now.isoformat()}, indent=2))
    return 0


def cmd_smoke_free(args: argparse.Namespace) -> int:
    """Real free-source smoke — NO Gemini, NO Google Grounding."""
    settings = Settings()
    object.__setattr__(settings, "external_intelligence_enabled", True)
    object.__setattr__(settings, "external_intelligence_provider", "free_sources")
    object.__setattr__(settings, "free_external_sources_enabled", True)
    object.__setattr__(settings, "google_grounding_enabled", False)
    # Ensure Gemini not required
    object.__setattr__(settings, "gemini_api_key", "")

    service = _build_service(settings, force_free=True)
    fs = service.free_sources_provider()
    now = datetime.now(tz=UTC)

    # Force live fetch once for smoke
    health_before = fs.provider_health(now=now) if fs else []
    collected = fs.collect(now=now, force_refresh=True) if fs else {}
    results = collected.get("results") or {}
    provider_smoke: list[dict[str, Any]] = []
    for name, res in results.items():
        provider_smoke.append(
            {
                "provider": name,
                "status": res.status,
                "http_ok": res.status == "OK",
                "item_count": len(res.items),
                "error_category": res.error_category,
                "latency_ms": res.latency_ms,
                "freshness_sample": [
                    {
                        "title": i.title[:80],
                        "freshness": i.freshness,
                        "published_at": i.published_at,
                    }
                    for i in res.items[:3]
                ],
            }
        )

    # Second collect should hit provider TTL cache
    collected2 = fs.collect(now=now, force_refresh=False) if fs else {}
    cache_hits = collected2.get("cache_hits") or {}

    ctx = service.get_context(
        args.symbol,
        force_refresh=True,
        compact=args.compact,
        bypass_enabled_gate=True,
    )

    provenance = [
        {
            "source_id": s.get("source_id"),
            "title": s.get("title"),
            "url": s.get("url"),
            "domain": s.get("domain"),
            "published_at": s.get("published_at"),
            "retrieved_at": s.get("retrieved_at"),
            "freshness": s.get("freshness"),
            "grounding_provider": s.get("grounding_provider"),
        }
        for s in (ctx.get("sources") or [])[:20]
    ]
    if args.compact:
        provenance = ctx.get("source_summaries") or []

    ext_ctx: dict[str, Any] = {
        "status": ctx.get("status"),
        "external_bias": ctx.get("external_bias"),
        "alignment_with_technical": ctx.get("alignment_with_technical"),
        "event_risk": ctx.get("event_risk"),
        "evidence_strength": ctx.get("evidence_strength"),
        "source_count": len(ctx.get("sources") or ctx.get("source_summaries") or []),
        "freshness": ctx.get("freshness"),
        "provider_chips": ctx.get("provider_chips"),
        "provider": ctx.get("provider"),
    }
    out: dict[str, Any] = {
        "phase": "16.3.7",
        "command": "smoke-free",
        "gemini_required": False,
        "google_grounding_required": False,
        "gemini_api_key_present": False,
        "provider_smoke": provider_smoke,
        "provider_cache_hits_on_second_collect": cache_hits,
        "health_before_fetch": health_before,
        "external_context": ext_ctx,
        "provenance": provenance,
        "broker_mutation": False,
        "execution_mutations": 0,
    }
    print(json.dumps(out, indent=2, default=str))
    ok_any = any(p.get("http_ok") for p in provider_smoke)
    source_count = int(ext_ctx["source_count"] or 0)
    print(
        f"\nsmoke-free ok_any_provider={ok_any} sources={source_count}",
        file=sys.stderr,
    )
    return 0 if ok_any else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 16.3.2 / 16.3.7 ExternalMarketContext (read-only)"
    )
    sub = parser.add_subparsers(dest="command")

    p_prov = sub.add_parser("providers", help="Show free provider health (no secrets)")
    p_prov.set_defaults(func=cmd_providers)

    p_smoke = sub.add_parser(
        "smoke-free", help="Real free-source smoke (no Gemini / no Grounding)"
    )
    p_smoke.add_argument("--symbol", default="XAUUSD")
    p_smoke.add_argument("--compact", action="store_true")
    p_smoke.set_defaults(func=cmd_smoke_free)

    # Legacy flat args (no subcommand)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--provider",
        default=None,
        help="Override provider: free_sources|gemini_google|fake",
    )

    args = parser.parse_args(argv)
    if getattr(args, "command", None):
        return int(args.func(args))
    return cmd_default(args)


if __name__ == "__main__":
    raise SystemExit(main())
