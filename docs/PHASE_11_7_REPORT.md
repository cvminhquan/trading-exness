# Phase 11.7 Report — Pre-Live Hardening

**Date:** 2026-08-29  
**Scope:** Hardening kiến trúc trước live. **Không** implement `MT5Executor`. **Không** gửi lệnh thật.  
**Status: CONDITIONAL**

Tài liệu: [`LIVE_EXECUTION_ARCHITECTURE.md`](LIVE_EXECUTION_ARCHITECTURE.md) (đã cập nhật cho Phase 11.7).

---

## Status

```text
CONDITIONAL
```

Không ghi **PASS**: còn blocker trước `MT5Executor` (reconcile live, crash windows A–E đầy đủ, stack legacy `run` vẫn tồn tại).  
Không ghi **BLOCKED**: Phase 11 vẫn non-trading; các hardening bắt buộc của 11.7 đã có evidence test.

---

## Architecture changes (CURRENT sau 11.7)

```text
MT5 Read-only (TradingDataProvider / MT5ReadOnlyClient)
    ↓
CandleEngine → ClosedCandleEvent
    ↓
SignalEngine → SignalResult(executable=…)
    ↓
ExecutionService.consume / consume_results
    ↓
RiskManager.assess
    ↓
ExecutionIntent  (không có fill_price)
    ↓
persist IN_FLIGHT
    ↓
ExecutionPort.submit(intent, quote=…)
    ├── PaperExecutor → ExecutionAck(FILLED) + VirtualPosition   [CURRENT]
    └── MT5Executor                                              [FUTURE / NOT IMPLEMENTED]
```

---

## ExecutionPort redesign

| Trước (11.6) | Sau (11.7) |
|--------------|------------|
| `open_position(PaperOpenRequest)` với `fill_price` từ caller | `submit(ExecutionIntent, quote=…) → ExecutionAck` |
| Intent = fill sẵn | Intent **không** chứa guaranteed fill |
| Paper leak trên request | Port broker-agnostic về intent/ack; paper types còn trên close/account helpers |

**CURRENT:** `ExecutionIntent`, `ExecutionAck`, `AckStatus`, `IntentLifecycle`, `IntentRecord` trong `paper_execution/contract.py`.

Paper: `PaperExecutor.submit` tự tạo fill (`ask+slip` / `bid-slip`). Risk sizing vẫn dùng cùng quote simulation trước submit để giữ SL/volume paper ổn định — **không** ghi fill vào Intent.

---

## Lifecycle model

```text
INTENT / risk approve
    → persist IntentRecord(IN_FLIGHT)   # trước side effect
    → ExecutionPort.submit(...)
    → persist FILLED | REJECTED | UNKNOWN
```

| Crash window | CURRENT paper | FUTURE live |
|--------------|---------------|-------------|
| Sau IN_FLIGHT, trước fill | Restart: `has_blocking_intent` → `UNKNOWN` outcome, không side effect mới | Cần query broker (NOT IMPLEMENTED) |
| Sau fill, trước persist final | Có thể mất FILLED trên disk (JSON non-transactional) | Cần durable store |

**CURRENT:** IN_FLIGHT / UNKNOWN persist + restart tests.  
**NOT IMPLEMENTED:** broker query sau UNKNOWN.

---

## Catch-up invariant

**CURRENT tại execution boundary:**

- `SignalResult.executable` (SignalEngine set `True` chỉ cho emission latest actionable)
- `ExecutionService.consume` từ chối nếu `not executable` hoặc `emission != SIGNAL_EMISSION` → `CATCHUP_IGNORED`
- `consume_results`: trong batch chỉ **một** tín hiệu latest (max candle_timestamp) được execute; còn lại `CATCHUP_IGNORED`

```text
N missed candles → N indicator updates → 1 actionable latest → max 1 intent
```

---

## Read-only MT5 boundary

| Component | BEFORE | AFTER |
|-----------|--------|-------|
| API `MT5BrokerReadGateway` | `MT5Adapter` (trading-capable) | `MT5ConnectionManager` + read-only client |
| Phase 11 packages | Không import trading | Giữ — AST tests |
| CLI `paper` / `signals` / `candles` | Read-only provider | Giữ + static proof không `MT5Adapter`/`OrderManager` |

