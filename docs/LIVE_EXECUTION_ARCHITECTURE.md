# Live Execution Architecture & Safety Design

**Cập nhật:** Phase 12.10 (DEMO Execution Evidence & Reconciliation) — 2026-09-07.

Nhãn: **CURRENT** | **DESIGN** | **FUTURE** | **NOT IMPLEMENTED**.

---

## Phase 12.10 — DEMO Evidence & Reconciliation (CURRENT)

Chi tiết: [`PHASE_12_10_DEMO_EXECUTION_EVIDENCE.md`](PHASE_12_10_DEMO_EXECUTION_EVIDENCE.md)

### Status

```text
CONDITIONAL — AWAITING OPERATOR DEMO EVIDENCE
Phase 12.10 DOES NOT ENABLE AUTONOMOUS LIVE TRADING.
Agent MUST NOT run demo-execution-smoke --execute.
```

### Proof targets

```text
CREATED → IN_FLIGHT → FILLED | REJECTED | UNKNOWN
transport_send_count <= 1
read-only reconciliation only
no auto-close / no UNKNOWN retry
```

---

## Phase 12.9 — Controlled DEMO Path Hardening (CURRENT)

Chi tiết: [`PHASE_12_9_CONTROLLED_DEMO_EXECUTION_HARDENING.md`](PHASE_12_9_CONTROLLED_DEMO_EXECUTION_HARDENING.md)

### Status

```text
PASS (implementation + tests; real DEMO --execute is operator-only, not claimed here)
Phase 12.9 DOES NOT ENABLE AUTONOMOUS LIVE TRADING.
```

### Canonical DEMO smoke path

```text
demo-execution-smoke
    ↓
ExecutionOrchestrator
    ↓
GatedMT5ExecutionPort   ← evaluate_demo_controlled_enablement (reuse)
    ↓
MT5Executor
    ↓
OneShotExecutionTransport
    ↓
Fake | LiveMT5ExecutionTransport
```

Controlled DEMO volume is explicit:

```text
CONTROLLED_DEMO_TEST_VOLUME = 0.01
```

Not derived from RiskManager / strategy equity sizing.

---

## Phase 12.8 — Gated MT5 Execution Integration (CURRENT)

Chi tiết: [`PHASE_12_8_REPORT.md`](PHASE_12_8_REPORT.md)

### Status

```text
PASS
Phase 12.8 DOES NOT ENABLE AUTONOMOUS LIVE TRADING.
```

### Composition

```text
ExecutionOrchestrator
    ↓
GatedMT5ExecutionPort   ← evaluate_demo_controlled_enablement (reuse)
    ↓
MT5Executor
    ↓
OneShotExecutionTransport
    ↓
Fake | LiveMT5ExecutionTransport
```

Default:

```text
build_execution_service → Paper only
```

Explicit only:

```text
build_gated_mt5_execution_port(settings, transport=..., snapshot_provider=...)
```

---

## Phase 12.7 — Real DEMO One-Shot Evidence (CURRENT)


Chi tiết: [`PHASE_12_7_REPORT.md`](PHASE_12_7_REPORT.md) · Runbook: [`DEMO_EXECUTION_SMOKE_RUNBOOK.md`](DEMO_EXECUTION_SMOKE_RUNBOOK.md)

### Status

```text
CONDITIONAL
Implementation: PASS
Real DEMO order_send: NOT TESTED (human operator only)
```

### Contract

```text
Operator approval → Preflight PASS → IN_FLIGHT → ONE order_send
→ broker response → read-only verify → reconcile → exit
NO RETRY · NO AUTO-CLOSE · DEMO ONLY
```

Agent may run read-only `demo-execution-smoke` only — **never** `--execute`.

---

## Phase 12.6 — Execution Orchestration Hardening (CURRENT)


Chi tiết: [`PHASE_12_6_REPORT.md`](PHASE_12_6_REPORT.md).

### Pipeline

```text
ClosedCandle / SignalResult
       ↓
RiskManager → ApprovedOrderPlan
       ↓
ExecutionPlan (broker-neutral)
       ↓
ExecutionOrchestrator
       ↓
DurableIntentStore (CREATED → IN_FLIGHT)
       ↓
ExecutionPort.submit (exactly once)
       ↓
FILLED | REJECTED | UNKNOWN
```

```text
                         ┌─ Paper/Fake ExecutionPort ✅
ExecutionOrchestrator ───┤
                         └─ MT5Executor ❌ NOT WIRED
```

### Guarantees

