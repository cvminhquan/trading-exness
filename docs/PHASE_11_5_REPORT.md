# Phase 11.5 Report — Live Paper Session Validation

**Date:** 2026-08-29  
**Scope:** Xác minh pipeline PAPER/RESEARCH trên dữ liệu MT5 (document + automated pipeline + smoke). **Không** Live Execution.  
**Status: CONDITIONAL**

Lý do không ghi PASS:

- Quality gate **đạt**.
- Smoke Windows + Exness MT5: kết nối read-only, `CANDLE_ALREADY_PROCESSED`, broker **3 → 3**.
- Forming M15 → closed → `ClosedCandleEvent` **trong phiên đang mở** **NOT TESTED** (thứ Bảy, không có nến đóng mới).
- Paper fill live **NOT TESTED** (không có nến đóng mới / không có tín hiệu actionable).

Không suy đoán fill hay tín hiệu chưa quan sát.

Tài liệu: [`LIVE_PAPER_VALIDATION.md`](LIVE_PAPER_VALIDATION.md).

---

## Implementation summary

Không thêm `MT5Executor`, không đổi `ema_rsi_atr_v1`, EMA/RSI/ATR, SL/RR, RiskManager, warmup.

Đã thêm:

| Mục | Chi tiết |
|-----|----------|
| Tests | `trading-engine/tests/unit/test_live_paper_session.py` — 7 case pipeline (FakeClock, không MT5) |
| Docs | `docs/LIVE_PAPER_VALIDATION.md` — forming, closed, signal, risk, fill, idempotency, restart, broker, dashboard, smoke |

Tái sử dụng `candle_engine` + `signal_engine` + `paper_execution` + `process_closed_candles`.

---

## Architecture

```
MT5 Read-only → Candle → Signal → Risk → PaperExecutor → Virtual Position
```

Không có `Signal → MT5Adapter` / `TradingClient` / `order_send`.  
`EXECUTION_MODE=live` vẫn fail closed.

---

## Automated tests

| Test | Kết quả |
|------|---------|
| `test_live_pipeline_uses_closed_candle_only` | PASS |
| `test_live_pipeline_no_lookahead` | PASS |
| `test_live_pipeline_signal_to_paper` | PASS |
| `test_live_pipeline_risk_rejection` | PASS |
| `test_live_pipeline_duplicate_poll_is_idempotent` | PASS |
| `test_live_pipeline_restart_preserves_state` | PASS |
| `test_live_pipeline_does_not_touch_broker_positions` | PASS |

Các test này **không** phải bằng chứng MT5 live.

---

## Quality gate

| Gate | Kết quả |
|------|---------|
| pytest | **436 passed**, 5 skipped, 1 deselected |
| ruff check src tests | **All checks passed** |
| mypy src | **Success: no issues found in 132 source files** |
| dashboard `npm test` | **21 passed** |
| dashboard `tsc --noEmit` | **pass** |

---

## Windows + MT5 smoke

```bash
DATA_SOURCE=mt5
EXECUTION_MODE=paper
exness-bot paper --once
```

| Field | Giá trị |
|-------|---------|
| Kết nối | `mt5_readonly_initialized`, Exness-MT5Trial17 |
| `candle_status` | `CANDLE_ALREADY_PROCESSED` |
| `session_id` | `59633903-7e1a-41dd-81bf-5f7160366264` (giữ sau restart file) |
| paper_open / execution_count / signal_count | 0 |
| **Broker BEFORE** | **3** |
| **Broker AFTER** | **3** |
| `broker_positions_unchanged` | `True` |

`exness-bot paper` vòng dài **không** chạy (không chờ M15 đóng trên weekend).

---

## Broker safety

Paper execution **không** làm thay đổi số vị thế MT5 trên smoke này (3 = 3).

---

## Safety audit

`paper_execution/`, `signal_engine/`, `candle_engine/`: `order_send`, `TRADE_ACTION_*`, `MT5Adapter`, `TradingClient` — **NO MATCH**.

API: không có `POST /order` / `POST /execute`.

---

## Evidence table

| Requirement | Result | Evidence |
|-------------|--------|----------|
| MT5 connected | PASS | Smoke `mt5_connection_manager_connected` Exness-MT5Trial17; API `connectionStatus=CONNECTED` |
| Canonical symbol | PASS | Engine `XAUUSD` (settings / CandleEngine) |
| Broker symbol | NOT TESTED | Lần `--once` này không in suffix broker |
| Forming candle ignored | PASS (unit) / NOT TESTED (MT5 live) | `test_live_pipeline_uses_closed_candle_only`; live forming **không** quan sát |
| Closed candle detected | PASS (unit) / NOT TESTED (MT5 live) | Unit `CANDLE_PROCESSED` + timestamp `10:00`; live `CANDLE_ALREADY_PROCESSED` |
| ClosedCandleEvent | PASS (unit) / NOT TESTED (MT5 live) | Unit: 1 event, `detected_at != timestamp` |
| No look-ahead | PASS (unit) / NOT TESTED (MT5 live) | Forming close=9999 không vào history |
| Indicators | PASS (unit) / NOT TESTED (MT5 live) | Pipeline gọi `ema_rsi_atr_v1` + snapshot EMA/RSI/ATR |
| Strategy evaluated | PASS (unit) / NOT TESTED (MT5 live) | `strategy=ema_rsi_atr_v1`; live warmup 0 signal |
| SignalResult | PASS (unit) / NOT TESTED (MT5 live) | Unit BUY actionable; live không có nến mới |
| Risk | PASS (unit) / NOT TESTED (MT5 live) | Unit reject `MAX_OPEN_POSITIONS` |
| Paper fill | PASS (unit) / NOT TESTED (MT5 live) | Fill = ask+slippage ≠ close; live 0 execution |
| Virtual position | PASS (unit) / NOT TESTED (MT5 live) | 1 `paper-pos-*`; live `paper_open=0` |
| PnL | PASS (unit) / NOT TESTED (MT5 live) | BUY mark = bid; equity = balance + unrealized |
| Idempotency | PASS (unit) / NOT TESTED (MT5 live poll lặp trên nến mới) | Duplicate poll 0 event thêm; live chỉ `ALREADY_PROCESSED` |
| Restart | PASS (unit) + PASS (CLI file) | Cùng `session_id`; unit giữ position |
| Broker positions unchanged | PASS | 3 → 3; unit tickets không đổi |
| API | PASS | `GET /status`: candleEngine, signalEngine, paperExecution; `GET /paper` `accountKind=paper` |
| Dashboard | PASS | `/dashboard`, `/dashboard/paper`, `/dashboard/positions` (Phase 11.4 cùng ngày): PAPER ≠ BROKER; warning bắt buộc; không nút BUY/SELL/OPEN/CLOSE/EXECUTE |
| Safety audit | PASS | NO MATCH trading API trên 3 package |

---

## Known limitations

1. Weekend: không chứng minh forming → closed trên MT5 thật.
2. Unit BUY dùng snapshot chỉ báo hợp lệ `_decide` — không tối ưu strategy, không phải tín hiệu thị trường live.
3. API worker `PAPER_EXECUTION_ENABLED=false` → `GET /paper` mặc định $10,000, không gắn session CLI.
4. JSON persistence không transactional.

---

## Phase 11.6 readiness

Hệ thống **sẵn sàng để review architecture** cho Live Execution (phase riêng).

**Không** implement Phase 11.6. Chưa có `MT5Executor`. Không chuyển `Signal → ExecutionPort → MT5Executor`.
