# Live Execution Architecture & Safety Design

**Cập nhật:** Phase 12.4 (Controlled DEMO one-shot) — 2026-08-29.

Nhãn: **CURRENT** | **DESIGN** | **FUTURE** | **NOT IMPLEMENTED**.

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
Operational EXECUTION_MODE=live runtime
Demo/real order_send smoke
automatic UNKNOWN retry
```

---

## Blockers before controlled live use (Phase 12.4+)

1. Explicit approval + operator runbook  
2. Wire `LiveMT5ExecutionTransport` under gates only  
3. Demo smoke with separate approval  
4. UNKNOWN / NOT_FOUND operator procedures  
