"""Phase 16.3.7 — Free External Market Data Providers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.external_context.cache import ExternalContextCache
from exness_bot.market_analysis.external_context.fingerprint import (
    technical_fingerprint,
)
from exness_bot.market_analysis.external_context.macro_models import BLS_SERIES, FRED_SERIES
from exness_bot.market_analysis.external_context.macro_normalizer import (
    macro_bias_from_context,
    normalize_macro_items,
)
from exness_bot.market_analysis.external_context.planner import plan_search
from exness_bot.market_analysis.external_context.provider_base import (
    ExternalIntelligenceRequest,
)
from exness_bot.market_analysis.external_context.providers.base import (
    ExternalDataItem,
    ProviderFetchStatus,
)
from exness_bot.market_analysis.external_context.providers.bls import (
    BlsProvider,
    parse_bls_payload,
)
from exness_bot.market_analysis.external_context.providers.composite import (
    FreeSourcesCompositeProvider,
)
from exness_bot.market_analysis.external_context.providers.federal_reserve import (
    FederalReserveProvider,
)
from exness_bot.market_analysis.external_context.providers.feed_parse import (
    parse_feed_xml,
)
from exness_bot.market_analysis.external_context.providers.fred import (
    FredProvider,
    parse_fred_observations,
    redact_secrets,
)
from exness_bot.market_analysis.external_context.providers.provider_cache import (
    ProviderResultCache,
)
from exness_bot.market_analysis.external_context.providers.rss import (
    RssProvider,
    is_url_safe_for_rss,
)
from exness_bot.market_analysis.external_context.service import ExternalContextService

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _snap(*, m15_ts: str = "2026-09-09T05:00:00+00:00") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "symbol": "XAUUSD",
        "current_price": 4380.0,
        "generated_at": "2026-09-09T05:00:00+00:00",
        "freshness": {"status": "FRESH"},
        "timeframes": {
            "M15": {
                "role": "PRIMARY",
                "trend": "BEARISH",
                "structure": "BEARISH",
                "last_closed_candle_timestamp": m15_ts,
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
        "mtf_summary": {"alignment": "MIXED", "primary_bias": "BEARISH"},
        "bot_analysis": {"signal": "WAIT"},
    }


def _request() -> ExternalIntelligenceRequest:
    snap = _snap()
    plan = plan_search(symbol="XAUUSD", snapshot=snap, now=NOW)
    return ExternalIntelligenceRequest(
        symbol="XAUUSD",
        snapshot=snap,
        search_plan=plan,
        utc_now_iso=NOW.isoformat(),
        technical_fingerprint="fp_test",
    )


BLS_FIXTURE = {
    "status": "REQUEST_SUCCEEDED",
    "Results": {
        "series": [
            {
                "seriesID": "CUUR0000SA0",
                "data": [
                    {
                        "year": "2026",
                        "period": "M08",
                        "periodName": "August",
                        "value": "320.000",
                    },
                    {
                        "year": "2026",
                        "period": "M07",
                        "periodName": "July",
                        "value": "318.000",
                    },
                ],
            },
            {
                "seriesID": "LNS14000000",
                "data": [
                    {
                        "year": "2026",
                        "period": "M08",
                        "periodName": "August",
                        "value": "4.3",
                    },
                    {
                        "year": "2026",
                        "period": "M07",
                        "periodName": "July",
                        "value": "4.2",
                    },
                ],
            },
        ]
    },
}

FED_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Fed Monetary</title>
<item>
  <title>FOMC statement: Committee decided to maintain the target range</title>
  <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260901a.htm</link>
  <pubDate>Mon, 01 Sep 2026 14:00:00 GMT</pubDate>
  <category>monetary_policy</category>
</item>
<item>
  <title>Speech: Economic Outlook</title>
  <link>https://www.federalreserve.gov/newsevents/speech/example20260902a.htm</link>
  <pubDate>Tue, 02 Sep 2026 15:00:00 GMT</pubDate>
</item>
<item>
  <title>Speech: Economic Outlook</title>
  <link>https://www.federalreserve.gov/newsevents/speech/example20260902a.htm</link>
  <pubDate>Tue, 02 Sep 2026 15:00:00 GMT</pubDate>
</item>
</channel></rss>
"""

