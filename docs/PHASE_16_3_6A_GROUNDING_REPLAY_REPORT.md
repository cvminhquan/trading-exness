# PHASE 16.3.6A — GROUNDING REPLAY & PROVIDER CONTRACT HARDENING

STATUS: **PASS**

## IMPORTANT

PHASE 16.3.6 REAL INTEGRATION STATUS: **BLOCKED**

REAL GOOGLE GROUNDING: **NOT_RUN**

REAL GEMINI SYNTHESIS: **NOT_RUN**

REAL ANALYST CHAT: **NOT_RUN**

Offline replay PASS **does not** upgrade 16.3.6.

## REPLAY

- fixture count: **9**
- fixture_set_hash: `91b9f7f84e41b658db76b997`
- network required: **NO**
- grounding normal: **PASS**
- missing metadata: **PASS**
- missing published_at: **PASS**
- duplicate sources: **PASS**
- redirect URLs: **PASS** (preserved offline; no resolve)
- unsafe URLs: **PASS**
- no sources: **PASS**
- malformed response: **PASS**

## SOURCE CONTRACT

- canonical source refs: **PASS**
- invented URLs: **ZERO** (model URLs without grounding blocked)
- stable IDs: **PASS**
- published_at fabrication: **NO**

## EXTERNAL

- replay normalization: **PASS**
- alignment: **PASS** (case A CONFLICT with bearish external)
- cache: **PASS** (hit on same fingerprint; quote tick stable; closed M15 changes)

## SYNTHESIS

- replay: **PASS**
- google_search: **ZERO**
- source validation: **PASS**
- fact protection: **PASS** (bot signal preserved)

## ANALYST CHAT

- replay: **PASS**
- bot causality: **PASS**
- source integrity: **PASS**
- execution claim guard: **PASS**
- context_changed: **PASS**

## ERROR HARDENING

- auth / 429 / timeout / model unavailable / network / malformed: **PASS** (classified)

## SECRET SAFETY

- fake secret leaked: **NO**
- artifact safe: **YES**
- logs safe: **YES** (categories, not raw secrets)

## TESTS

- new: `test_phase_16_3_6a_grounding_replay.py` (**24 passed**)
- backend regression (16.3.1–16.3.6 + 16.3.6A + 16.2.4A.2): **123 passed**
- frontend market-context: **11 passed**
- ruff: **PASS**
- mypy (touched packages): clean after lazy `__init__` typing

## FORWARD

cutoff / V2 freeze / metric fingerprint / hypotheses: **UNCHANGED** · contaminated: **NO**

## SAFETY

V1/V2/Execution/Phase17 unmodified · order_send **ZERO** · broker mutation **NO**

## ARTIFACTS

- docs: `docs/PHASE_16_3_6A_GROUNDING_REPLAY.md`
- fixtures: `tests/fixtures/gemini_grounding/` + `technical_snapshots/`
- package: `market_analysis/integration/replay/`
- shared adapter: `external_context/gemini_adapter.py`
- CLI: `python -m exness_bot.market_analysis.integration replay`
- JSON: `data/integration/phase_16_3_6A_replay_report.json`

## HARDENING NOTE

Adapter now treats **only** grounding-metadata URLs as canonical sources.
Model-emitted URLs without grounding no longer become sources (fixes
no-source / invented-URL contract).

## FINAL NOTE

Offline replay evidence must **not** be described as real Gemini grounding
verification. Phase 16.3.6 remains **BLOCKED** until a live key smoke succeeds.

## STOP

Do not start 16.3.7. Wait for local `GEMINI_API_KEY`, then return to 16.3.6.
