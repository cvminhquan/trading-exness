# Phase 12.3 Report — MT5Executor Implementation (Execution Boundary Only)

**Date:** 2026-08-29  
**Scope:** `MT5Executor` + `MT5ExecutionTransport` boundary. Fail-closed enablement. No autonomous live trading.  
**Status: CONDITIONAL**

---

## Status

```text
CONDITIONAL
```

| Label | Meaning |
|-------|---------|
| **PASS** | `MT5Executor` implements `ExecutionPort`; Fake transport tests; gates enforced; UNKNOWN no retry; paper unchanged; quality gates |
| **CONDITIONAL** | Executor exists but **DISABLED** by default; not wired into `build_execution_service` / strategy loop |
| **NOT IMPLEMENTED** | Autonomous live trading loop; demo/real smoke `order_send`; production live activation |
| **NOT TESTED** | Real Exness demo/live `order_send` (intentionally forbidden in this phase) |
| **BLOCKED** | Controlled demo/live activation until separate approval (Phase 12.4+) |

---

## Live execution

```text
IMPLEMENTED BUT DISABLED
```

- `MT5_EXECUTOR_IMPLEMENTED = True` (capability gate)
- Defaults: `LIVE_KILL_SWITCH=true`, `ALLOW_LIVE_TRADING=false`, `EXECUTION_MODE=paper`
- `build_execution_service` still refuses `EXECUTION_MODE=live`
- No Dashboard trading controls
- Unit tests use `FakeMT5ExecutionTransport` only

---

## Architecture

```text
ExecutionIntent
    ↓
DurableIntentStore (IN_FLIGHT before submit)
    ↓
LiveEnablementGate (fail-closed)
    ↓
MT5Executor
    ↓
MT5ExecutionTransport
    ├── FakeMT5ExecutionTransport  [tests]
    └── LiveMT5ExecutionTransport  [production boundary — not auto-wired]
    ↓
Broker (NOT exercised in Phase 12.3 validation)
```

Paper path unchanged:

```text
ExecutionService → PaperExecutor → Virtual Position
```

---

## Responsibilities

| Component | Owns | Does not own |
|-----------|------|--------------|
| `MT5Executor` | quote/volume/stops/symbol validation, request build, transport send, Ack mapping | strategy, risk, idempotency policy, UNKNOWN recovery, retries |
| `ExecutionService` | CREATED→IN_FLIGHT before `port.submit`, lifecycle finalize | MT5 mutation |
| `LiveEnablement` | multi-gate allow/deny | order submission |

---

## Broker result mapping

| Transport outcome | AckStatus |
|-------------------|-----------|
| FILLED (price+volume confirmed, full volume) | FILLED |
| REJECTED (definite retcode) | REJECTED |
| TIMEOUT | TIMEOUT → lifecycle UNKNOWN |
| PARTIAL / volume mismatch | UNKNOWN (`PARTIAL_FILL_UNSUPPORTED`) |
| None / ambiguous retcode | UNKNOWN |

**No automatic retry** after UNKNOWN / TIMEOUT / PARTIAL.

---

## Partial fills

Policy: **UNSUPPORTED as FILLED**. Map to `AckStatus.UNKNOWN` with reason `PARTIAL_FILL_UNSUPPORTED` / volume mismatch. Do not invent a full fill. Reconciliation remains read-only.

---

## UNKNOWN handling

1. Transport ambiguity → `ExecutionAck(UNKNOWN|TIMEOUT)`  
2. Persist `IntentLifecycle.UNKNOWN` (no resubmit)  
3. `BrokerExecutionQuery` may reconcile later (read-only)  
4. Unresolved UNKNOWN blocks live enablement gates  

---

## Tests

```text
pytest: 635 passed, 5 skipped
ruff: (run after fixes)
mypy: clean (144 source files)
dashboard: NOT CHANGED
```

---

## Broker execution

```text
REAL BROKER ORDER SUBMISSION DURING VALIDATION: NO
```

---

## Static safety audit

### Allowed (Phase 12 path)

| Location | Tokens |
|----------|--------|
| `broker/mt5/executor.py` | `TRADE_ACTION_DEAL` via mapper constants in request payload |
| `broker/mt5/execution_transport.py` | `order_send` only in `LiveMT5ExecutionTransport.send` |

### Forbidden packages (no live trading API)

- `candle_engine`, `signal_engine`, `risk`, `paper_execution`, `config/live_enablement.py`
- `api/services` read paths

### Legacy (isolated)

- `broker/mt5/adapter.py` — existing `order_send` (OrderManager path)
- `orders/order_manager.py` — gated by `ALLOW_LEGACY_RUN`

---

## Known limitations

1. `LiveMT5ExecutionTransport` is not wired into any CLI/API/runtime loop.  
2. Symbol map must be explicit (`LIVE_SYMBOL_MAP` / `MT5_SYMBOL`); no fuzzy guess at submit time.  
3. Partial fills cannot be represented as safe FILLED under current `ExecutionAck` contract.  
4. Enablement `allowed=True` only means gates pass — **not** that autonomous trading is active.

---

## Phase 12.4 readiness

Do **not** start automatically. Before any controlled demo/live execution:

1. Explicit operator approval + runbook  
2. Wire `LiveMT5ExecutionTransport` only behind all gates + kill switch  
3. Demo account smoke with separate approval (still no strategy loop until approved)  
4. Operator playbook for UNKNOWN after `NOT_FOUND`  
5. Confirm identity allowlist against live terminal  

**Không** tự bắt đầu Phase 12.4.
