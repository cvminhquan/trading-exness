# Phase 11.6 Report — Live Execution Architecture Review & Safety Design

**Date:** 2026-08-29  
**Scope:** Design + validation. **Không** implement live order execution.  
**Status: CONDITIONAL**

Tài liệu kiến trúc: [`LIVE_EXECUTION_ARCHITECTURE.md`](LIVE_EXECUTION_ARCHITECTURE.md).

---

## Status

```text
CONDITIONAL
```

Không ghi PASS: architecture **chưa** sẵn sàng gắn `MT5Executor`.  
Không ghi BLOCKED: Phase 11 **không** đang gửi lệnh thật; các STOP condition “đang trade live” **không** kích hoạt.

---

## Architecture verdict

Pipeline hiện tại:

```text
MT5 Read-only → CandleEngine → SignalEngine → RiskManager → PaperExecutor
```

**Sẵn sàng để review / thiết kế** live executor.  
**Chưa sẵn sàng implement** `MT5Executor`.

Hướng phụ thuộc Phase 11 **đúng** (strategy/signal/risk/candle không gọi execution broker).  
`ExecutionPort` **leak paper** và nhận `fill_price` trước submit — không đủ cho live.

Repo còn **stack song song** `exness-bot run` → `MT5Adapter.order_send` (mặc định dry-run).

---

## Findings

### PASS

- `SignalEngine` không import `paper_execution` / `MT5Adapter` / `order_send`
- `RiskManager.assess()` không gửi lệnh
- `PaperExecutor` / `candle_engine` / `signal_engine` không chứa trading API
- Chỉ `actionable` BUY/SELL tới `open_position`
- `NO_SIGNAL` / `INVALID` → `IGNORED`
- Duplicate `idempotency_key` → `DUPLICATE`
- Catch-up SignalEngine: N nến → 1 `SignalResult` (unit)
- `EXECUTION_MODE=live` fail-closed (validator raise)
- `ExecutionMode` enum chỉ `paper`
- API không `POST /order` `/trade` `/execute`
- `GET /paper` `accountKind=paper` ≠ `GET /account` broker
- Dashboard không nút BUY/SELL/OPEN/CLOSE/EXECUTE (audit Phase 11.4/11.5)

### CONDITIONAL

- `ExecutionPort` gắn kiểu paper (`VirtualOrder`, `PaperAccount`, fill sẵn)
- Catch-up **không** enforce ở `ExecutionService` — tin `process_events`
- Dual stack: `OrderManager` + `MT5Adapter` còn `order_send`
- API gateway khởi tạo `MT5Adapter` trading-capable cho **đọc**
- `TRADING_MODE` + `ALLOW_LIVE_TRADING` độc lập `EXECUTION_MODE`
- Paper JSON: crash giữa fill và persist có thể trùng key khi restart
- `SymbolInfo` không có `stops_level` / `freeze_level`
- Restart live Case A–E **NOT IMPLEMENTED**
- `MT5Adapter` docstring “no order execution” **sai** so với code

### BLOCKER (trước khi implement MT5Executor — không phải blocker Phase 11.6)

1. Redesign `ExecutionPort` (intent ≠ pre-fill)
2. Persist `IN_FLIGHT`/`UNKNOWN` trước side effect
3. Reconcile broker trước mọi lệnh; paper ≠ broker
4. Cô lập stack `exness-bot run`
5. Read path chỉ `MT5ReadOnlyClient`
6. Enforce catch-up tại execution layer
7. Quote/stops/volume live validation

---

## ExecutionPort verdict

**Không phù hợp** để `MT5Executor` implement nguyên xi.

Không leak kiểu MT5. Leak paper. Semantics `open_position` = fill tức thì.

Khuyến nghị: contract `ExecutionIntent` / `ExecutionAck` — **DESIGN only**, không đổi code 11.6.

---

## Safety verdict

Phase 11.6 **hoàn toàn non-trading**:

- Không tạo `MT5Executor`
- Không gọi `order_send` / `TRADE_ACTION_*` mới
- Không bật `EXECUTION_MODE=live`
- Không đổi paper / strategy / RiskManager
- Không fallback live→paper
- Không nút lệnh trên Dashboard

---

## Tests

File: `trading-engine/tests/unit/test_live_execution_architecture.py`

| Test | Mục đích |
|------|----------|
| `test_execution_port_is_broker_agnostic` | Port không chứa token MT5 trading |
| `test_signal_engine_does_not_depend_on_execution` | Không import execution |
| `test_risk_manager_does_not_execute` | Không trading API / executor |
| `test_paper_executor_remains_broker_agnostic` | Package paper không MT5 trade |
| `test_catchup_cannot_create_execution_burst` | 3 nến miss → 1 fill |
| `test_non_actionable_signal_cannot_execute` | NO_SIGNAL / INVALID |
| `test_duplicate_signal_cannot_execute_twice` | Cùng key |
| `test_live_mode_is_not_enabled` | Enum chỉ paper |
| `test_unsupported_execution_mode_fails_closed` | `live` / `mt5` raise |
| `test_no_live_trading_api_in_phase_11_packages` | Static tokens |
| `test_paper_and_broker_state_are_distinct` | API paper ≠ account |

Không mock `order_send`. Không test live fill.

| Gate | Kết quả |
|------|---------|
| pytest | **447 passed**, 5 skipped, 1 deselected |
| ruff check src tests | **All checks passed** |
| mypy src | **Success: no issues found in 132 source files** |

---

## Static safety audit

Grep `order_send`, `TRADE_ACTION_DEAL|PENDING|SLTP|REMOVE`, `MT5Adapter`, `TradingClient`:

| Package | Kết quả |
|---------|---------|
| `candle_engine/` | **NO MATCH** |
| `signal_engine/` | **NO MATCH** |
| `paper_execution/` | **NO MATCH** |
| `risk/manager.py` | **NO MATCH** |
| `broker/mt5/` | MATCH — stack cũ (`MT5Adapter.order_send`), không phải Phase 11 |

---

## Documentation

| File | Việc |
|------|------|
| `docs/LIVE_EXECUTION_ARCHITECTURE.md` | **Tạo** — 16 mục + nhãn CURRENT/DESIGN/FUTURE/NOT IMPLEMENTED |
| `docs/PHASE_11_6_REPORT.md` | **Tạo** (file này) |
| `trading-engine/docs/PHASE_11_6_REPORT.md` | Pointer |

Không đổi hành vi paper. Không sửa `ExecutionPort`.

---

## Known limitations

1. Live executor **chưa** tồn tại — đúng mục tiêu 11.6.
2. `exness-bot run` vẫn là đường lệnh broker (dry-run mặc định).
3. Catch-up burst chỉ được chứng minh qua `SignalEngine.process_events`, không phải invariant cứng của `consume()`.
4. Restart paper không transactional.
5. Weekend: forming→closed MT5 live **NOT TESTED** (Phase 11.5).
6. `ARCHITECTURE.md` mô tả trục OrderManager — lệch so với Phase 11.

---

## Phase 11.7 readiness

**Không** bắt đầu Phase 11.7.

Trước `MT5Executor` thật:

1. Hardening pre-live (cô lập `run`, read-only API, port redesign, IN_FLIGHT persist, catch-up gate, reconcilation spec)
2. Vẫn cấm `EXECUTION_MODE=live` cho đến phase implement có chủ đích
3. Test bằng fake `ExecutionPort` — **cấm** mock `order_send` như live giả

Chi tiết: mục 17 trong [`LIVE_EXECUTION_ARCHITECTURE.md`](LIVE_EXECUTION_ARCHITECTURE.md).
