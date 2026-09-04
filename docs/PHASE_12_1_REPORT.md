# Phase 12.1 Report — Durable Live Intent Store

**Date:** 2026-08-29  
**Scope:** Durable intent lifecycle store — atomic local snapshot, fail-closed load, explicit transitions.  
**Status: CONDITIONAL**

---

## Status

```text
CONDITIONAL
```

| Label | Ý nghĩa |
|-------|---------|
| **PASS** | DurableIntentStore API, atomic tmp→fsync→replace, fail-closed corruption/schema, explicit transitions, IN_FLIGHT-before-submit, UNKNOWN recovery, idempotency, tests + ruff + mypy |
| **CONDITIONAL** | JSON local durability ≠ ACID / ≠ MT5 2PC; single-process only |
| **NOT IMPLEMENTED** | `MT5Executor`, live order, `EXECUTION_MODE=live`, auto UNKNOWN retry |
| **NOT TESTED** | Multi-process concurrent writers; OS crash during `os.replace` |
| **BLOCKED** | Không — sẵn sàng Phase 12.2 (enablement design) khi được yêu cầu riêng |

---

## CURRENT architecture

```text
risk approved
    ↓
DurableIntentStore.create_intent → INTENT_CREATED
    ↓
mark_in_flight → IN_FLIGHT   # persisted BEFORE submit
    ↓
ExecutionPort.submit()
    ↓
mark_filled | mark_rejected | mark_unknown
```

Startup:

```text
load snapshot (fail-closed)
    ↓
IN_FLIGHT → UNKNOWN
    ↓
optional read-only BrokerExecutionQuery reconcile
    ↓
NO submit
```

---

## Lifecycle transitions

Allowed (`mark_*`):

```text
CREATED → IN_FLIGHT
IN_FLIGHT → FILLED | REJECTED | UNKNOWN
```

Reconciliation only (evidence-backed):

```text
UNKNOWN → FILLED | REJECTED   # reconcile_filled / reconcile_rejected
```

Rejected:

```text
FILLED → IN_FLIGHT
UNKNOWN → IN_FLIGHT
UNKNOWN → FILLED via mark_filled   # must use reconcile_*
```

---

## Persistence

- `FilePaperStateStore.save`: write `*.tmp` → `flush` → `os.fsync` → `os.replace`
- One mutation → one coherent PaperSnapshot (intents + session + keys)
- Missing file → fresh snapshot (first start)
- Empty / invalid JSON / bad schema / duplicate ids-keys / missing intent fields → **fail closed** (`CorruptStateError` / `UnsupportedSchemaError`)
- **Không** reset corrupt state thành empty account

---

## Schema

```text
schemaVersion = 3 (unchanged)
```

Không bump schema: Phase 12.1 chỉ harden load/save + store API; không thêm field bắt buộc mới. Unsupported version → fail closed.

---

## Durability semantics

```text
Durable locally ≠ Broker transactionally coupled
```

Guarantees: atomic local replace, deterministic recovery, lifecycle + idempotency persistence, no silent reset.

Does **NOT** guarantee: MT5 2PC, exactly-once broker execution, broker ACK durability.

---

## Concurrency

Single-process architecture. `threading.Lock` / `RLock` bảo vệ mutate+persist in-process. Không có distributed lock.

---

## Quality gates

```text
pytest: 571 passed, 5 skipped
ruff check src tests: clean
mypy src: clean
```

---

## Explicitly NOT IMPLEMENTED

1. MT5Executor  
2. Live order execution  
3. EXECUTION_MODE=live  
4. Automatic UNKNOWN retry / auto FILLED|REJECTED without evidence  

---

## Acceptance checklist

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Explicit lifecycle | PASS |
| 2 | IN_FLIGHT before side effect | PASS |
| 3 | Idempotency survives restart | PASS |
| 4 | No duplicate intent | PASS |
| 5 | Corrupt fails closed | PASS |
| 6 | Unsupported schema fails closed | PASS |
| 7 | Impossible transitions rejected | PASS |
| 8 | IN_FLIGHT → UNKNOWN recovery | PASS |
| 9 | UNKNOWN never auto-resubmits | PASS |
| 10 | UNKNOWN not auto FILLED/REJECTED | PASS |
| 11 | Atomic snapshot | PASS |
| 12 | Paper behaviour unchanged | PASS |
| 13–15 | No MT5 trading / no live mode | PASS |
| 16–18 | Tests / ruff / mypy | PASS |
| 19–20 | Docs + report | PASS |

**Overall: CONDITIONAL** — local durable store sẵn sàng cho phase live tiếp theo; chưa production DB / chưa MT5Executor.
