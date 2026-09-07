# PHASE 12.10 — DEMO EXECUTION EVIDENCE & RECONCILIATION

**Date:** 2026-09-07  
**Scope:** DEMO-only lifecycle validation, reconciliation audit, operator evidence template.  
**Does NOT enable autonomous live trading.**

---

## 1. Objective

Prove that **one** controlled DEMO execution can safely move through:

```text
CREATED → IN_FLIGHT → FILLED | REJECTED | UNKNOWN
```

using the Phase 12.9 canonical path, then be reconciled **read-only**.

This phase does **not** claim a real broker fill unless a human operator provides evidence.

---

## 2. Preconditions

| Item | Required |
|------|----------|
| Architecture from Phase 12.9 | Present |
| `CONTROLLED_DEMO_TEST_VOLUME=0.01` | Present |
| Safe defaults in repo | `LIVE_KILL_SWITCH=true`, `LIVE_DEMO_APPROVAL=false`, `EXECUTION_MODE=paper`, `ALLOW_LEGACY_RUN=false` |
| Operator DEMO overrides | Local only — never committed |
| Agent `--execute` | **Forbidden** |

Deterministic intent after gates:

```text
SIDE=BUY
VOLUME=0.01
SYMBOL=XAUUSD
BROKER_SYMBOL=XAUUSDm
```

---

## 3. Architecture

```text
demo-execution-smoke
        ↓
ExecutionOrchestrator
        ↓
GatedMT5ExecutionPort   ← evaluate_demo_controlled_enablement
        ↓
MT5Executor
        ↓
OneShotExecutionTransport
        ↓
LiveMT5ExecutionTransport   ← only Phase-12 order_send boundary
        ↓
MT5 order_send()
```

### Architecture audit (Task 1)

| Check | Result |
|-------|--------|
| Demo-only gates (`TRADING_ENV=demo`, trade_mode) | PASS |
| Account / server allowlist | PASS |
| Symbol mapping (`XAUUSD`→`XAUUSDm`) | PASS |
| Quote freshness | PASS |
| Spread limit (`MAX_SPREAD_POINTS`) | PASS — **restored** as `DemoGateName.SPREAD_LIMIT` (gap after 12.9 removed RiskManager from smoke) |
| Volume validation (0.01 explicit) | PASS |
| Operator approval | PASS |
| One-shot guard (ledger + transport) | PASS |
| Durable intent store | PASS |
| IN_FLIGHT before side effect | PASS |
| UNKNOWN handling / no auto-retry | PASS |
| Broker reconciliation read-only | PASS (`ReadOnlyMt5BrokerExecutionQuery`) |
| Legacy isolation | PASS |
| Strategy loop isolation | PASS |

**Defect fixed in this phase:** controlled DEMO enablement no longer enforced `MAX_SPREAD_POINTS` after Phase 12.9 bypassed RiskManager sizing. Added fail-closed `spread_limit` gate + preflight check. Architecture otherwise unchanged.

---

## 4. Operator execution

**Status:** **NOT PERFORMED BY AGENT**

Human-only command:

