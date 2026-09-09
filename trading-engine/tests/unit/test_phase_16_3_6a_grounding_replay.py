"""Phase 16.3.6A — grounding replay & provider contract hardening tests."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.analyst_chat.context_builder import (
    MarketAnalystContextBuilder,
)
from exness_bot.market_analysis.analyst_chat.fake_provider import (
    FakeMarketAnalystProvider,
)
from exness_bot.market_analysis.analyst_chat.models import (
    MarketAnalystContext,
    SourceRef,
)
from exness_bot.market_analysis.analyst_chat.provider_base import (
    MarketAnalystProviderResponse,
)
from exness_bot.market_analysis.analyst_chat.service import MarketAnalystChatService
from exness_bot.market_analysis.analyst_chat.session import ChatSessionStore
from exness_bot.market_analysis.analyst_chat.validator import (
    ValidationError,
    validate_provider_response,
)
from exness_bot.market_analysis.external_context.cache import ExternalContextCache
from exness_bot.market_analysis.external_context.fake_provider import (
    FakeExternalIntelligenceProvider,
)
from exness_bot.market_analysis.external_context.fingerprint import (
    technical_fingerprint,
)
from exness_bot.market_analysis.external_context.gemini_adapter import (
    adapt_gemini_grounded_response,
    response_from_dict,
)
from exness_bot.market_analysis.external_context.models import CacheMeta
from exness_bot.market_analysis.external_context.normalizer import (
    normalize_provider_result,
)
from exness_bot.market_analysis.external_context.service import ExternalContextService
from exness_bot.market_analysis.integration.errors import (
    assert_no_secret,
    classify_provider_exception,
    redact_secrets,
    sanitize_error_message,
)
from exness_bot.market_analysis.integration.replay.loader import (
    fixture_set_hash,
    load_all_fixtures,
    load_technical_case,
)
from exness_bot.market_analysis.integration.replay.runner import (
    run_all_fixtures,
    run_fixture,
)
from exness_bot.market_analysis.integration.replay.sanitizer import (
    sanitize_provider_payload,
)
from exness_bot.market_analysis.synthesis.cache import SynthesisCache
from exness_bot.market_analysis.synthesis.fake_provider import (
    FakeMarketSynthesisProvider,
)
from exness_bot.market_analysis.synthesis.service import MarketSynthesisService

ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "exness_bot"
    / "market_analysis"
)


@pytest.fixture
def snap_a() -> dict:
    data = load_technical_case("case_a_conflicting_wait.json")
    return {k: v for k, v in data.items() if k != "case_id"}


def test_replay_all_fixtures_offline() -> None:
    report = run_all_fixtures()
    assert report["network_required"] is False
    assert report["real_grounding"] == "NOT_RUN"
    assert report["phase_16_3_6_status"] == "BLOCKED"
    assert report["failed"] == 0
    assert report["fixture_count"] >= 8
    assert report["fixture_set_hash"]


def test_fixture_set_hash_stable() -> None:
    fixtures = load_all_fixtures()
    h1 = fixture_set_hash(fixtures)
    h2 = fixture_set_hash(fixtures)
    assert h1 == h2
    assert len(h1) == 24


def test_grounding_normal() -> None:
    r = run_fixture("grounding_normal")
    assert r.passed, r.errors


def test_missing_published_at_undated() -> None:
    r = run_fixture("grounding_missing_published_at")
    assert r.passed, r.errors
    assert r.checks.get("published_at_null") is True


def test_duplicate_sources() -> None:
    r = run_fixture("grounding_duplicate_sources")
    assert r.passed, r.errors


def test_redirect_urls_preserved_offline() -> None:
    r = run_fixture("grounding_redirect_urls")
    assert r.passed, r.errors


def test_unsafe_urls_rejected() -> None:
    r = run_fixture("grounding_unsafe_url")
    assert r.passed, r.errors


def test_no_sources_insufficient() -> None:
    r = run_fixture("grounding_no_sources")
    assert r.passed, r.errors
    assert r.source_count == 0


def test_malformed_response() -> None:
    r = run_fixture("grounding_malformed_candidate")
    assert r.passed, r.errors


def test_conflicting_alignment_case_a(snap_a: dict) -> None:
    r = run_fixture("grounding_conflicting_sources")
    assert r.passed, r.errors


def test_stable_source_ids(snap_a: dict) -> None:
    fx = next(f for f in load_all_fixtures() if f.fixture_id == "grounding_normal")
    fp = technical_fingerprint(
        symbol="XAUUSD", schema_version="1.0", snapshot=snap_a
    )
    now = datetime(2026, 9, 9, 8, 40, tzinfo=UTC)

    def _ids() -> list[str]:
        pr = adapt_gemini_grounded_response(
            response_from_dict(fx.response), provider="replay", model="f"
        )
        ctx = normalize_provider_result(
            result=pr,
            symbol="XAUUSD",
            snapshot=snap_a,
            search_plan={},
            technical_fingerprint=fp,
            technical_snapshot_timestamp=snap_a["generated_at"],
            cache=CacheMeta(
                hit=False, age_seconds=0, expires_at=None, fingerprint=fp
            ),
            now=now,
        )
        return [s.source_id for s in ctx.sources]

    assert _ids() == _ids()
    assert _ids()[0].startswith("src_")


def test_cache_contract_same_fingerprint(tmp_path: Path, snap_a: dict) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="fake",
    )
    calls = {"n": 0}

    class CountingFake(FakeExternalIntelligenceProvider):
        def fetch_context(self, request):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return super().fetch_context(request)

    svc = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: snap_a,
        provider=CountingFake(scenario="mixed"),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    a = svc.get_context("XAUUSD", force_refresh=True)
    b = svc.get_context("XAUUSD", force_refresh=False)
    assert calls["n"] == 1
    assert (b.get("cache") or {}).get("hit") is True
    assert a.get("technical_fingerprint") == b.get("technical_fingerprint")


def test_quote_tick_does_not_change_technical_fingerprint(snap_a: dict) -> None:
    a = dict(snap_a)
    b = dict(snap_a)
    b["current_price"] = float(a["current_price"]) + 1.5
    fa = technical_fingerprint(symbol="XAUUSD", schema_version="1.0", snapshot=a)
    fb = technical_fingerprint(symbol="XAUUSD", schema_version="1.0", snapshot=b)
    assert fa == fb


def test_closed_candle_changes_fingerprint(snap_a: dict) -> None:
    a = dict(snap_a)
    b = dict(snap_a)
    b["timeframes"] = dict(a["timeframes"])
    b["timeframes"]["M15"] = dict(a["timeframes"]["M15"])
    b["timeframes"]["M15"]["last_closed_candle_timestamp"] = (
        "2026-09-09T08:30:00+00:00"
    )
    fa = technical_fingerprint(symbol="XAUUSD", schema_version="1.0", snapshot=a)
    fb = technical_fingerprint(symbol="XAUUSD", schema_version="1.0", snapshot=b)
    assert fa != fb


def test_synthesis_replay(tmp_path: Path, snap_a: dict) -> None:
    settings = Settings(AI_MARKET_SYNTHESIS_ENABLED=False)
    ext = run_fixture("grounding_normal")
    assert ext.passed

    # Build external via adapter+normalizer
    fx = next(f for f in load_all_fixtures() if f.fixture_id == "grounding_normal")
    fp = technical_fingerprint(symbol="XAUUSD", schema_version="1.0", snapshot=snap_a)
    pr = adapt_gemini_grounded_response(response_from_dict(fx.response))
    external = normalize_provider_result(
        result=pr,
        symbol="XAUUSD",
        snapshot=snap_a,
        search_plan={},
        technical_fingerprint=fp,
        technical_snapshot_timestamp=snap_a["generated_at"],
        cache=CacheMeta(hit=False, age_seconds=0, expires_at=None, fingerprint=fp),
        now=datetime(2026, 9, 9, 8, 40, tzinfo=UTC),
    ).to_dict()

    svc = MarketSynthesisService(
        settings,
        snapshot_loader=lambda _s: snap_a,
        external_loader=lambda _s: external,
        provider=FakeMarketSynthesisProvider(),
        cache=SynthesisCache(root=tmp_path, ttl_seconds=600),
    )
    out = svc.get_synthesis("XAUUSD", force_refresh=True)
    assert out.get("technical_view")
    assert (out.get("technical_view") or {}).get("bot_signal") == "WAIT"
    assert out.get("synthesis")


def test_chat_causality_reject(tmp_path: Path, snap_a: dict) -> None:
    settings = Settings(AI_MARKET_ANALYST_CHAT_ENABLED=True)
    builder = MarketAnalystContextBuilder(
        settings,
        snapshot_loader=lambda _s: snap_a,
        external_loader=lambda _s: {
            "status": "AVAILABLE",
            "external_bias": "BULLISH_FOR_GOLD",
            "alignment_with_technical": "SUPPORT",
            "sources": [],
        },
        synthesis_loader=lambda _s: {
            "status": "AVAILABLE",
            "synthesis": {"summary": "x", "what_to_watch": []},
        },
    )
    provider = FakeMarketAnalystProvider(
        canned_answer="Bot WAIT vì external bullish.",
        answer_type="BOT_SIGNAL_EXPLANATION",
    )
    svc = MarketAnalystChatService(
        settings,
        context_builder=builder,
        provider=provider,
        session_store=ChatSessionStore(root=tmp_path),
    )
    resp = svc.chat(symbol="XAUUSD", message="Tại sao bot WAIT?")
    assert resp.provider_metadata.fallback_used is True
    assert "provider_rejected:false_external_causality" in resp.warnings or (
        "không tham gia" in resp.answer.lower()
        or "external" in resp.answer.lower()
    )


def test_chat_technical_contradiction() -> None:
    ctx = MarketAnalystContext(
        schema_version="1.0",
        symbol="XAUUSD",
        generated_at="t",
        technical_fingerprint="a",
        external_fingerprint="b",
        synthesis_fingerprint="c",
        technical={
            "bot_signal": "WAIT",
            "timeframes": {"M15": {"trend": "BULLISH", "role": "PRIMARY"}},
        },
        external={},
        synthesis={},
        sources=[],
        freshness={},
        context_status="AVAILABLE",
    )
    raw = MarketAnalystProviderResponse(
        answer="M15 đang bearish và sẽ dump.",
        answer_type="TECHNICAL_EXPLANATION",
    )
    with pytest.raises(ValidationError) as ei:
        validate_provider_response(raw, context=ctx)
    assert ei.value.reason == "technical_contradiction_m15"


def test_chat_execution_claim() -> None:
    ctx = MarketAnalystContext(
        schema_version="1.0",
        symbol="XAUUSD",
        generated_at="t",
        technical_fingerprint="a",
        external_fingerprint="b",
        synthesis_fingerprint="c",
        technical={"bot_signal": "WAIT", "timeframes": {}},
        external={},
        synthesis={},
        sources=[],
        freshness={},
        context_status="AVAILABLE",
    )
    raw = MarketAnalystProviderResponse(
        answer="Tôi đã mở lệnh SHORT.",
        answer_type="GENERAL_MARKET_QUESTION",
    )
    with pytest.raises(ValidationError) as ei:
        validate_provider_response(raw, context=ctx)
    assert ei.value.reason == "execution_language"


def test_chat_source_integrity() -> None:
    ctx = MarketAnalystContext(
        schema_version="1.0",
        symbol="XAUUSD",
        generated_at="t",
        technical_fingerprint="a",
        external_fingerprint="b",
        synthesis_fingerprint="c",
        technical={},
        external={},
        synthesis={},
        sources=[
            SourceRef(
                source_id="src_a",
                title="A",
                domain="reuters.com",
                url="https://www.reuters.com/a",
            )
        ],
        freshness={},
        context_status="AVAILABLE",
    )
    raw = MarketAnalystProviderResponse(
        answer="See sources.",
        answer_type="EXTERNAL_EXPLANATION",
        source_refs=["src_a", "src_fake"],
    )
    _ans, _t, refs, sources, _w = validate_provider_response(raw, context=ctx)
    assert refs == ["src_a"]
    assert [s.source_id for s in sources] == ["src_a"]


def test_context_changed_on_fingerprint(tmp_path: Path, snap_a: dict) -> None:
    settings = Settings(AI_MARKET_ANALYST_CHAT_ENABLED=False)
    box: dict[str, dict] = {"snap": snap_a}

    def loader(_s: str) -> dict:
        return box["snap"]

    builder = MarketAnalystContextBuilder(
        settings,
        snapshot_loader=loader,
        external_loader=lambda _s: {"status": "DISABLED", "sources": []},
        synthesis_loader=lambda _s: {"status": "TECHNICAL_ONLY", "synthesis": {}},
    )
    store = ChatSessionStore(root=tmp_path)
    svc = MarketAnalystChatService(
        settings, context_builder=builder, session_store=store
    )
    r1 = svc.chat(symbol="XAUUSD", message="Giá hiện tại?")
    assert r1.context_changed is False
    new_snap = dict(snap_a)
    new_snap["timeframes"] = dict(snap_a["timeframes"])
    new_snap["timeframes"]["M15"] = dict(snap_a["timeframes"]["M15"])
    new_snap["timeframes"]["M15"]["last_closed_candle_timestamp"] = (
        "2026-09-09T08:30:00+00:00"
    )
    box["snap"] = new_snap
    r2 = svc.chat(
        symbol="XAUUSD", message="Giá hiện tại?", session_id=r1.session_id
    )
    assert r2.context_changed is True


def test_provider_error_mapping() -> None:
    assert classify_provider_exception(TimeoutError("timed out")) == "TIMEOUT"
    assert (
        classify_provider_exception(RuntimeError("429 rate limit")) == "RATE_LIMIT"
    )
    assert classify_provider_exception(PermissionError("auth failed")) == "AUTH_ERROR"
    assert "AUTH_ERROR" in sanitize_error_message("AUTH_ERROR")


def test_secret_redaction() -> None:
    secret = "TEST_SECRET_NEVER_LOG"
    blob = f"header Authorization: Bearer {secret} and AIzaSyFakeKey1234567890"
    cleaned = redact_secrets(blob, fake_secret=secret)
    assert secret not in cleaned
    assert "AIza" not in cleaned or "[REDACTED]" in cleaned
    assert_no_secret({"msg": cleaned}, secret)
    sanitized = sanitize_provider_payload(
        {"api_key": secret, "text": "ok", "authorization": "Bearer x"}
    )
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["authorization"] == "[REDACTED]"


def test_static_google_search_isolation() -> None:
    syn = (ROOT / "synthesis" / "gemini_provider.py").read_text(encoding="utf-8")
    chat = (ROOT / "analyst_chat" / "gemini_provider.py").read_text(encoding="utf-8")
    ext = (ROOT / "external_context" / "gemini_provider.py").read_text(
        encoding="utf-8"
    )
    assert "google_search" in ext or "GoogleSearch" in ext
    assert "google_search" not in syn and "GoogleSearch" not in syn
    assert "google_search" not in chat and "GoogleSearch" not in chat


def test_static_safety_replay_package() -> None:
    pkg = ROOT / "integration" / "replay"
    banned = (
        "ExecutionCandidate",
        "ExecutionOrchestrator",
        "MT5Executor",
        "LiveMT5ExecutionTransport",
    )
    banned_ident = "order" + "_send"
    for path in pkg.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in banned:
            assert name not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == banned_ident:
                raise AssertionError(banned_ident)