---

## Validation abstractions

**CURRENT:** `domain/execution_validation.py`

- `validate_quote`, `validate_volume`, `validate_stops_metadata`, `validate_sl_tp_distance`
- `SymbolInfo.stops_level` / `freeze_level`: `None` = unavailable (fail-closed cho live validation; **không** giả = 0)
- `map_symbol_info` map `trade_stops_level` / `trade_freeze_level` khi MT5 có

**NOT IMPLEMENTED:** gắn validation vào live submit path.

---

## Legacy stack isolation

**CURRENT:**

- `exness-bot run` vẫn LEGACY: `MT5Adapter` → `OrderManager` → có thể `order_send` nếu không dry-run
- CLI warning `legacy_run_stack`; help text ghi LEGACY
- `MT5Adapter` docstring sửa (không còn “no order execution in Phase 1”)
- `TRADING_MODE` / `ALLOW_LIVE_TRADING` documented tách khỏi `EXECUTION_MODE=paper`

**NOT IMPLEMENTED:** xóa hoặc force-disable `run`.

---

## Reconciliation (read-only design)

**CURRENT:** `paper_execution/reconciliation.py` — `MATCH` / `MISSING_LOCAL` / `MISSING_BROKER` / `MISMATCH` / `UNKNOWN`.

So sánh paper vs broker **không** copy vị thế. Không đặt/sửa lệnh.

---

## API / Dashboard safety

- Không `POST /order` `/trade` `/execute` `/position`
- `POST /accounts/active` chỉ switch xem
- Dashboard không đổi trong 11.7 — PAPER ≠ BROKER (giữ Phase 11.4/11.5)

---

## Tests

`tests/unit/test_phase_11_7_hardening.py` (+ cập nhật tests 11.3–11.6).

| Gate | Kết quả |
|------|---------|
| pytest | **479 passed**, 5 skipped, 1 deselected |
| ruff check src tests | **All checks passed** |
| mypy src | **Success: no issues found in 135 source files** |

Dashboard không đổi → không chạy npm.

---

## Static safety audit

| Package | Kết quả |
|---------|---------|
| `candle_engine/` | NO MATCH trading tokens |
| `signal_engine/` | NO MATCH |
| `paper_execution/` | NO MATCH |
| `risk/` | NO MATCH |
| `api/services/broker_gateway.py` | NO MATCH `MT5Adapter` / `order_send` |
| `broker/mt5/adapter.py` + `trading_client.py` | MATCH — **legacy `exness-bot run` only** |

Không có `class MT5Executor`.

---

## Known limitations

1. `MT5Executor` **NOT IMPLEMENTED** (đúng mục tiêu).
2. Legacy `exness-bot run` vẫn có đường `order_send` (dry-run mặc định).
3. Paper JSON vẫn không transactional giữa IN_FLIGHT và FILLED disk write cuối.
4. Validation stops/freeze chưa gắn vào paper path (chỉ primitives).
5. Live Case A–E recovery đầy đủ **NOT IMPLEMENTED**.
6. Port vẫn expose `PaperAccount` / `VirtualPosition` trên close/account (paper helpers) — đủ cho paper, chưa “pure” cho live-only port.

---

## Phase 11.8 readiness

**Không** bắt đầu Phase 11.8 trong báo cáo này.

Đề xuất Phase 11.8 (nếu tiếp tục pre-live):

1. Fake `ExecutionPort` mô phỏng ACCEPTED / TIMEOUT / UNKNOWN (vẫn **không** `order_send`)
2. Durable intent store + recovery policy cho UNKNOWN
3. Gắn quote/stops validation vào gate trước submit (paper optional; live bắt buộc)
4. Quyết định deprecate / seal `exness-bot run`
5. Chỉ sau đó mới xét phase implement `MT5Executor` có chủ đích

**Không** bật `EXECUTION_MODE=live` trong 11.8 trừ khi đó là phase live có kiểm soát riêng.
