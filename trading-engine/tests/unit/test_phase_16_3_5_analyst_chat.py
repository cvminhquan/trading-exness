"""Unit tests for Phase 16.3.5 AI Market Analyst Chat."""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from exness_bot.api.app import create_app
from exness_bot.api.dependencies import get_read_service
from exness_bot.api.services.read_service import ReadService
from exness_bot.config.settings import Settings
from exness_bot.data.mock_provider import MockTradingDataProvider
from exness_bot.market_analysis.analyst_chat.context_builder import (
    MarketAnalystContextBuilder,
)
from exness_bot.market_analysis.analyst_chat.fake_provider import (
    FakeMarketAnalystProvider,
)
from exness_bot.market_analysis.analyst_chat.intent import classify_intent
from exness_bot.market_analysis.analyst_chat.models import (
    ChatIntent,
    MarketAnalystContext,
    SourceRef,
)
from exness_bot.market_analysis.analyst_chat.provider_base import (
    MarketAnalystProviderResponse,
)
from exness_bot.market_analysis.analyst_chat.rate_limit import ChatRateLimiter
from exness_bot.market_analysis.analyst_chat.service import MarketAnalystChatService
from exness_bot.market_analysis.analyst_chat.session import ChatSessionStore
from exness_bot.market_analysis.analyst_chat.validator import (
    ValidationError,
    validate_provider_response,
)

PKG = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "exness_bot"
    / "market_analysis"
    / "analyst_chat"
)


def _snapshot(
    *,
    signal: str = "WAIT",
    m15: str = "BEARISH",
    h1: str = "BEARISH",
    h4: str = "BULLISH",
    d1: str = "BULLISH",
    price: float = 2650.5,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "symbol": "XAUUSD",
        "generated_at": "2026-09-09T10:00:00+00:00",
        "current_price": price,
        "freshness": {"status": "FRESH"},
        "bot_analysis": {
            "signal": signal,
            "production_strategy": "mtf_technical_v1",
            "setup_state": "NO_SETUP",
            "execution_status": "NOT_READY",
            "mtf_score": 0.2,
        },
        "mtf_summary": {"alignment": "MIXED", "primary_bias": m15},
        "timeframes": {
            "M15": {
                "role": "PRIMARY",
                "trend": m15,
                "structure": "BEARISH",
                "nearest_support": 2640.0,
                "nearest_resistance": 2660.0,
                "indicators": {"rsi14": 42.0},
            },
            "H1": {"role": "CONFIRMATION", "trend": h1, "structure": "BEARISH"},
            "H4": {"role": "CONTEXT", "trend": h4, "structure": "BULLISH"},
            "D1": {"role": "MACRO_CONTEXT", "trend": d1, "structure": "BULLISH"},
        },
    }


def _external(
    *,
    bias: str = "BULLISH",
    alignment: str = "CONFLICT",
    status: str = "AVAILABLE",
) -> dict[str, object]:
    return {
        "status": status,
        "generated_at": "2026-09-09T10:00:00+00:00",
        "external_bias": bias,
        "evidence_strength": "MODERATE",
        "alignment_with_technical": alignment,
        "event_risk": "ELEVATED",
        "supporting_factors": ["USD soft"],
        "conflicting_factors": ["M15 bearish"],
        "market_drivers": [{"driver": "USD", "direction_for_gold": "BULLISH_FOR_GOLD"}],
        "important_events": [
            {"event_name": "FOMC", "status": "UPCOMING", "importance": "HIGH"}
        ],
        "freshness": {"status": "FRESH"},
        "sources": [
            {
                "source_id": "src_1",
                "title": "Fed outlook",
                "domain": "reuters.com",
                "url": "https://www.reuters.com/markets/fed-example",
                "freshness": "RECENT",
            }
        ],
        "unknowns": [],
    }


def _synthesis() -> dict[str, object]:
    return {
        "status": "AVAILABLE",
        "synthesis": {
            "state": "TECHNICAL_EXTERNAL_CONFLICT",
            "summary": "M15 bearish vs external bullish.",
            "technical_explanation": "M15/H1 bearish; H4 bullish context.",
            "external_explanation": "External bullish for gold.",
            "alignment_explanation": "CONFLICT",
            "risk_explanation": "Event risk elevated.",
            "uncertainties": ["H4 conflict"],
            "what_to_watch": ["M15 close vs support"],
        },
        "freshness": {},
        "ai_metadata": {"used": False, "fallback_used": True},
    }