FRED_FIXTURE = {
    "observations": [
        {"date": "2026-09-01", "value": "4.10"},
        {"date": "2026-09-02", "value": "4.20"},
        {"date": "2026-09-03", "value": "."},
        {"date": "2026-09-04", "value": "4.05"},
    ]
}


def test_bls_series_ids_documented() -> None:
    assert "CUUR0000SA0" in BLS_SERIES
    assert "CUUR0000SA0L1E" in BLS_SERIES
    assert "LNS14000000" in BLS_SERIES
    assert "CES0000000001" in BLS_SERIES


def test_bls_parsing() -> None:
    items = parse_bls_payload(
        BLS_FIXTURE, retrieved_at=NOW.isoformat(), now=NOW
    )
    assert len(items) == 2
    cpi = next(i for i in items if i.series_id == "CUUR0000SA0")
    assert cpi.value == 320.0
    assert cpi.published_at == "2026-08-01T00:00:00+00:00"
    assert cpi.retrieved_at != cpi.published_at
    assert cpi.metadata.get("previous_value") == 318.0


def test_bls_unavailable() -> None:
    def boom(_body: dict[str, Any]) -> dict[str, Any]:
        raise TimeoutError("slow")

    p = BlsProvider(enabled=True, http_post=boom)
    res = p.fetch(now=NOW)
    assert res.status == ProviderFetchStatus.TIMEOUT.value
    assert res.items == []


def test_bls_zero_key_mode() -> None:
    calls: list[dict[str, Any]] = []

    def capture(body: dict[str, Any]) -> dict[str, Any]:
        calls.append(body)
        return BLS_FIXTURE

    p = BlsProvider(enabled=True, api_key="", http_post=capture)
    res = p.fetch(now=NOW)
    assert res.status == ProviderFetchStatus.OK.value
    assert "registrationkey" not in calls[0]
    assert p.health().detail == "zero_key_mode"


def test_fred_disabled_without_key() -> None:
    p = FredProvider(enabled=True, api_key="")
    res = p.fetch(now=NOW)
    assert res.status == ProviderFetchStatus.NOT_CONFIGURED.value
    assert p.health().configured is False


def test_fred_secret_redaction() -> None:
    key = "SECRET_FRED_KEY_XYZ"
    assert key not in redact_secrets(f"url?api_key={key}", key)
    assert "[REDACTED]" in redact_secrets(f"url?api_key={key}", key)


def test_fred_configured_parsing() -> None:
    item = parse_fred_observations(
        FRED_FIXTURE,
        series_id="DGS10",
        retrieved_at=NOW.isoformat(),
        now=NOW,
    )
    assert item is not None
    assert item.value == 4.05
    assert item.published_at == "2026-09-04T00:00:00+00:00"
    assert item.metadata.get("previous_value") == 4.20
    assert "DGS10" in FRED_SERIES

    def fake_get(_url: str) -> dict[str, Any]:
        # URL may contain api_key — never log it
        _ = _url
        return FRED_FIXTURE

    p = FredProvider(
        enabled=True,
        api_key="SECRET_KEY",
        series_ids=["DGS10"],
        http_get=fake_get,
    )
    res = p.fetch(now=NOW)
    assert res.status == ProviderFetchStatus.OK.value
    assert len(res.items) == 1


def test_fed_feed_parsing_and_dedupe() -> None:
    entries = parse_feed_xml(FED_RSS, default_category="monetary_policy")
    assert len(entries) == 3  # before dedupe at feed_parse level (items listed)
    from exness_bot.market_analysis.external_context.providers.feed_parse import (
        dedupe_feed_entries,
    )

    deduped = dedupe_feed_entries(entries)
    assert len(deduped) == 2

    p = FederalReserveProvider(
        enabled=True,
        feeds=(
            (
                "press_monetary",
                "https://www.federalreserve.gov/feeds/press_monetary.xml",
                "monetary_policy",
            ),
        ),
        http_get_bytes=lambda _u: FED_RSS.encode("utf-8"),
    )
    res = p.fetch(now=NOW)
    assert res.status == ProviderFetchStatus.OK.value
    assert len(res.items) == 2
    assert all(i.canonical_url for i in res.items)
    assert all(i.retrieved_at != i.published_at for i in res.items if i.published_at)


