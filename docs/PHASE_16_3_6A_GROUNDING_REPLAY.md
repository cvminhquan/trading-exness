# Phase 16.3.6A — Grounding Replay & Provider Contract Hardening

## Why this phase exists

Real Gemini Google Search Grounding responses can include messy metadata:
chunks, redirect URLs, missing `published_at`, duplicates, unsafe schemes,
partial fields. Simple fake objects miss adapter bugs.

This phase builds an **offline** replay harness over realistic fixtures so the
production adapter + normalizer can be exercised without a live API key.

## What it verifies

- Grounding metadata → canonical sources (only)
- Model-written URLs without grounding are **not** treated as sources
- Missing `published_at` → `null` / freshness `UNDATED` (never fabricated)
- Duplicate / UTM variants collapse safely
- Unsafe URL schemes rejected
- Redirect-style grounding URLs preserved offline (no network resolve)
- Malformed / no-source responses degrade safely
- Deterministic source IDs
- Claim ↔ source mapping integrity
- ExternalContext / Synthesis / Analyst Chat replay contracts
- Bot-signal causality guard (external ≠ cause of `mtf_technical_v1`)
- Critical technical contradiction guards
- Cache fingerprint semantics (quote tick vs closed M15)
- Provider error categories + secret redaction

## What it does NOT verify

- Real Gemini availability
- Real Google Search Grounding
- Real citation provenance from live web
- Dashboard live AI behavior

**Offline replay PASS does not upgrade Phase 16.3.6 from BLOCKED.**

## Fixture contract

Location: `tests/fixtures/gemini_grounding/`

Each fixture:

```json
{
  "fixture_id": "...",
  "description": "...",
  "response": { "text": "...", "candidates": [...] },
  "expected": { ... }
}
```

Structural shape mirrors google.genai grounding metadata fields used by the
adapter (`candidates[0].grounding_metadata.grounding_chunks[].web`).

Synthetic text / example domains only — no copyrighted article bodies.

Technical snapshots: `tests/fixtures/technical_snapshots/` (cases A/B/C).

## Provider response contract

Shared module: `external_context/gemini_adapter.py`

- Live provider and offline replay call the same `adapt_gemini_grounded_response`
- Canonical sources come **only** from grounding chunks
- Claim/driver/event `source_urls` may reference grounded URLs; they cannot invent new ones
- Missing optional fields are tolerated; required malformed structures fail closed

## CLI

```bash
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.market_analysis.integration replay
.\.venv\Scripts\python.exe -m exness_bot.market_analysis.integration replay --fixture grounding_normal
```

Artifact: `data/integration/phase_16_3_6A_replay_report.json`

## Relationship to 16.3.6

| Layer | 16.3.6A | 16.3.6 |
|-------|---------|--------|
| Offline replay | YES | n/a |
| Real Google Grounding | NOT_RUN | required for PASS |
| Verdict impact on 16.3.6 | none | remains BLOCKED until real key smoke |

After local `GEMINI_API_KEY` is configured, return to Phase 16.3.6 real smoke.
Do not start 16.3.7.
