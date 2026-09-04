# Phase 12.4 Report — Controlled Demo Execution

**Date:** 2026-08-29  
**Scope:** ONE explicitly controlled MT5 DEMO order path (CLI one-shot). No strategy loop.  
**Status: CONDITIONAL**

---

## Status

```text
CONDITIONAL
```

| Label | Meaning |
|-------|---------|
| **PASS** | Demo enablement gates, one-shot approval, IN_FLIGHT-before-send, OneShot transport, Fake-transport tests, CLI wired, quality gates |
| **CONDITIONAL** | Real broker DEMO smoke not run in this session (environment / operator confirmation required) |
| **NOT IMPLEMENTED** | Autonomous live trading; strategy→MT5 loop; Dashboard trade controls |
| **NOT TESTED** | Manual MT5 DEMO `order_send` against Exness (intentionally not fabricated) |
| **BLOCKED** | Production/live/real `TRADING_ENV`; kill switch default; missing approval |

---

## Live / demo execution

```text
CONTROLLED DEMO PATH: IMPLEMENTED
AUTONOMOUS TRADING: DISABLED
REAL-MONEY: BLOCKED
MANUAL DEMO SMOKE THIS SESSION: NOT TESTED
```

---

## Architecture

```text
Operator approval (LIVE_DEMO_APPROVAL + --confirm DEMO-EXECUTE)
    ↓
Demo enablement gates (TRADING_ENV=demo only)
    ↓
Read-only identity / symbol / quote verification
    ↓
RiskManager (controlled intent — not SignalEngine)
    ↓
DurableIntentStore: IN_FLIGHT
    ↓
MT5Executor (enablement recheck)
    ↓
OneShotExecutionTransport (max 1 send)
    ↓
LiveMT5ExecutionTransport   [only with --execute]
    ↓
MT5 DEMO broker
    ↓
ExecutionAck → FILLED | REJECTED | UNKNOWN
    ↓
Read-only reconciliation (no resubmit)
    ↓
Exit (no poll loop)
```

CLI:

```text
exness-bot demo-execution-smoke
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

Without `--execute`: preflight / probe only — **no** broker mutation.

---

## Automated proof

| Check | Result |
|-------|--------|
| TRADING_ENV=demo required | PASS |
| live/production/real rejected | PASS |
| Kill switch blocks | PASS |
| Approval required + one-shot | PASS |
| Executor cannot bypass gates | PASS |
| Stale/invalid quote blocks | PASS |
| Missing stops / invalid volume | PASS |
| IN_FLIGHT before transport | PASS |
| Transport exactly once | PASS |
| FILLED / REJECTED / TIMEOUT / PARTIAL | PASS |
| UNKNOWN no retry; reconcile read-only | PASS |
| Second submission blocked (ledger) | PASS |
| No SignalEngine / no strategy loop | PASS |
| Legacy path unused | PASS |
| Paper unchanged | PASS |

```text
pytest (phase 12.4 file): 33 passed
```

---

## Manual demo evidence

```text
NOT TESTED
```

No Exness DEMO `order_send` was executed in this implementation session.  
Do **not** treat unit tests as proof of real broker execution.

To run manually (operator only):

1. `TRADING_ENV=demo`
2. `LIVE_KILL_SWITCH=false` (temporary)
3. `LIVE_DEMO_APPROVAL=true`
4. `DEMO_ACCOUNT_ALLOWLIST=<demo login>`
5. Explicit `LIVE_SYMBOL_MAP`
6. MT5 demo terminal connected
7. `exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE`
8. Restore `LIVE_KILL_SWITCH=true`, `LIVE_DEMO_APPROVAL=false`

---

## Broker evidence

```text
NOT TESTED (no real submission this session)
```

---

## Partial fills / UNKNOWN

Unchanged from Phase 12.3: PARTIAL → UNKNOWN; no auto-retry; reconcile read-only only.

---

## Position handling

If a DEMO position remains open after a real smoke: **not auto-closed**.  
Report must list ticket/volume/SL/TP. Close requires separate explicit approval (not implemented as autonomy).

---

## Quality gates

```text
pytest: 668 passed, 5 skipped
ruff: clean
mypy: clean (152 source files)
dashboard: NOT CHANGED
```

---

## Static safety audit

### Allowed

- `broker/mt5/execution_transport.py` — `order_send` in Live transport only  
- `broker/mt5/executor.py` — request build  
- `controlled_demo/` — orchestration (no direct `order_send`)  
- CLI `demo-execution-smoke` wires Live transport only under `--execute`

### Forbidden (Phase 11 packages)

- `candle_engine`, `signal_engine`, `risk`, `paper_execution` — no trading mutation API

### Legacy isolated

- `adapter.py` / `OrderManager` / `exness-bot run` — not used by Phase 12.4 path

---

## Post-smoke safety (repository defaults)

- `LIVE_KILL_SWITCH` default **true**
- `LIVE_DEMO_APPROVAL` default **false**
- `EXECUTION_MODE` default **paper**
- `ALLOW_LEGACY_RUN` default **false**
- No live worker / strategy loop added
- Ledger path `.demo_smoke_ledger.json` blocks a second controlled submit

---

## Known limitations

1. Manual DEMO broker smoke **NOT TESTED** here.  
2. Preflight without MT5 connection exits non-zero (Windows + terminal required for CLI probe).  
3. Open DEMO positions are not auto-closed.  
4. Approval consume is process + ledger; operator must reset env flags after smoke.

---

## Phase 12.5 readiness

Do **not** start automatically.

Before any next phase: complete a real DEMO smoke with evidence, operator runbook for UNKNOWN, and explicit decision on whether autonomous paper→live wiring is ever allowed.