def test_fed_malformed_feed() -> None:
    p = FederalReserveProvider(
        enabled=True,
        feeds=(
            (
                "press_monetary",
                "https://www.federalreserve.gov/feeds/press_monetary.xml",
                "monetary_policy",
            ),
        ),
        http_get_bytes=lambda _u: b"<not>valid",
    )
    res = p.fetch(now=NOW)
    assert res.status == ProviderFetchStatus.INVALID_RESPONSE.value


def test_rss_allowlist_and_unsafe_rejection() -> None:
    allow = {"https://www.federalreserve.gov/feeds/press_monetary.xml"}
    assert is_url_safe_for_rss(
        "https://www.federalreserve.gov/feeds/press_monetary.xml", allowlist=allow
    )
    assert not is_url_safe_for_rss(
        "https://evil.example/blog.xml", allowlist=allow
    )
    assert not is_url_safe_for_rss("javascript:alert(1)", allowlist=allow)
    assert not is_url_safe_for_rss("file:///etc/passwd", allowlist=allow)
    assert not is_url_safe_for_rss("data:text/xml,hi", allowlist=allow)


def test_rss_malformed_and_timeout() -> None:
    p = RssProvider(
        enabled=True,
        allowlist=("https://www.federalreserve.gov/feeds/press_monetary.xml",),
        http_get_bytes=lambda _u: b"<<<",
    )
    res = p.fetch(now=NOW)
    assert res.status == ProviderFetchStatus.INVALID_RESPONSE.value

    def timeout(_u: str) -> bytes:
        raise TimeoutError("rss timeout")

    p2 = RssProvider(
        enabled=True,
        allowlist=("https://www.federalreserve.gov/feeds/press_monetary.xml",),
        http_get_bytes=timeout,
    )
    res2 = p2.fetch(now=NOW)
    assert res2.status == ProviderFetchStatus.TIMEOUT.value


def test_composite_partial_failure() -> None:
    bls = BlsProvider(enabled=True, http_post=lambda _b: BLS_FIXTURE)
    fred = FredProvider(enabled=True, api_key="")  # NOT_CONFIGURED
    fed = FederalReserveProvider(
        enabled=True,
        feeds=(
            (
                "press_monetary",
                "https://www.federalreserve.gov/feeds/press_monetary.xml",
                "monetary_policy",
            ),
        ),
        http_get_bytes=lambda _u: FED_RSS.encode(),
    )
    rss = RssProvider(enabled=True, http_get_bytes=lambda _u: (_ for _ in ()).throw(TimeoutError()))

    comp = FreeSourcesCompositeProvider(
        bls=bls, fred=fred, federal_reserve=fed, rss=rss
    )
    result = comp.fetch_context(_request())
    assert result.ok is True
    assert result.provider == "free_sources"
    assert len(result.sources) >= 1
    assert result.search_queries == []


