# Phase 11.8 Report — Pre-Live Execution Boundary Hardening

**Date:** 2026-08-29  
**Scope:** Hardening biên ExecutionService / IntentStore / validation / UNKNOWN recovery.  
**Status: CONDITIONAL**

---

## Status

```text
CONDITIONAL
```

| Label | Ý nghĩa |
|-------|---------|
| **PASS** | Fake port, durable IN_FLIGHT-before-submit, UNKNOWN recovery no-resubmit, validation gate, catch-up, fail-closed modes, tests xanh |
| **CONDITIONAL** | Legacy `exness-bot run` vẫn tồn tại; chưa có broker query cho UNKNOWN; chưa `MT5Executor` |
| **NOT IMPLEMENTED** | `MT5Executor`, live order, `EXECUTION_MODE=live`, auto-repair reconciliation |
| **NOT TESTED** | MT5 forming→closed live smoke (không bắt buộc cho 11.8) |

---

## Explicit non-goals (verified)

```text
MT5Executor = NOT IMPLEMENTED
Live order execution = NOT IMPLEMENTED
EXECUTION_MODE=live = DISABLED (fail-closed)
```

Không `order_send` / `TRADE_ACTION_*` trên Phase 11 path.  
Không mock `order_send` như live giả.  
`UNKNOWN` ≠ `FILLED` ≠ `REJECTED` ≠ auto-retry.

---

## Architecture (CURRENT)

```text
SignalResult
    ↓
ExecutionService (catch-up + idempotency + risk)
    ↓
validate quote / volume / stops / SL-TP   # fail-closed
    ↓
IntentStore: CREATED → IN_FLIGHT          # persisted BEFORE submit
    ↓
ExecutionPort.submit()
    ├── PaperExecutor (production) → Ack FILLED
    └── FakeExecutionPort (tests only)
    ↓
IntentStore: FILLED | REJECTED | UNKNOWN
```

---

## Fake ExecutionPort

**CURRENT:** `paper_execution/fake_port.py`

- Deterministic `AckStatus`: FILLED / REJECTED / TIMEOUT / UNKNOWN / ACCEPTED
- Không chứa MT5 / trading mutation tokens
- Chỉ dùng trong unit tests — không wire production live

---

## Durable intent store

**CURRENT:** `paper_execution/intent_store.py` — `IntentStore` + `SnapshotIntentStore`

- Rows trong `PaperSnapshot.intents` (JSON schemaVersion 3+)
- Fields: intent_id, idempotency_key, lifecycle, timestamps, symbol, side, volume, sl, tp, strategy, timeframe, signal_timestamp
- `ExecutionIntent` vẫn **không** chứa guaranteed fill price

Lifecycle:

```text
CREATED → IN_FLIGHT → FILLED | REJECTED | UNKNOWN
```

Invariant:

```text
persist(IN_FLIGHT) → port.submit() → persist(final)
```

---

## UNKNOWN recovery

On `ExecutionService` startup:

```text
IN_FLIGHT → UNKNOWN
```

Then:

- Giữ nguyên `intent_id` + `idempotency_key`
- **Không** `submit()` lại
- **Không** map sang FILLED / REJECTED
- Consume cùng key → `ExecutionOutcome.UNKNOWN` hoặc `DUPLICATE` (nếu đã remember_key)

Broker reconciliation vẫn **read-only** — không auto-repair.

---

## Validation-before-submit

Dùng primitives Phase 11.7:

- `validate_quote`
- `validate_volume`
- `validate_stops_metadata`
- `validate_sl_tp_distance`

Thiếu `stops_level` / `freeze_level` → `INVALID_STOPS`, **không** giả = 0.

Paper research: `BacktestConfig.paper_stops_level` / `paper_freeze_level` gắn **tường minh** vào SymbolInfo paper (không phải silent broker default).

Validation failure → REJECTED **trước** IN_FLIGHT và **trước** submit.

---

## Legacy `exness-bot run`

```text
LEGACY — NOT part of Phase 11 ExecutionPort architecture
```

- CLI help + `legacy_run_stack` warning
- `EXECUTION_MODE=paper` không route vào `OrderManager`
- Phase 11 `paper` / `signals` / `candles` không construct `MT5Adapter` / `OrderManager`

**Không** xóa legacy trong 11.8.

---

## Tests

`tests/unit/test_phase_11_8_hardening.py`

| Gate | Kết quả |
|------|---------|
| pytest | **506 passed**, 5 skipped, 1 deselected |
| ruff check src tests | **All checks passed** |
| mypy src | **Success: no issues found in 137 source files** |

---

## Static safety audit

| Scope | Kết quả |
|-------|---------|
| `candle_engine/` | NO MATCH |
| `signal_engine/` | NO MATCH |
| `paper_execution/` | NO MATCH (`FakeExecutionPort` sạch) |
| `risk/` | NO MATCH |
| `api/services/` | NO MATCH trading mutation |
| `broker/mt5/adapter.py` + `trading_client.py` | MATCH — **legacy `exness-bot run` only** |

---

## Known limitations / remaining blockers before MT5Executor

1. UNKNOWN recovery chưa query broker deals/positions (chỉ fail-closed local)
2. Legacy `exness-bot run` vẫn có đường broker submit (dry-run mặc định)
3. JSON intent store chưa transactional đa bước với broker
4. PaperAccount helpers vẫn trên ExecutionPort surface
5. Chưa có kill-switch live độc lập ngoài cấm `EXECUTION_MODE=live`

---

## Phase 11.8 Status

```text
CONDITIONAL
```

**Không** bắt đầu Phase 11.9 tự động.

Remaining blockers before `MT5Executor`:

1. Authoritative UNKNOWN reconciliation against broker (read then decide — still no auto-resubmit without proof)
2. Seal / deprecate legacy `run` path for production operators
3. Durable transactional intent store suitable for crash between broker ack and local persist
4. Live-only ExecutionPort surface (no paper account types)
5. Explicit multi-gate live enablement (separate from Phase 11 paper) — only in a dedicated live phase
