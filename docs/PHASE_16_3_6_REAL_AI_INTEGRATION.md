# Phase 16.3.6 — Real External / AI Integration Smoke & Hardening

## Purpose

Validate the **complete real** read-only pipeline:

TechnicalMarketSnapshot → Gemini Google Search Grounding → ExternalMarketContext
→ MarketSynthesis → AI Market Analyst Chat → Dashboard

This phase is integration / validation / observability / hardening — **not**
strategy tuning or execution.

## Preflight

```bash
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.market_analysis.integration preflight
```

Reports (never prints the key value):

- `gemini_api_key_configured`
- feature flags (external / synthesis / chat)
- provider + model names
- technical snapshot availability
- cache/session store writability
- `real_smoke_ready` / `block_reason`

## Local configuration

Repository defaults stay **OFF** in `.env.example`.

For a **local-only** smoke, operator configures:

1. `GEMINI_API_KEY` in `trading-engine/.env` (gitignored)
2. Temporarily enable:
   - `EXTERNAL_INTELLIGENCE_ENABLED=true`
   - `AI_MARKET_SYNTHESIS_ENABLED=true`
   - `AI_MARKET_ANALYST_CHAT_ENABLED=true`
3. Do **not** commit local enabled state or the key

Then:

```bash
.\.venv\Scripts\python.exe -m exness_bot.market_analysis.integration smoke
```

If key missing:

```
REAL INTEGRATION: BLOCKED — GEMINI_API_KEY NOT CONFIGURED
```

## Secret safety

- `.env` is gitignored
- Key must never appear in reports, artifacts, logs, or frontend
- Browser talks only to backend API

## Grounding / citation / freshness

Covered by Phase 16.3.2 design + this phase’s real smoke when unblocked.
Invented URLs are rejected. `published_at` must not be fabricated.

## Cache behavior

In-process metrics:

- `external_provider_calls` / `external_cache_hits`
- `synthesis_provider_calls` / `synthesis_cache_hits`
- `analyst_chat_provider_calls` / `analyst_chat_fallbacks`

Smoke expects: force refresh → provider call; second get → cache hit.

## Synthesis / chat validation

- Synthesis Gemini: **no** `google_search` tool
- Analyst Chat Gemini: **no** `google_search` tool
- Bot-signal causality: external must not be described as causing V1 signal
- Execution / leverage prompts: read-only refusal

## Failure behavior

Fake/mocked coverage remains in 16.3.2–16.3.5 tests (timeout, malformed,
invalid sources, invented URLs). Do not spam live Gemini for 429.

## Known limitations

- Real smoke is **BLOCKED** until `GEMINI_API_KEY` is configured locally
- Closed-M15 invalidation and quote-tick observation may be `NOT_OBSERVED`
  in a short smoke window (unit tests cover fingerprint/cache semantics)
- Real Google grounding for 16.3.2 was also NOT_RUN for the same reason

## Final verdict rule

| Condition | Verdict |
|-----------|---------|
| Key missing | **BLOCKED** |
| Real pipeline verified, no material defects | **PASS** |
| Works with non-critical limitation | **CONDITIONAL** |
| Real provider ran but safety/correctness failed | **FAIL** |

Unit-test PASS ≠ REAL INTEGRATION PASS.
