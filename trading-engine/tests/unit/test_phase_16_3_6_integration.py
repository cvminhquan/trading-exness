"""Phase 16.3.6 hardening tests — preflight, metrics, static tool isolation."""

from __future__ import annotations

import ast
from pathlib import Path

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.integration.metrics import (
    IntegrationMetrics,
    get_integration_metrics,
)
from exness_bot.market_analysis.integration.preflight import run_preflight

ROOT = Path(__file__).resolve().parents[2] / "src" / "exness_bot" / "market_analysis"


def test_preflight_never_includes_secret_value() -> None:
    settings = Settings(GEMINI_API_KEY="")
    report = run_preflight(settings)
    blob = str(report)
    assert "gemini_api_key_configured" in report
    assert report["gemini_api_key_configured"] is False
    assert report["gemini_api_key_printed"] is False
    # no raw key field
    assert "gemini_api_key" not in report
    assert "AIza" not in blob


def test_preflight_block_reason_when_key_missing() -> None:
    settings = Settings(
        GEMINI_API_KEY="",
        EXTERNAL_INTELLIGENCE_ENABLED=True,
    )
    report = run_preflight(settings)
    assert report["block_reason"] == "GEMINI_API_KEY NOT CONFIGURED"
    assert report["real_smoke_ready"] is False


def test_metrics_counters() -> None:
    m = IntegrationMetrics()
    m.inc("external_provider_calls")
    m.inc("external_cache_hits", 2)
    snap = m.snapshot()
    assert snap["external_provider_calls"] == 1
    assert snap["external_cache_hits"] == 2
    m.reset()
    assert m.snapshot()["external_provider_calls"] == 0


def test_global_metrics_reset_safe() -> None:
    get_integration_metrics().reset()
    get_integration_metrics().inc("synthesis_provider_calls")
    assert get_integration_metrics().snapshot()["synthesis_provider_calls"] >= 1
    get_integration_metrics().reset()


def _file_has_google_search_tool(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return "google_search" in text or "GoogleSearch" in text


def test_static_google_search_only_in_external() -> None:
    syn = ROOT / "synthesis" / "gemini_provider.py"
    chat = ROOT / "analyst_chat" / "gemini_provider.py"
    ext = ROOT / "external_context" / "gemini_provider.py"
    assert ext.exists()
    assert _file_has_google_search_tool(ext)
    assert not _file_has_google_search_tool(syn)
    assert not _file_has_google_search_tool(chat)


def test_static_no_execution_in_integration_package() -> None:
    pkg = ROOT / "integration"
    banned = (
        "ExecutionCandidate",
        "CandidateExecutionService",
        "ExecutionOrchestrator",
        "MT5Executor",
        "LiveMT5ExecutionTransport",
    )
    banned_ident = "order" + "_send"
    for path in pkg.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in banned:
            assert name not in text, f"{name} in {path}"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == banned_ident:
                raise AssertionError(f"{banned_ident} in {path}")