- IN_FLIGHT durable **before** side effect  
- Deterministic idempotency key  
- CATCH_UP / REPLAY → BLOCKED  
- Unresolved UNKNOWN blocks **new** plans (global, single-process)  
- No automatic UNKNOWN retry  
- CLI: `exness-bot execution-orchestration-smoke` (Fake only)

### Status

```text
EXECUTION ORCHESTRATION VALIDATED
REAL MT5 EXECUTION STILL OPERATOR-ONLY
AUTONOMOUS BROKER WIRING NOT IMPLEMENTED
```

---

## Phase 12.5 — Real MT5 DEMO Smoke & Recovery (CURRENT)


Chi tiết: [`PHASE_12_5_REPORT.md`](PHASE_12_5_REPORT.md).

### Mục tiêu

Chứng minh boundary Phase 12.4 trên tài khoản MT5 DEMO thật (operator-controlled), cộng recovery UNKNOWN bằng Fake transport. **Không** autonomous trading.

### Trạng thái session

```text
OVERALL: CONDITIONAL
REAL DEMO order_send: NOT TESTED (gates fail-closed)
READ-ONLY identity on connected DEMO: PASS (masked login, server, trade_mode=demo)
UNKNOWN recovery (Fake): PASS
Second smoke / ledger: PASS (no second transport.send)
```

### Preflight (read-only)

```text
exness-bot demo-execution-smoke
```

Structured checks: PASS | BLOCKED | FAIL | NOT_TESTED. Never calls `order_send`.

### Controlled submit (operator only)

```text
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

Requires: `TRADING_ENV=demo`, kill switch off, `LIVE_DEMO_APPROVAL=true`, allowlist, fresh quote, empty ledger. Max one broker submission.

### Recovery policy

```text
IN_FLIGHT → UNKNOWN → restart → BrokerExecutionQuery
  CONFIRMED_FILLED   → FILLED
  CONFIRMED_REJECTED → REJECTED
  NOT_FOUND|AMBIGUOUS|UNAVAILABLE → UNKNOWN
NO RESUBMIT
```

Open positions after FILLED: **no auto-close** — operator action riêng.

### Defaults after smoke

```text
LIVE_KILL_SWITCH=true
LIVE_DEMO_APPROVAL=false
EXECUTION_MODE=paper
ALLOW_LEGACY_RUN=false
```

---

## Phase 12.4 — Controlled DEMO Execution (CURRENT)


Chi tiết: [`PHASE_12_4_REPORT.md`](PHASE_12_4_REPORT.md).

### Mục tiêu

Một lệnh DEMO được operator approve tường minh — **không** strategy loop, **không** tiền thật.

```text
exness-bot demo-execution-smoke
exness-bot demo-execution-smoke --execute --confirm DEMO-EXECUTE
```

### Pipeline

```text
LIVE_DEMO_APPROVAL + --confirm DEMO-EXECUTE
    ↓
Demo enablement (TRADING_ENV=demo only; reject live/production/real)
    ↓
Read-only identity / symbol / quote
    ↓
RiskManager (controlled intent — not SignalEngine)
    ↓
IN_FLIGHT → MT5Executor → OneShotTransport → LiveMT5ExecutionTransport
    ↓
Ack → durable finalize → read-only reconcile → exit
```

### Hard rules

- `TRADING_ENV=demo` bắt buộc; `trade_mode=demo` từ broker
- Kill switch mặc định true; approval one-shot
- Max 1 `transport.send`; UNKNOWN không retry
- Không Dashboard BUY/SELL; không `exness-bot run`
- Manual DEMO smoke: **NOT TESTED** trừ khi operator chạy thật

---

## Phase 12.3 — MT5Executor (CURRENT — DISABLED BY DEFAULT)

Chi tiết: [`PHASE_12_3_REPORT.md`](PHASE_12_3_REPORT.md).

### Pipeline

```text
MT5 Read-only → CandleEngine → SignalEngine → ExecutionService
    → RiskManager → DurableIntentStore → LiveEnablementGates
        → ExecutionPort
            ├── PaperExecutor          [CURRENT — default runtime]
            └── MT5Executor            [CURRENT — boundary only, DISABLED]
                    → MT5ExecutionTransport
                        ├── Fake (tests)
                        └── Live (order_send) — NOT auto-wired