```bash
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

Follow [`DEMO_EXECUTION_SMOKE_RUNBOOK.md`](DEMO_EXECUTION_SMOKE_RUNBOOK.md) steps 1–11.

Agent may only:

```bash
exness-bot demo-execution-smoke --help
exness-bot demo-execution-smoke          # read-only preflight when MT5 available
```

---

## 5. Broker response

| Source | Status |
|--------|--------|
| Fake / unit transport evidence | Covered by tests (FILLED / REJECTED / UNKNOWN) |
| Real MT5 `order_send` response | **AWAITING OPERATOR** — not claimed |

Do not invent tickets, deals, or fill prices.

---

## 6. Lifecycle result

### Expected mapping

| Broker / transport outcome | Lifecycle |
|----------------------------|-----------|
| Confirmed success | `FILLED` |
| Confirmed rejection | `REJECTED` |
| Ambiguous / unavailable / not found / finalize fail after side effect | `UNKNOWN` |

### Pre-submit persistence

`ExecutionOrchestrator` persists `CREATED → IN_FLIGHT` **before** `port.submit` / transport send.

IN_FLIGHT record includes reconciliable fields:

- intent id  
- idempotency key  
- symbol  
- side  
- volume (`requested_quantity`)  
- timestamps  
- lifecycle state  

Verified by Fake failure-injection / smoke tests (not by a real broker send in this phase).

---

## 7. Reconciliation result

| Capability | Status |
|------------|--------|
| Read-only MT5 query (`ReadOnlyMt5BrokerExecutionQuery`) | Implemented — no `order_send` |
| Match intent → deal/order evidence | Implemented |
| `CONFIRMED_FILLED` / `CONFIRMED_REJECTED` / stay `UNKNOWN` | Covered in Phase 12.5/12.7 tests |
| Auto-close open position | **DISABLED** — explicit human action required |
| Real DEMO reconcile after operator fill | **AWAITING OPERATOR** |

---

## 8. One-shot proof

| Layer | Evidence |
|-------|----------|
| `OneShotExecutionTransport` | Second `send` → `ONE_SHOT_VIOLATION`, no inner call |
| Smoke ledger | Second `--execute` blocked |
| Orchestrator idempotency | Duplicate plan → `port_calls=0` |
| Strategy loop | Not invoked from controlled_demo |

Fake-path proof: `transport_send_count <= 1`.

Real-path one-shot proof: **AWAITING OPERATOR** terminal capture.

---

## 9. Failure handling

Fake-only failure scenarios (Task 7) — **no real broker injection**:

| ID | Scenario | Expected | Test |
|----|----------|----------|------|
| A | Broker REJECTED | `REJECTED` | `test_phase_12_10` A |
| B | Ambiguous response | `UNKNOWN` | B |
| C | Persistence failure after side effect | `UNKNOWN`, no resend | C |
| D | Restart with unresolved intent | BLOCK | D |
| E | Duplicate plan | BLOCK / zero second port calls | E |
| F | Second smoke submission | BLOCK via ledger | F |

`UNKNOWN` never auto-resubmits.

---

## 10. Safety audit

| Item | Result |
|------|--------|
| pytest | See § Test results |
| ruff | See § Test results |
| mypy | See § Test results |
| Phase-12 `order_send` boundary | `LiveMT5ExecutionTransport` only |
| Legacy `order_send` | Isolated (`ALLOW_LEGACY_RUN=false`) |
| Safe defaults unchanged | PASS |
| Credentials not in source / not logged | PASS |
| Agent did not run `--execute` | PASS |

### Test results

| Gate | Result |
|------|--------|
| pytest | **792 passed**, 1 deselected |
| ruff check src tests | **PASS** |
| mypy src | **PASS** (168 source files) |
| `exness-bot demo-execution-smoke --help` | **PASS** |
| Real `--execute` | **NOT RUN** (operator-only) |

---

## 11. Remaining risks

1. Real DEMO fill / reconcile evidence still requires a human operator.
2. Multi-process exactly-once is not guaranteed.
3. Open DEMO positions after a fill still need explicit human close/management.
4. Operator must restore kill switch / approval after the one-shot.
5. Spread gate depends on accurate symbol.spread / bid-ask metadata from the broker.

---

## 12. Final result

```text
PHASE 12.10 IMPLEMENTATION RESULT:
CONDITIONAL — AWAITING OPERATOR DEMO EVIDENCE
```

**Why CONDITIONAL (not FAIL):**

- Controlled DEMO path, gates (including restored spread limit), lifecycle, UNKNOWN, one-shot, and Fake failure scenarios are implemented and tested.
- Architecture audit PASS with one concrete defect fixed (spread gate).
- Reconciliation is read-only and tested with Fake/query doubles.
- Real broker `--execute` was **not** run by the agent; no sanitized operator evidence was provided in this session.

**Why not PASS:**

- Broker response, real lifecycle fill, and live reconciliation sections remain **AWAITING OPERATOR**.

---

## Operator next steps

1. Follow [`DEMO_EXECUTION_SMOKE_RUNBOOK.md`](DEMO_EXECUTION_SMOKE_RUNBOOK.md).  
2. Run **one** human `--execute --confirm DEMO-EXECUTE`.  
3. Capture sanitized output under [`evidence/phase-12-10/`](evidence/phase-12-10/).  
4. Read-only reconcile; do not resubmit UNKNOWN; do not auto-close.  
5. Restore safe defaults.  
6. Update this document’s §§4–7 with operator evidence to promote result to **PASS**.
