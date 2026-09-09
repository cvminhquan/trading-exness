"""Unit tests for Phase 16.3.2 External Intelligence."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from exness_bot.api.app import create_app
from exness_bot.api.dependencies import get_read_service
from exness_bot.api.services.read_service import ReadService
from exness_bot.config.settings import Settings
from exness_bot.data.mock_provider import MockTradingDataProvider
from exness_bot.market_analysis.external_context.alignment import (
    align_external_with_technical,
)
from exness_bot.market_analysis.external_context.cache import ExternalContextCache
from exness_bot.market_analysis.external_context.fake_provider import (
    FakeExternalIntelligenceProvider,
)
from exness_bot.market_analysis.external_context.fingerprint import (
    technical_fingerprint,
)
from exness_bot.market_analysis.external_context.freshness import (
    classify_external_freshness,
)
from exness_bot.market_analysis.external_context.models import (
    AlignmentWithTechnical,
    ExternalBias,
    ExternalFreshness,
)
from exness_bot.market_analysis.external_context.planner import plan_search
from exness_bot.market_analysis.external_context.service import ExternalContextService
from exness_bot.market_analysis.external_context.sources import (
    classify_source_type,
    dedupe_urls,
    normalize_url,
)


def _snap(*, m15_trend: str = "BEARISH") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "symbol": "XAUUSD",
        "current_price": 4380.0,
        "generated_at": "2026-09-09T05:00:00+00:00",
        "freshness": {"status": "FRESH"},
        "timeframes": {
            "M15": {
                "role": "PRIMARY",
                "trend": m15_trend,
                "structure": m15_trend,
                "last_closed_candle_timestamp": "2026-09-09T05:00:00+00:00",
                "descriptive_impulse": {
                    "last_1_bar_move": {"atr_normalized_change": -1.2}
                },
                "wick": {"pattern": "NO_CLEAR_REJECTION"},
            },
            "H1": {
                "trend": "BEARISH",
                "last_closed_candle_timestamp": "2026-09-09T04:00:00+00:00",
            },
            "H4": {
                "trend": "BULLISH",
                "last_closed_candle_timestamp": "2026-09-09T00:00:00+00:00",
            },
            "D1": {
                "trend": "BULLISH",
                "last_closed_candle_timestamp": "2026-09-08T00:00:00+00:00",
            },
        },
        "mtf_summary": {"alignment": "MIXED", "primary_bias": m15_trend},
        "bot_analysis": {"signal": "WAIT"},
    }


def test_query_planner_bounded_topics() -> None:
    plan = plan_search(symbol="XAUUSD", snapshot=_snap())
    assert 1 <= len(plan.search_topics) <= 6
    topics = {t.topic for t in plan.search_topics}
    assert "GOLD_MARKET" in topics
    assert "USD" in topics


def test_alignment_matrix() -> None:
    assert (
        align_external_with_technical(
            external_bias=ExternalBias.BULLISH_FOR_GOLD,
            snapshot=_snap(m15_trend="BULLISH"),
        )
        == AlignmentWithTechnical.SUPPORT
    )
    assert (
        align_external_with_technical(
            external_bias=ExternalBias.BEARISH_FOR_GOLD,
            snapshot=_snap(m15_trend="BEARISH"),
        )
        == AlignmentWithTechnical.SUPPORT
    )
    assert (
        align_external_with_technical(
            external_bias=ExternalBias.BEARISH_FOR_GOLD,
            snapshot=_snap(m15_trend="BULLISH"),
        )
        == AlignmentWithTechnical.CONFLICT
    )
    assert (
        align_external_with_technical(
            external_bias=ExternalBias.BULLISH_FOR_GOLD,
            snapshot=_snap(m15_trend="BEARISH"),
        )
        == AlignmentWithTechnical.CONFLICT
    )
    assert (
        align_external_with_technical(
            external_bias=ExternalBias.INSUFFICIENT_EVIDENCE,
            snapshot=_snap(),
        )
        == AlignmentWithTechnical.INSUFFICIENT_DATA
    )


def test_technical_immutability_with_conflicting_external(tmp_path: Path) -> None:
    snap = _snap(m15_trend="BEARISH")
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: snap,
        provider=FakeExternalIntelligenceProvider(scenario="bullish"),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    ctx = service.get_context("XAUUSD", force_refresh=True)
    assert ctx["external_bias"] == "BULLISH_FOR_GOLD"
    assert ctx["alignment_with_technical"] == "CONFLICT"
    # Snapshot input unchanged
    assert snap["timeframes"]["M15"]["trend"] == "BEARISH"  # type: ignore[index]


def test_freshness_boundaries() -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    assert (
        classify_external_freshness(now - timedelta(hours=1), now=now)
        == ExternalFreshness.BREAKING
    )
    assert (
        classify_external_freshness(now - timedelta(hours=12), now=now)
        == ExternalFreshness.RECENT
    )
    assert (
        classify_external_freshness(now - timedelta(hours=48), now=now)
        == ExternalFreshness.CURRENT
    )
    assert (
        classify_external_freshness(now - timedelta(hours=100), now=now)
        == ExternalFreshness.STALE
    )
    assert classify_external_freshness(None, now=now) == ExternalFreshness.UNDATED


def test_url_safety_and_dedupe() -> None:
    assert normalize_url("javascript:alert(1)") is None
    assert normalize_url("file:///etc/passwd") is None
    ok = normalize_url("https://www.Reuters.com/path?utm_source=x&a=1")
    assert ok is not None
    assert "utm_source" not in ok
    assert dedupe_urls(
        [
            "https://example.com/a",
            "https://example.com/a",
            "https://example.com/b",
        ]
    ) == ["https://example.com/a", "https://example.com/b"]


def test_cache_hit_and_ttl(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
        EXTERNAL_INTELLIGENCE_MODEL="fake-model",
    )
    clock = {"t": datetime(2026, 9, 9, 12, 0, tzinfo=UTC)}

    def now() -> datetime:
        return clock["t"]

    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        provider=FakeExternalIntelligenceProvider(scenario="bearish"),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
        clock=now,
    )
    first = service.get_context("XAUUSD", force_refresh=True)
    assert first["cache"]["hit"] is False
    second = service.get_context("XAUUSD", force_refresh=False)
    assert second["cache"]["hit"] is True
    # Quote tick alone shouldn't matter — same fingerprint
    clock["t"] = clock["t"] + timedelta(seconds=30)
    third = service.get_context("XAUUSD", force_refresh=False)
    assert third["cache"]["hit"] is True
    # Expire
    clock["t"] = clock["t"] + timedelta(seconds=700)
    fourth = service.get_context("XAUUSD", force_refresh=False)
    assert fourth["cache"]["hit"] is False


def test_fingerprint_ignores_price_tick() -> None:
    a = _snap()
    b = dict(a)
    b["current_price"] = 9999.0
    fa = technical_fingerprint(symbol="XAUUSD", schema_version="1.0", snapshot=a)
    fb = technical_fingerprint(symbol="XAUUSD", schema_version="1.0", snapshot=b)
    assert fa == fb


def test_disabled_and_missing_key(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=False,
        EXTERNAL_INTELLIGENCE_PROVIDER="gemini_google",
        GEMINI_API_KEY="",
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    out = service.get_context("XAUUSD")
    assert out["status"] == "DISABLED"


def test_missing_api_key_when_enabled(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="gemini_google",
        GEMINI_API_KEY="",
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    out = service.get_context("XAUUSD", force_refresh=True)
    assert out["status"] == "DISABLED"
    assert any("GEMINI_API_KEY" in str(u) for u in (out.get("unknowns") or []))


def test_failure_modes(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
    )
    cases = (
        ("timeout", "UNAVAILABLE"),
        ("no_sources", "INSUFFICIENT_EVIDENCE"),
        ("malformed", "UNAVAILABLE"),
    )
    for scenario, status in cases:
        svc = ExternalContextService(
            settings,
            snapshot_loader=lambda _s: _snap(),
            provider=FakeExternalIntelligenceProvider(scenario=scenario),
            cache=ExternalContextCache(root=tmp_path / scenario, ttl_seconds=600),
        )
        out = svc.get_context("XAUUSD", force_refresh=True)
        assert out["status"] == status


def test_snapshot_unavailable(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
    )

    def _boom(_symbol: str) -> dict[str, object]:
        raise RuntimeError("snapshot down")

    svc = ExternalContextService(
        settings,
        snapshot_loader=_boom,
        provider=FakeExternalIntelligenceProvider(),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    out = svc.get_context("XAUUSD", force_refresh=True)
    assert out["status"] == "UNAVAILABLE"


def test_sources_claim_relationship_and_undated(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
    )
    svc = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        provider=FakeExternalIntelligenceProvider(scenario="mixed"),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    out = svc.get_context("XAUUSD", force_refresh=True)
    sources = out["sources"]
    assert isinstance(sources, list) and len(sources) >= 2
    ids = {s["source_id"] for s in sources}  # type: ignore[index]
    for claim in out["claims"]:  # type: ignore[union-attr]
        for sid in claim["source_ids"]:  # type: ignore[index]
            assert sid in ids
    assert all(s["freshness"] == "UNDATED" for s in sources)  # type: ignore[index]
    assert classify_source_type("federalreserve.gov").value == "OFFICIAL"


def test_prompt_injection_treated_as_text(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
    )
    svc = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        provider=FakeExternalIntelligenceProvider(scenario="bearish"),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    out = svc.get_context("XAUUSD", force_refresh=True)
    blob = str(out).lower()
    assert "order_send" not in blob
    assert out["status"] in {"AVAILABLE", "PARTIAL", "INSUFFICIENT_EVIDENCE"}
    assert "execution" not in out


def test_static_safety_audit() -> None:
    package = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "exness_bot"
        / "market_analysis"
        / "external_context"
    )
    forbidden = (
        "ExecutionOrchestrator",
        "GatedMT5ExecutionPort",
        "MT5Executor",
        "LiveMT5ExecutionTransport",
        "CandidateExecutionService",
        "ExecutionCandidate",
        "CandidateExecutionAdapter",
    )
    for py in package.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "order_send" not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    for name in forbidden:
                        assert name not in alias.name
                        assert name not in (node.module or "")


def test_cache_model_key_difference(tmp_path: Path) -> None:
    settings_a = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
        EXTERNAL_INTELLIGENCE_MODEL="model-a",
    )
    settings_b = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
        EXTERNAL_INTELLIGENCE_MODEL="model-b",
    )
    cache = ExternalContextCache(root=tmp_path, ttl_seconds=600)
    svc_a = ExternalContextService(
        settings_a,
        snapshot_loader=lambda _s: _snap(),
        provider=FakeExternalIntelligenceProvider(scenario="bearish"),
        cache=cache,
    )
    first = svc_a.get_context("XAUUSD", force_refresh=True)
    assert first["cache"]["hit"] is False
    svc_b = ExternalContextService(
        settings_b,
        snapshot_loader=lambda _s: _snap(),
        provider=FakeExternalIntelligenceProvider(scenario="bullish"),
        cache=cache,
    )
    second = svc_b.get_context("XAUUSD", force_refresh=False)
    assert second["cache"]["hit"] is False


def test_api_external_context_disabled(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=False,
        DATA_SOURCE="mock",
    )
    service = ReadService(
        settings,
        MockTradingDataProvider(settings),
        project_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_read_service] = lambda: service
    client = TestClient(app)
    resp = client.get("/api/v1/analysis/XAUUSD/external-context")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "DISABLED"
    assert client.post("/api/v1/analysis/XAUUSD/external-context").status_code in {
        405,
        422,
    }
