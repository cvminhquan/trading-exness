# Phase 12.7 Report — Real DEMO One-Shot Evidence & Reconciliation

**Date:** 2026-09-04  
**Scope:** Harden controlled DEMO one-shot evidence path; operator runbook; Fake tests. Agent does **not** run `--execute`.  
**Status: CONDITIONAL**

---

## 1. Overall status

```text
CONDITIONAL

Implementation: PASS
Real DEMO broker submission: NOT TESTED
```

```text
AUTONOMOUS LIVE TRADING: NOT IMPLEMENTED
PRODUCTION EXECUTION: NOT ENABLED
STRATEGY → MT5 EXECUTOR: NOT WIRED
```

---

## 2. Preflight evidence (read-only, agent-run)

Command (no `--execute`):

```text
exness-bot demo-execution-smoke
```

| Check | Result |
|-------|--------|
| MT5 connection | PASS |
| Masked login | `***4158` |
| Server | `Exness-MT5Trial17` |
| `trade_mode` | **demo** (authoritative) |
| Symbol map | `XAUUSD` → `XAUUSDm` |
| Quote bid/ask | Present |
| Quote freshness | **QUOTE: BLOCKED — STALE** |
| Terminal trade | **BLOCKED** (`trade_allowed=false`) |
| Allowlist | BLOCKED (empty) |
| Kill switch / approval / env | BLOCKED (safe defaults) |
| Overall | **BLOCKED** — **no `order_send`** |

---

## 3. DEMO verification

Connected account `trade_mode=demo` independently verified (not inferred from `TRADING_ENV` alone).  
Gate `ACCOUNT_TRADE_MODE` + preflight `account_trade_mode` enforced.

---

## 4. Operator gate evidence

| Gate | Enforcement |
|------|-------------|
| `LIVE_KILL_SWITCH` | Default true → BLOCK |
| `LIVE_DEMO_APPROVAL` | Default false → BLOCK |
| `--confirm DEMO-EXECUTE` | Exact phrase required |
| Preflight must PASS before `--execute` | CLI hard-return if not PASS |
| `DEMO_ACCOUNT_ALLOWLIST` | Required; no auto-fill |
| Terminal Algo Trading | `TERMINAL_TRADE_PERMISSION` gate |

---

## 5. One-shot execution evidence

| Item | Status |
|------|--------|
| Fake: IN_FLIGHT before send | AUTOMATED PASS |
| Fake: exactly one transport call | AUTOMATED PASS |
| Real DEMO `order_send` | **NOT TESTED** (agent forbidden; operator pending) |

---

## 6–8. Broker response / verification / reconciliation

Implementation present (`BrokerSmokeEvidence`, `BrokerExecutionQuery`, sanitize).  
Real broker response / independent verify / reconcile: **NOT TESTED**.

Mapping retained:

```text
CONFIRMED_FILLED → FILLED
CONFIRMED_REJECTED → REJECTED
NOT_FOUND|AMBIGUOUS|UNAVAILABLE → UNKNOWN
```

---

## 9. UNKNOWN behavior

```text
EXECUTION STATE: UNKNOWN
ACTION REQUIRED: READ-ONLY BROKER RECONCILIATION
AUTOMATIC RESUBMISSION: DISABLED
```

Printed/logged on UNKNOWN. No automatic retry.

---

## 10. Position handling

Open positions: **never auto-closed**. Evidence carries:

```text
Position remains open and requires separate explicit operator action.
```

---

## 11–12. Duplicate / restart

Ledger + idempotency: second smoke BLOCKED (`calls==[]`) — AUTOMATED PASS.  
Restart / UNKNOWN recovery — covered by Phase 12.5/12.6 + 12.7 Fake tests.

---

## 13. Automated test results

| Gate | Result |
|------|--------|
| pytest | **720 passed**, 5 skipped, 1 deselected |
| ruff | PASS |
| mypy | PASS |

New: `tests/unit/test_phase_12_7_demo_evidence.py`

---

## 14. Static safety audit

- `order_send` remains in `LiveMT5ExecutionTransport` only (Phase 12 path)
- Strategy / candle / risk / execution orchestration: no MetaTrader5 imports
- Factory does not wire `MT5Executor` / Live transport
- No Dashboard/API trade controls added

---

## 15. Safe defaults

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
ALLOW_LEGACY_RUN=false
```

Unchanged in repository Settings / `.env.example`.

---

## 16. Remaining risks

1. Real DEMO one-shot still operator-gated and not executed this session.  
2. Market/session may leave quotes STALE; terminal Algo Trading may be off.  
3. Multi-process ledger is single-host JSON (documented).  
4. Phase 12.5 CONDITIONAL remains until human smoke + sanitized evidence.

---

## 17. Changed files

- `controlled_demo/enablement.py` — terminal trade gate; QUOTE FRESH/STALE labels  
- `controlled_demo/preflight.py` — terminal BLOCK when trade_allowed=false  
- `controlled_demo/evidence.py` — quote fields, sanitize, open-position policy  
- `controlled_demo/smoke.py` — context fields; UNKNOWN procedure print  
- `cli.py` — `--execute` requires preflight PASS  
- `tests/unit/test_phase_12_7_demo_evidence.py`  
- `tests/unit/test_phase_12_4_demo_smoke.py` — trade_allowed on contexts  
- `docs/DEMO_EXECUTION_SMOKE_RUNBOOK.md`  
- `docs/evidence/phase-12-7/*`  
- `docs/PHASE_12_7_REPORT.md`  
- `docs/LIVE_EXECUTION_ARCHITECTURE.md`

---

## 18. Phase 12.8 recommendation

```text
DO NOT BEGIN Phase 12.8 AUTOMATICALLY
```

Next human steps (optional):

1. Follow [`DEMO_EXECUTION_SMOKE_RUNBOOK.md`](DEMO_EXECUTION_SMOKE_RUNBOOK.md)  
2. Enable Algo Trading; wait for FRESH quote; set local demo gates  
3. Run **one** `--execute --confirm DEMO-EXECUTE`  
4. File sanitized evidence under `docs/evidence/phase-12-7/`  
5. Restore safe defaults  

Only then may overall status become **PASS**.

Until then:

```text
Implementation: PASS
Real DEMO broker submission: NOT TESTED
Overall: CONDITIONAL
```
