"""Synthesis fingerprints — ignore quote micro-ticks."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from exness_bot.market_analysis.external_context.fingerprint import (
    technical_fingerprint,
)
from exness_bot.market_analysis.synthesis.models import RULE_VERSION, SCHEMA_VERSION


def external_fingerprint(external: dict[str, Any] | None) -> str:
    if not external:
        return "none"
    payload = {
        "status": external.get("status"),
        "generated_at": external.get("generated_at"),
        "technical_fingerprint": external.get("technical_fingerprint"),
        "external_bias": external.get("external_bias"),
        "evidence_strength": external.get("evidence_strength"),
        "alignment_with_technical": external.get("alignment_with_technical"),
        "event_risk": external.get("event_risk"),
        "source_count": len(external.get("sources") or []),
        "freshness": external.get("freshness"),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def synthesis_fingerprint(
    *,
    technical_fp: str,
    external_fp: str,
    provider: str,
    model: str,
    schema_version: str = SCHEMA_VERSION,
    rule_version: str = RULE_VERSION,
) -> str:
    payload = {
        "technical": technical_fp,
        "external": external_fp,
        "schema": schema_version,
        "rules": rule_version,
        "provider": provider,
        "model": model,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def tech_fp_from_snapshot(symbol: str, snapshot: dict[str, Any]) -> str:
    return technical_fingerprint(
        symbol=symbol,
        schema_version=str(snapshot.get("schema_version") or "1.0"),
        snapshot=snapshot,
    )