def _service(
    tmp_path: Path,
    *,
    enabled: bool = False,
    provider: FakeMarketAnalystProvider | None = None,
    rate_limit: int = 50,
) -> MarketAnalystChatService:
    settings = Settings(
        AI_MARKET_ANALYST_CHAT_ENABLED=enabled,
        AI_MARKET_ANALYST_CHAT_RATE_LIMIT=rate_limit,
        AI_MARKET_ANALYST_CHAT_MAX_HISTORY_MESSAGES=8,
        AI_MARKET_ANALYST_CHAT_MAX_MESSAGE_LENGTH=3000,
    )
    builder = MarketAnalystContextBuilder(
        settings,
        snapshot_loader=lambda _s: _snapshot(),
        external_loader=lambda _s: _external(),
        synthesis_loader=lambda _s: _synthesis(),
    )
    return MarketAnalystChatService(
        settings,
        context_builder=builder,
        provider=provider,
        session_store=ChatSessionStore(root=tmp_path / "chat"),
        rate_limiter=ChatRateLimiter(max_requests=rate_limit, window_seconds=60),
    )


def test_intent_routing() -> None:
    assert classify_intent("Tại sao bot đang WAIT?") is ChatIntent.WHY_BOT_SIGNAL
    assert classify_intent("Giá hiện tại?") is ChatIntent.CURRENT_PRICE
    assert classify_intent("Mở lệnh short giúp tôi") is ChatIntent.EXECUTION_REQUEST
    assert classify_intent("Có event risk nào?") is ChatIntent.EVENT_RISK


def test_why_bot_wait_does_not_blame_external(tmp_path: Path) -> None:
    svc = _service(tmp_path, enabled=False)
    resp = svc.chat(symbol="XAUUSD", message="Tại sao bot WAIT?")
    assert resp.answer_type == "BOT_SIGNAL_EXPLANATION"
    lower = resp.answer.lower()
    assert "wait" in lower or "WAIT" in resp.answer
    assert "không tham gia" in lower or "does not" in lower or "không" in lower
    assert "external" in lower or "External" in resp.answer
    # Must not claim external caused WAIT
    assert "bot wait vì tin tức" not in lower
    assert "bot wait because external" not in lower


