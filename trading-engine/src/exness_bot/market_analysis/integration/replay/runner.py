"""Offline replay runner — network-free, reuses production adapter+normalizer."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from exness_bot.market_analysis.external_context.fingerprint import (
    technical_fingerprint,
)
from exness_bot.market_analysis.external_context.gemini_adapter import (
    adapt_gemini_grounded_response,
    response_from_dict,
)
from exness_bot.market_analysis.integration.replay.assertions import (
    assert_fixture_expectations,
)
from exness_bot.market_analysis.integration.replay.loader import (
    default_fixture_root,
    fixture_set_hash,
    load_all_fixtures,
    load_fixture,
    load_technical_case,
)
from exness_bot.market_analysis.integration.replay.models import ReplayCaseResult


def _artifact_path() -> Path:
    cwd = Path.cwd()
    candidate = cwd / "data" / "integration"
    if (cwd / "data").exists() or candidate.parent.exists():
        root = candidate
    else:
        root = Path(__file__).resolve().parents[5] / "data" / "integration"
    root.mkdir(parents=True, exist_ok=True)
    return root / "phase_16_3_6A_replay_report.json"


def run_fixture(
    fixture_id_or_path: str,
    *,
    technical_case: str = "case_a_conflicting_wait.json",
) -> ReplayCaseResult:
    root = default_fixture_root()
    path = Path(fixture_id_or_path)
    if not path.exists():
        path = root / f"{fixture_id_or_path}.json"
        if not path.exists():
            path = root / fixture_id_or_path
    fx = load_fixture(path)
    snapshot = load_technical_case(technical_case)
    # strip case_id helper field if present
    snap = {k: v for k, v in snapshot.items() if k != "case_id"}
    fp = technical_fingerprint(
        symbol=str(snap.get("symbol") or "XAUUSD"),
        schema_version=str(snap.get("schema_version") or "1.0"),
        snapshot=snap,
    )
    response_obj = response_from_dict(fx.response)
    provider_result = adapt_gemini_grounded_response(
        response_obj,
        provider="gemini_google_replay",
        model="fixture",
        latency_ms=0.0,
    )
    return assert_fixture_expectations(
        fixture_id=fx.fixture_id,
        expected=fx.expected,
        provider_result=provider_result,
        snapshot=snap,
        technical_fingerprint=fp,
    )


def run_all_fixtures() -> dict[str, Any]:
    fixtures = load_all_fixtures()
    results: list[ReplayCaseResult] = []
    for fx in fixtures:
        results.append(run_fixture(fx.fixture_id))
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    report = {
        "run_id": str(uuid.uuid4()),
        "phase": "16.3.6A",
        "status": "PASS" if failed == 0 else "FAIL",
        "offline_replay": "PASS" if failed == 0 else "FAIL",
        "real_grounding": "NOT_RUN",
        "phase_16_3_6_status": "BLOCKED",
        "network_required": False,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "fixture_count": len(results),
        "fixture_set_hash": fixture_set_hash(fixtures),
        "passed": passed,
        "failed": failed,
        "results": [r.to_dict() for r in results],
        "note": (
            "Offline replay PASS does not upgrade Phase 16.3.6 from BLOCKED. "
            "Real Google Grounding remains NOT_RUN until GEMINI_API_KEY smoke."
        ),
    }
    path = _artifact_path()
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["artifact"] = str(path)
    return report
