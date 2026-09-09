# PHASE 17.3 — AUTONOMOUS DEMO EXECUTION LOOP — REPORT

**Date:** 2026-09-09  
**Symbol / TF:** XAUUSD · M15  
**Scope:** Controlled DEMO autonomy only

---

## IMPLEMENTATION STATUS: PASS

## REAL DEMO EVIDENCE: PENDING

(Requires human-enabled DEMO profile + eligible live closed M15.)

---

## What shipped

| Component | Path |
|-----------|------|
| Loop | `execution/auto_demo/loop.py` |
| Decision store | `execution/auto_demo/decision_store.py` |
| Enablement | `execution/auto_demo/enablement.py` |
| Hot-read | `execution/auto_demo/hot_read.py` |
| Risk gates | `execution/auto_demo/risk_gates.py` |
| Factory | `execution/auto_demo/factory.py` |
| CLI | `python -m exness_bot.execution.auto_demo` |
| Status API | `GET /api/v1/execution/auto-demo/status` |
| Docs | `docs/AUTONOMOUS_DEMO_EXECUTION.md` |

### Gated port alignment

`GatedMT5ExecutionPort` / `build_gated_mt5_execution_port` accept:

- `enablement_evaluator` (auto-demo sticky approval, no one-shot guard)
- `settings_provider` (hot-read kill switch / flags)

### Settings

`AUTO_DEMO_EXECUTION_ENABLED=false` (default). Documented in `.env.example` (not enabled).

---

## AUTO DEMO

| Check | Result |
|-------|--------|
| default enabled | **NO** |
| runtime enabled | depends on operator `.env` (safe default false) |
| DEMO only gate | PASS |
| allowlist | enforced (empty → BLOCK) |
| kill switch | hot-read before side effect |
| account unknown env | BLOCK |

---

## TRIGGER

| Check | Result |
|-------|--------|
| M15 closed-candle | PASS |
| quote tick execution | ZERO |

---

## IDEMPOTENCY / LIFECYCLE

| Check | Result |
|-------|--------|
| same candle duplicate | ZERO (unit) |
| restart duplicate | ZERO (unit) |
| IN_FLIGHT before side effect | PASS (unit) |
| UNKNOWN auto-resubmit | ZERO (unit) |

---

## RISK

Unit coverage for daily loss, drawdown, open positions, spread, freshness/precheck path via CandidateExecutionService.

---

## EXECUTION

| Check | Result |
|-------|--------|
| ExecutionOrchestrator sole owner | YES |
| LiveMT5ExecutionTransport sole order_send | YES |
| new direct order_send in auto_demo | ZERO |

---

## AI / EXTERNAL

| Check | Result |
|-------|--------|
| external affects strategy | NO |
| synthesis affects strategy | NO |
| chat affects strategy | NO |

Static isolation scan in `test_phase_17_3_autonomous_demo_loop.py`.

---

## TESTS

- Phase 17.3: **23 passed**
- Broader regression: see command log in session

---

## FORWARD / RESEARCH

| Check | Result |
|-------|--------|
| cutoff changed | NO |
| V2 freeze changed | NO |
| hypotheses changed | NO |
| contaminated | NO |

---

## FINAL VERDICT

**PASS (implementation)** — autonomous DEMO loop is default-off, fail-closed, idempotent, reuses canonical execution stack.

**REAL DEMO EVIDENCE: PENDING** until an operator-enabled eligible closed-M15 event is observed on an allowlisted DEMO account.