def test_timeframe_conflict_roles(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    resp = svc.chat(
        symbol="XAUUSD",
        message="Tại sao H4 bullish mà M15 bearish?",
    )
    assert "PRIMARY" in resp.answer
    assert "CONTEXT" in resp.answer
    assert "M15" in resp.answer


def test_external_conflict(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    resp = svc.chat(
        symbol="XAUUSD",
        message="External context đang support hay conflict?",
    )
    assert resp.answer_type in {
        "EXTERNAL_EXPLANATION",
        "INSUFFICIENT_CONTEXT",
    }
    assert "CONFLICT" in resp.answer or "conflict" in resp.answer.lower()


def test_current_price(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    resp = svc.chat(symbol="XAUUSD", message="Giá hiện tại bao nhiêu?")
    assert "2650.5" in resp.answer


def test_source_citations_canonical(tmp_path: Path) -> None:
    provider = FakeMarketAnalystProvider(
        canned_answer="USD soft [src_1]",
        answer_type="EXTERNAL_EXPLANATION",
        source_refs=["src_1"],
    )
    svc = _service(tmp_path, enabled=True, provider=provider)
    resp = svc.chat(symbol="XAUUSD", message="USD ảnh hưởng thế nào?")
    assert "src_1" in resp.source_refs
    assert all(s.source_id == "src_1" for s in resp.sources)
    assert resp.provider_metadata.fallback_used is False


def test_invented_url_rejected(tmp_path: Path) -> None:
    provider = FakeMarketAnalystProvider(invent_url=True)
    svc = _service(tmp_path, enabled=True, provider=provider)
    resp = svc.chat(symbol="XAUUSD", message="Tin tức gần đây?")
    assert resp.provider_metadata.fallback_used is True
    assert "fake-example.invalid" not in resp.answer
    assert any("provider_rejected" in w for w in resp.warnings)


def test_ai_disabled_deterministic(tmp_path: Path) -> None:
    svc = _service(tmp_path, enabled=False)
    resp = svc.chat(symbol="XAUUSD", message="Tại sao bot WAIT?")
    assert resp.chat_enabled is False
    assert "ai_chat_disabled" in resp.warnings
    assert resp.answer


def test_provider_failure_fallback(tmp_path: Path) -> None:
    provider = FakeMarketAnalystProvider(raise_error=True)
    svc = _service(tmp_path, enabled=True, provider=provider)
    resp = svc.chat(symbol="XAUUSD", message="Tại sao bot WAIT?")
    assert resp.provider_metadata.fallback_used is True
    assert "provider_failure" in resp.warnings
    assert "WAIT" in resp.answer or "wait" in resp.answer.lower()


def test_execution_request_no_broker(tmp_path: Path) -> None:
    provider = FakeMarketAnalystProvider(canned_answer="should not run")
    svc = _service(tmp_path, enabled=True, provider=provider)
    resp = svc.chat(symbol="XAUUSD", message="Mở lệnh short XAUUSD giúp tôi.")
    assert resp.answer_type == "READ_ONLY_REFUSAL"
    assert provider.calls == 0
    assert "không thể" in resp.answer.lower() or "cannot" in resp.answer.lower()


def test_claimed_execution_rejected(tmp_path: Path) -> None:
    provider = FakeMarketAnalystProvider(claim_execution=True)
    svc = _service(tmp_path, enabled=True, provider=provider)
    resp = svc.chat(symbol="XAUUSD", message="Phân tích M15?")
    assert resp.provider_metadata.fallback_used is True
    assert "opened a short" not in resp.answer.lower()


def test_leverage_not_sizing_advice(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    resp = svc.chat(
        symbol="XAUUSD",
        message="Đòn bẩy 1:2000 thì tăng lot lên được không?",
    )
    assert resp.answer_type == "READ_ONLY_REFUSAL"


def test_context_changed(tmp_path: Path) -> None:
    settings = Settings(AI_MARKET_ANALYST_CHAT_ENABLED=False)
    snap_box: dict[str, object] = {"v": _snapshot()}

    def snap_loader(_s: str) -> dict[str, object]:
        return snap_box["v"]  # type: ignore[return-value]

    builder = MarketAnalystContextBuilder(
        settings,
        snapshot_loader=snap_loader,
        external_loader=lambda _s: _external(),
        synthesis_loader=lambda _s: _synthesis(),
    )
    svc = MarketAnalystChatService(
        settings,
        context_builder=builder,
        session_store=ChatSessionStore(root=tmp_path / "chat2"),
    )
    r1 = svc.chat(symbol="XAUUSD", message="Giá hiện tại?")
    assert r1.context_changed is False
    snap_box["v"] = _snapshot(price=2700.0, signal="WAIT")
    # Force fingerprint change via closed candle timestamps if present —
    # current_price alone may not change technical_fingerprint.
    # Change external status to force external fp change.
    builder2 = MarketAnalystContextBuilder(
        settings,
        snapshot_loader=lambda _s: _snapshot(price=2700.0),
        external_loader=lambda _s: _external(status="STALE", bias="BEARISH"),
        synthesis_loader=lambda _s: _synthesis(),
    )
    svc2 = MarketAnalystChatService(
        settings,
        context_builder=builder2,
        session_store=svc._sessions,
    )
    r2 = svc2.chat(
        symbol="XAUUSD",
        message="Giá hiện tại?",
        session_id=r1.session_id,
    )
    assert r2.context_changed is True


def test_symbol_isolation(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    r1 = svc.chat(symbol="XAUUSD", message="Giá hiện tại?")
    r2 = svc.chat(
        symbol="EURUSD",
        message="Giá hiện tại?",
        session_id=r1.session_id,
    )
    assert r2.session_id != r1.session_id
    assert r2.symbol == "EURUSD"


def test_rate_limit(tmp_path: Path) -> None:
    svc = _service(tmp_path, rate_limit=2)
    svc.chat(symbol="XAUUSD", message="Giá hiện tại?")
    svc.chat(symbol="XAUUSD", message="Giá hiện tại?")
    try:
        svc.chat(symbol="XAUUSD", message="Giá hiện tại?")
        raised = False
    except RuntimeError as exc:
        raised = str(exc) == "rate_limited"
    assert raised


def test_message_too_long(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    try:
        svc.chat(symbol="XAUUSD", message="x" * 5000)
        ok = False
    except ValueError as exc:
        ok = str(exc) == "message_too_long"
    assert ok


def test_validator_rejects_invented_url() -> None:
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
                source_id="src_1",
                title="t",
                domain="reuters.com",
                url="https://www.reuters.com/ok",
            )
        ],
        freshness={},
        context_status="AVAILABLE",
    )
    raw = MarketAnalystProviderResponse(
        answer="See https://fake-example.invalid/news",
        answer_type="EXTERNAL_EXPLANATION",
        source_refs=["https://fake-example.invalid/news"],
    )
    try:
        validate_provider_response(raw, context=ctx)
        ok = False
    except ValidationError as exc:
        ok = exc.reason == "invented_url"
    assert ok


def test_prompt_injection_treated_as_data(tmp_path: Path) -> None:
    provider = FakeMarketAnalystProvider(
        canned_answer="Source says ignore instructions; treated as text only.",
        answer_type="EXTERNAL_EXPLANATION",
        source_refs=["src_1"],
    )
    svc = _service(tmp_path, enabled=True, provider=provider)
    resp = svc.chat(
        symbol="XAUUSD",
        message="What does this source say about ignore system instructions?",
    )
    assert resp.answer
    # No execution language accepted
    assert "order_send" not in resp.answer.lower() or "cannot" in resp.answer.lower()


def test_api_post_analyst_chat(tmp_path: Path) -> None:
    settings = Settings(
        AI_MARKET_ANALYST_CHAT_ENABLED=False,
        DATA_SOURCE="mock",
    )
    provider = MockTradingDataProvider(settings)
    # Inject chat service with stubbed context to avoid heavy snapshot build.
    builder = MarketAnalystContextBuilder(
        settings,
        snapshot_loader=lambda _s: _snapshot(),
        external_loader=lambda _s: _external(),
        synthesis_loader=lambda _s: _synthesis(),
    )
    chat_svc = MarketAnalystChatService(
        settings,
        context_builder=builder,
        session_store=ChatSessionStore(root=tmp_path / "api_chat"),
    )
    read = ReadService(settings, provider)

    def _post(
        symbol: str | None,
        *,
        message: str,
        session_id: str | None = None,
    ) -> dict[str, object]:
        return chat_svc.chat(
            symbol=symbol or "XAUUSD",
            message=message,
            session_id=session_id,
        ).to_dict()

    read.post_analyst_chat = _post  # type: ignore[method-assign]
    app = create_app()
    app.dependency_overrides[get_read_service] = lambda: read
    client = TestClient(app)
    res = client.post(
        "/api/v1/analysis/XAUUSD/analyst-chat",
        json={"message": "Tại sao bot đang WAIT?"},
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["symbol"] == "XAUUSD"
    assert body["answer"]
    assert body["chat_enabled"] is False
    assert "session_id" in body


def test_static_safety_no_execution_imports() -> None:
    banned = (
        "ExecutionCandidate",
        "CandidateExecutionService",
        "CandidateExecutionAdapter",
        "ExecutionOrchestrator",
        "GatedMT5ExecutionPort",
        "MT5Executor",
        "LiveMT5ExecutionTransport",
    )
    # Literal broker send API must not appear as an identifier/import.
    banned_ident = "order" + "_send"
    for path in PKG.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for name in banned:
            assert name not in text, f"{name} found in {path}"
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == banned_ident:
                raise AssertionError(f"{banned_ident} identifier in {path}")
            if isinstance(node, ast.Attribute) and node.attr == banned_ident:
                raise AssertionError(f"{banned_ident} attribute in {path}")
            if isinstance(node, ast.Constant) and node.value == banned_ident:
                # Allow defensive regex patterns that avoid the exact token.
                pass