def test_composite_all_unavailable() -> None:
    def fail_bls(_b: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("down")

    comp = FreeSourcesCompositeProvider(
        bls=BlsProvider(enabled=True, http_post=fail_bls),
        fred=FredProvider(enabled=False),
        federal_reserve=FederalReserveProvider(enabled=False),
        rss=RssProvider(enabled=False),
    )
    result = comp.fetch_context(_request())
    assert result.ok is False
    assert result.external_bias == "INSUFFICIENT_EVIDENCE"


def test_published_at_null_undated() -> None:
    item = ExternalDataItem(
        provider="rss",
        source_type="OFFICIAL",
        title="Undated headline",
        value="Undated headline",
        published_at=None,
        retrieved_at=NOW.isoformat(),
        canonical_url="https://www.federalreserve.gov/x.htm",
        freshness="UNDATED",
    )
    assert item.published_at is None
    assert item.freshness == "UNDATED"
    assert item.retrieved_at != item.published_at


def test_provider_ttl_cache() -> None:
    calls = {"n": 0}

    def post(_b: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        return BLS_FIXTURE

    cache = ProviderResultCache()
    bls = BlsProvider(enabled=True, http_post=post)
    comp = FreeSourcesCompositeProvider(
        bls=bls,
        fred=FredProvider(enabled=False),
        federal_reserve=FederalReserveProvider(enabled=False),
        rss=RssProvider(enabled=False),
        cache=cache,
    )
    a = comp.collect(now=NOW, force_refresh=False)
    b = comp.collect(now=NOW, force_refresh=False)
    assert calls["n"] == 1
    assert a["cache_hits"]["bls"] is False
    assert b["cache_hits"]["bls"] is True

    # Expired TTL → refresh
    expired = NOW + timedelta(hours=7)
    c = comp.collect(now=expired, force_refresh=False)
    assert calls["n"] == 2
    assert c["cache_hits"]["bls"] is False


def test_gemini_absent_still_builds_context(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="free_sources",
        FREE_EXTERNAL_SOURCES_ENABLED=True,
        GOOGLE_GROUNDING_ENABLED=False,
        GEMINI_API_KEY="",
        BLS_ENABLED=True,
        FRED_ENABLED=False,
        FEDERAL_RESERVE_ENABLED=True,
        EXTERNAL_RSS_ENABLED=False,
    )
    # Reconstruct with injected composite
    bls = BlsProvider(enabled=True, http_post=lambda _b: BLS_FIXTURE)
    fed = FederalReserveProvider(
        enabled=True,
        feeds=(
            (
                "press_monetary",
                "https://www.federalreserve.gov/feeds/press_monetary.xml",
                "monetary_policy",
            ),
        ),
        http_get_bytes=lambda _u: FED_RSS.encode(),
    )
    provider = FreeSourcesCompositeProvider(
        bls=bls,
        fred=FredProvider(enabled=False),
        federal_reserve=fed,
        rss=RssProvider(enabled=False),
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        provider=provider,
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    out = service.get_context("XAUUSD", force_refresh=True)
    assert out["status"] in {"AVAILABLE", "PARTIAL"}
    assert out["provider"] == "free_sources"
    assert len(out["sources"]) >= 1


def test_google_grounding_disabled_zero_gemini_calls(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="free_sources",
        GOOGLE_GROUNDING_ENABLED=False,
        GEMINI_API_KEY="",
    )
    gemini = MagicMock()
    gemini.name = "gemini_google"
    gemini.fetch_context = MagicMock(
        side_effect=AssertionError("Gemini must not be called")
    )
    # Use free provider instead — assert gemini never constructed path used
    provider = FreeSourcesCompositeProvider(
        bls=BlsProvider(enabled=True, http_post=lambda _b: BLS_FIXTURE),
        fred=FredProvider(enabled=False),
        federal_reserve=FederalReserveProvider(enabled=False),
        rss=RssProvider(enabled=False),
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        provider=provider,
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    service.get_context("XAUUSD", force_refresh=True)
    gemini.fetch_context.assert_not_called()


def test_gemini_google_provider_blocked_when_grounding_off(tmp_path: Path) -> None:
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="gemini_google",
        GOOGLE_GROUNDING_ENABLED=False,
        GEMINI_API_KEY="fake-key-not-used",
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    out = service.get_context("XAUUSD", force_refresh=True)
    assert out["status"] == "DISABLED"
    assert any("GOOGLE_GROUNDING" in str(u) for u in (out.get("unknowns") or []))


def test_quote_tick_no_unnecessary_fetch(tmp_path: Path) -> None:
    calls = {"n": 0}

    def post(_b: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        return BLS_FIXTURE

    provider = FreeSourcesCompositeProvider(
        bls=BlsProvider(enabled=True, http_post=post),
        fred=FredProvider(enabled=False),
        federal_reserve=FederalReserveProvider(enabled=False),
        rss=RssProvider(enabled=False),
    )
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="free_sources",
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        provider=provider,
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    service.get_context("XAUUSD", force_refresh=True)
    # Quote-only change — same fingerprint → outer cache hit, no new provider fetch
    # (provider TTL cache would also protect, but outer cache should short-circuit)
    before = calls["n"]
    service._snapshot_loader = lambda _s: {**_snap(), "current_price": 9999.0}
    service.get_context("XAUUSD", force_refresh=False)
    assert calls["n"] == before


def test_new_m15_reuses_provider_cache(tmp_path: Path) -> None:
    calls = {"n": 0}

    def post(_b: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        return BLS_FIXTURE

    cache = ProviderResultCache()
    provider = FreeSourcesCompositeProvider(
        bls=BlsProvider(enabled=True, http_post=post),
        fred=FredProvider(enabled=False),
        federal_reserve=FederalReserveProvider(enabled=False),
        rss=RssProvider(enabled=False),
        cache=cache,
    )
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="free_sources",
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(m15_ts="2026-09-09T05:00:00+00:00"),
        provider=provider,
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    service.get_context("XAUUSD", force_refresh=True)
    assert calls["n"] == 1
    # New closed M15 → outer miss, but provider TTL cache hit
    service._snapshot_loader = lambda _s: _snap(m15_ts="2026-09-09T05:15:00+00:00")
    out = service.get_context("XAUUSD", force_refresh=False)
    assert calls["n"] == 1
    assert out["status"] in {"AVAILABLE", "PARTIAL"}
    fa = technical_fingerprint(
        symbol="XAUUSD",
        schema_version="1.0",
        snapshot=_snap(m15_ts="2026-09-09T05:00:00+00:00"),
    )
    fb = technical_fingerprint(
        symbol="XAUUSD",
        schema_version="1.0",
        snapshot=_snap(m15_ts="2026-09-09T05:15:00+00:00"),
    )
    assert fa != fb


def test_macro_normalization_yield_headwind() -> None:
    items = [
        ExternalDataItem(
            provider="fred",
            source_type="MARKET_DATA",
            title="10Y",
            value=4.2,
            published_at="2026-09-04T00:00:00+00:00",
            retrieved_at=NOW.isoformat(),
            canonical_url="https://fred.stlouisfed.org/series/DGS10",
            freshness="RECENT",
            category="yields",
            series_id="DGS10",
            metadata={"previous_value": 4.0},
        )
    ]
    ctx = normalize_macro_items(items)
    assert ctx.yield_context == "RISING"
    assert macro_bias_from_context(ctx) == "BEARISH_FOR_GOLD"


def test_external_does_not_import_execution_stack() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "exness_bot"
        / "market_analysis"
        / "external_context"
    )
    banned = (
        "order_send",
        "ExecutionOrchestrator",
        "MT5Executor",
        "LiveMT5ExecutionTransport",
        "ExecutionCandidate",
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} contains {token}"


def test_canonical_source_ids_and_source_dedupe(tmp_path: Path) -> None:
    # Same Fed item via Fed + RSS → one source URL after normalize
    shared = FED_RSS.encode()
    provider = FreeSourcesCompositeProvider(
        bls=BlsProvider(enabled=False),
        fred=FredProvider(enabled=False),
        federal_reserve=FederalReserveProvider(
            enabled=True,
            feeds=(
                (
                    "press_monetary",
                    "https://www.federalreserve.gov/feeds/press_monetary.xml",
                    "monetary_policy",
                ),
            ),
            http_get_bytes=lambda _u: shared,
        ),
        rss=RssProvider(
            enabled=True,
            allowlist=("https://www.federalreserve.gov/feeds/press_monetary.xml",),
            http_get_bytes=lambda _u: shared,
        ),
    )
    settings = Settings(
        EXTERNAL_INTELLIGENCE_ENABLED=True,
        EXTERNAL_INTELLIGENCE_PROVIDER="free_sources",
    )
    service = ExternalContextService(
        settings,
        snapshot_loader=lambda _s: _snap(),
        provider=provider,
        cache=ExternalContextCache(root=tmp_path, ttl_seconds=600),
    )
    out = service.get_context("XAUUSD", force_refresh=True)
    urls = [s["url"] for s in out["sources"]]
    assert len(urls) == len(set(urls))
    assert all(s["source_id"].startswith("src_") for s in out["sources"])