```

### Executor responsibilities

- Validate quote, volume, stops/freeze, SL/TP geometry
- Explicit canonical → broker symbol map (`LIVE_SYMBOL_MAP`)
- Normalize price to tick/point; volume only for float noise
- Build explicit MT5 request (action/type/filling/time/deviation/magic/comment)
- `submit` → transport → map to `ExecutionAck`
- Actual fill price **only** from broker response (never in `ExecutionIntent`)

### Does NOT own

Strategy, RiskManager, idempotency, UNKNOWN recovery, retries, position DB.

### Transport boundary

```text
MT5Executor → MT5ExecutionTransport.send(request) → MT5TransportResult
```

Production: `LiveMT5ExecutionTransport` may call `order_send`.  
Tests: `FakeMT5ExecutionTransport` — **no** real broker.

### Result mapping

| Outcome | Ack |
|---------|-----|
| Confirmed fill | FILLED |
| Definite reject | REJECTED |
| Timeout | TIMEOUT → UNKNOWN lifecycle |
| Partial / ambiguous | UNKNOWN (no invent full fill) |

### Partial-fill policy

`DONE_PARTIAL` / volume mismatch → **UNKNOWN** (`PARTIAL_FILL_UNSUPPORTED`). Not FILLED.

### Enablement

Defaults keep live **DISABLED**. `MT5Executor.submit` refuses when gates fail (`require_enablement=True`).  
`build_execution_service` still paper-only (`assert_live_execution_not_operational`).

Concepts remain separate:

```text
executor_exists = true
configuration_preflight_ready = (gates)
live_execution_enabled / allowed = false by default
```

### Why real broker execution is NOT activated

Phase 12.3 creates the **mechanism**, not authorization. No autonomous loop, no demo smoke, no Dashboard trade buttons.

---

## Phase 12.2 — Live Enablement Gates (CURRENT)

Module: `config/live_enablement.py`. Chi tiết: [`PHASE_12_2_REPORT.md`](PHASE_12_2_REPORT.md).

### Gates (all required, fail-closed)

| Gate | Env / input | Default |
|------|-------------|---------|
| A Execution mode | `EXECUTION_MODE=live` (preflight request) | paper → block |
| B Explicit flag | `ALLOW_LIVE_TRADING=true` | false |
| C Environment | `TRADING_ENV=live` | research |
| D Broker identity | `LIVE_ACCOUNT_ALLOWLIST` (+ optional server allowlist) | empty → block |
| E Symbol metadata | quote / stops / freeze / volume | missing → block |
| F Risk config | existing RiskManager settings | invalid → block |
| G Intent store | durable store healthy; no IN_FLIGHT/UNKNOWN | corrupt/UNKNOWN → block |
| H Reconciliation | `BrokerExecutionQuery` available; no AMBIGUOUS | unavailable → block |
| I Legacy isolation | `ALLOW_LEGACY_RUN=false` | true → block |
| J Kill switch | `LIVE_KILL_SWITCH` | **true** (blocks); false ≠ enable |
| K Executor capability | `MT5Executor` exists | **True from Phase 12.3** |

### Readiness vs execution

```text
configuration_preflight_ready  — config gates pass
execution_capability           — MT5Executor available (True from 12.3)
allowed                        — both; still False under defaults
```

Statuses: `LIVE_DISABLED` | `BLOCKED` | `PREFLIGHT_READY` | `NOT_IMPLEMENTED`

**Không** báo production `LIVE READY` chỉ vì executor tồn tại.

### Defaults & fail-closed

- Booleans chỉ nhận `true`/`false`
- Không paper fallback, không legacy fallback
- UNKNOWN không auto-retry / auto-repair

### Surfaces

```text
GET /api/v1/live-readiness     # read-only
exness-bot live-preflight     # read-only, exit ≠0 if not allowed
```

### Operational rule

`EXECUTION_MODE=live` có thể parse cho preflight, nhưng `build_execution_service` / paper path **fail closed** (`assert_live_execution_not_operational`).

---

## PHASE 12.1 — CURRENT (durable store)

Durable intent lifecycle (atomic JSON, fail-closed load). Xem [`PHASE_12_1_REPORT.md`](PHASE_12_1_REPORT.md).

---

## Still NOT IMPLEMENTED / NOT ACTIVATED

```text
Autonomous live trading loop
Operational EXECUTION_MODE=live as default runtime
SignalEngine → MT5Executor continuous wiring
Real DEMO order_send (operator-gated; see Phase 12.7)
automatic UNKNOWN retry
Dashboard BUY/SELL
```

---

## Blockers before Phase 12.9 / autonomous use

1. Explicit product decision after Phase 12.8 review  
2. Optional: human DEMO smoke evidence (12.7)  
3. **Do not** auto-start Phase 12.9  
