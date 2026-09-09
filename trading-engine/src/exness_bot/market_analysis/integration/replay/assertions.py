"""Assertions for offline grounding replay results."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from exness_bot.market_analysis.external_context.models import CacheMeta
from exness_bot.market_analysis.external_context.normalizer import (
    normalize_provider_result,
)
from exness_bot.market_analysis.external_context.provider_base import (
    ProviderGroundedResult,
)
from exness_bot.market_analysis.integration.replay.models import ReplayCaseResult


def assert_fixture_expectations(
    *,
    fixture_id: str,
    expected: dict[str, Any],
    provider_result: ProviderGroundedResult,
    snapshot: dict[str, Any],
    technical_fingerprint: str,
    now: datetime | None = None,
) -> ReplayCaseResult:
    now = now or datetime(2026, 9, 9, 8, 40, tzinfo=UTC)
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def _check(name: str, cond: bool, msg: str = "") -> None:
        checks[name] = cond
        if not cond:
            errors.append(msg or name)

    if "ok" in expected:
        _check("ok", provider_result.ok is bool(expected["ok"]), "ok mismatch")
    if "status_hint" in expected:
        _check(
            "status_hint",
            provider_result.status_hint == expected["status_hint"],
            f"status_hint={provider_result.status_hint}",
        )
    if "error" in expected:
        _check(
            "error",
            (provider_result.error or "") == expected["error"],
            f"error={provider_result.error}",
        )
    if "min_sources" in expected:
        _check(
            "min_sources",
            len(provider_result.sources) >= int(expected["min_sources"]),
            f"sources={len(provider_result.sources)}",
        )
    if "exact_source_count" in expected:
        _check(
            "exact_source_count",
            len(provider_result.sources) == int(expected["exact_source_count"]),
            f"sources={len(provider_result.sources)}",
        )
    if expected.get("has_search_queries"):
        _check(
            "search_queries",
            len(provider_result.search_queries) > 0,
            "missing search queries",
        )
    if "external_bias" in expected:
        _check(
            "external_bias",
            provider_result.external_bias == expected["external_bias"],
            f"bias={provider_result.external_bias}",
        )

    # Normalize through production path
    ctx = normalize_provider_result(
        result=provider_result,
        symbol=str(snapshot.get("symbol") or "XAUUSD"),
        snapshot=snapshot,
        search_plan={"topics": []},
        technical_fingerprint=technical_fingerprint,
        technical_snapshot_timestamp=str(snapshot.get("generated_at") or ""),
        cache=CacheMeta(
            hit=False,
            age_seconds=0.0,
            expires_at=None,
            fingerprint=technical_fingerprint,
        ),
        now=now,
    )
    payload = ctx.to_dict()
    sources = list(payload.get("sources") or [])
    source_ids = {str(s.get("source_id")) for s in sources if isinstance(s, dict)}

    if expected.get("published_at_null"):
        for s in sources:
            if isinstance(s, dict):
                _check(
                    "published_at_null",
                    s.get("published_at") is None,
                    "published_at fabricated",
                )
                if expected.get("freshness"):
                    _check(
                        "freshness_undated",
                        s.get("freshness") == expected["freshness"],
                        f"freshness={s.get('freshness')}",
                    )
                break

    if "exact_source_count_after_normalize" in expected:
        _check(
            "normalized_source_count",
            len(sources) == int(expected["exact_source_count_after_normalize"]),
            f"normalized_sources={len(sources)}",
        )

    if expected.get("unsafe_rejected"):
        for s in sources:
            if isinstance(s, dict):
                url = str(s.get("url") or "")
                _check(
                    "no_unsafe_scheme",
                    not url.startswith(("javascript:", "file:", "data:")),
                    f"unsafe url leaked: {url}",
                )

    if expected.get("preserve_redirect_url"):
        urls = [str(s.get("url")) for s in sources if isinstance(s, dict)]
        _check(
            "redirect_preserved",
            any("grounding-api-redirect" in u for u in urls),
            "redirect URL not preserved",
        )

    # Claim refs must resolve
    orphan = False
    for claim in payload.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        for sid in claim.get("source_ids") or []:
            if str(sid) not in source_ids:
                orphan = True
    _check("claim_refs_valid", not orphan, "orphan claim source_ids")

    if "alignment_with_case_a" in expected:
        _check(
            "alignment",
            payload.get("alignment_with_technical") == expected["alignment_with_case_a"],
            f"alignment={payload.get('alignment_with_technical')}",
        )

    passed = all(checks.values()) if checks else True
    return ReplayCaseResult(
        fixture_id=fixture_id,
        passed=passed,
        checks=checks,
        errors=errors,
        source_count=len(sources),
        status_hint=provider_result.status_hint,
    )
