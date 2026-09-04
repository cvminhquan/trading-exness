# Phase 11.4 Report — Paper Trading Validation

**Ngày xác nhận:** 2026-08-29  
**Phạm vi:** Xác minh pipeline PAPER/RESEARCH (MT5 read-only → nến đóng → tín hiệu → risk → paper fill → Dashboard/API)  
**Status: CONDITIONAL**

Lý do không ghi PASS:

- Pytest / ruff / mypy **đạt**.
- Smoke Windows + Exness MT5 demo **đã chạy** (`exness-bot paper --once` hai lần): kết nối read-only, warm start, **0 paper fill** vì `CANDLE_ALREADY_PROCESSED`.
- Nến đóng **mới** trong phiên (forming → closed → tín hiệu actionable → 1 vị thế ảo) **chưa** quan sát: 2026-08-29 là thứ Bảy.
- Broker positions **3 → 3** (không đổi) trên cả hai lần `--once`.
- Dashboard `/dashboard/paper` **đã** quan sát sau khi restart API: PAPER ACCOUNT $10,000 tách khỏi BROKER ACCOUNT (~$8,161 / equity ~$41,177); 3 vị thế Short XAUUSD trên trang Vị thế.

Không suy đoán fill chưa có bằng chứng.

Tài liệu: [`PAPER_EXECUTION.md`](PAPER_EXECUTION.md), [`PAPER_VALIDATION.md`](PAPER_VALIDATION.md).

---

## Implementation

Phase 11.4 **không** thêm live execution. Bổ sung validation + session + API/Dashboard:

| Thành phần | Thay đổi |
|------------|----------|
| `PaperSession` | session_id, started_at, balances, PnL, drawdown, counts |
| JSON schemaVersion 2 | `sessionId`, `startedAt`, `candlesProcessed`, `signalCount`, `currentPrice` |
| Mark-to-market | LONG = bid, SHORT = ask (`VirtualPosition.current_price`) |
| `GET /api/v1/status` | `candleEngine` + `signalEngine` + `paperExecution.accountKind=paper` |
| `GET /api/v1/paper` | session + `positions[]` (PAPER POSITION) |
| CLI `paper --once` | log `paper_validation_summary` (broker before/after) |
| Dashboard | `/dashboard/paper`: warning bắt buộc; Tổng quan = BROKER ACCOUNT; Vị thế = BROKER ACCOUNT |
| Lifespan API | paper **xor** signal **xor** candle (một thread) |

Luồng không đổi:

```
MT5 (read-only)
  → Closed Candle (bỏ forming)
  → SignalEngine (ema_rsi_atr_v1)
  → RiskManager.assess()
  → PaperExecutor.open_position()
  → Virtual Position / Virtual PnL
  → GET /api/v1/paper
```

`PaperExecutor` vẫn là execution boundary duy nhất. **Không** `order_send` / `TRADE_ACTION_*` / `MT5Adapter` / `TradingClient` trên `paper_execution/`, `signal_engine/`, `candle_engine/`.

`EXECUTION_MODE=paper` fail closed; giá trị khác (kể cả `live`) raise, không fallback.

Không đổi EMA / RSI / ATR / entry / SL multiplier / RR.

---

## Architecture

* Signal Engine không import paper.
* Paper không gọi broker trading API; MT5 chỉ `TradingDataProvider` (nến + tick).
* Persistence: atomic `.tmp` + `replace`. Restart cùng file → cùng `sessionId` + khóa idempotency.
* API worker: `PAPER_EXECUTION_ENABLED=true` chạy **một** thread `paper-execution`. Mặc định `false` để TestClient không spawn thread.
* Khi worker tắt, `GET /api/v1/paper` trả snapshot mặc định $10,000 (`sessionId=null`). File CLI `.paper_execution_state.json` **không** tự gắn vào process API — tránh double-poll và tránh TestClient đọc file máy thật.

---

## Automated tests

File mới: `trading-engine/tests/unit/test_paper_validation.py`

| # | Case | Test |
|---|------|------|
| 1 | closed candle → signal → paper fill | `test_closed_candle_signal_paper_fill` |
| 2 | actionable=false → không execution | `test_actionable_false_does_not_execute` |
| 3 | duplicate signal → không duplicate fill | `test_duplicate_signal_no_second_fill` |
| 4 | risk rejection → không mở | `test_risk_rejection_does_not_open` |
| 5 | BUY → TP | `test_buy_then_tp` |
| 6 | SELL → TP | `test_sell_then_tp` |
| 7 | BUY → SL | `test_buy_then_sl` |
| 8 | SELL → SL | `test_sell_then_sl` |
| 9 | SL-first cùng nến | `test_same_candle_sl_first` |
| 10 | unrealized BUY = bid | `test_unrealized_uses_bid_for_buy` |
| 11 | unrealized SELL = ask | `test_unrealized_uses_ask_for_sell` |
| 12 | realized PnL | `test_realized_pnl_and_equity` |
| 13 | equity / drawdown | `test_drawdown_after_sl` |
| 14 | restart persistence | `test_restart_keeps_session_and_position` |
| 15 | restart không duplicate | `test_restart_does_not_duplicate_execution` |
| 16 | broker disconnect không reset paper | `test_broker_disconnect_does_not_reset_paper_state` |
| 17 | paper mode không gọi MT5 trading API | `test_phase_11_packages_have_no_trading_api` |

Thêm: `test_api_lifespan_is_exclusive`, `test_paper_payload_distinct_from_broker`.

---

## Quality gate

| Gate | Kết quả |
|------|---------|
| pytest | **429 passed**, 5 skipped, 1 deselected |
| ruff check src tests | **All checks passed** |
| mypy src | **Success: no issues found in 132 source files** |
| dashboard `npm test` | **21 passed** |
| dashboard `tsc --noEmit` | **pass** |

---

## Safety audit

Tìm trong `paper_execution/`, `signal_engine/`, `candle_engine/` (2026-08-29):

`order_send`, `TRADE_ACTION_DEAL`, `TRADE_ACTION_PENDING`, `TRADE_ACTION_SLTP`, `TRADE_ACTION_REMOVE`, `MT5Adapter`, `TradingClient` — **không xuất hiện**.

---

## Windows + MT5 smoke

Command:

```bash
DATA_SOURCE=mt5
EXECUTION_MODE=paper
exness-bot paper --once
```

(`PAPER_EXECUTION_ENABLED` chỉ bật worker trên API; CLI `paper` luôn chạy vòng paper.)

### Lần 1

| Field | Giá trị |
|-------|---------|
| Kết nối | Exness-MT5Trial17, `mt5_readonly_initialized` |
| `candle_status` | `CANDLE_ALREADY_PROCESSED` |
| `session_id` | `59633903-7e1a-41dd-81bf-5f7160366264` |
| candles_processed | 0 |
| signal_count | 0 |
| execution_count | 0 |
| rejected_count | 0 |
| paper_open | 0 |
| realized_pnl | 0.0 |
| unrealized_pnl | 0.0 |
| drawdown_pct | 0.0 |
| **Broker positions BEFORE** | **3** |
| **Broker positions AFTER** | **3** |
| `broker_positions_unchanged` | `True` |

### Lần 2 (restart)

* Log `paper_execution_state_recovery`
* **Cùng** `session_id` `59633903-7e1a-41dd-81bf-5f7160366264`
* execution_count vẫn 0 (không duplicate)
* Broker **3 → 3**

Forming → closed → 1 paper fill: **NOT TESTED** (thị trường đóng, thứ Bảy).

---

## Dashboard validation

Sau restart API (process cũ không có `GET /paper`):

| Hạng mục | Quan sát |
|----------|----------|
| `GET /api/v1/status` | `candleEngine`, `signalEngine`, `paperExecution.accountKind=paper` |
| `GET /api/v1/paper` | `accountKind=paper`, researchOnly, $10,000, positions=[] |
| `/dashboard/paper` | Warning **"PAPER ONLY — KHÔNG PHẢI VỊ THẾ THẬT TRÊN EXNESS"**; PAPER ACCOUNT $10,000; Last Signal / Last Execution / session |
| `/dashboard` | Banner paper $10,000 **khác** BROKER ACCOUNT số dư ~$8,161 / equity ~$41,177 |
| `/dashboard/positions` | Badge **BROKER ACCOUNT**; 3 Short XAUUSD — không phải paper |

Không có nút gửi lệnh trên Dashboard.

PAPER POSITION card chỉ hiện khi `positions.length > 0`. Smoke không có vị thế giấy → card không hiện (đúng). Mock repository có 1 PAPER POSITION để xem layout.

Worker API `STOPPED` vì `PAPER_EXECUTION_ENABLED` mặc định `false`.

---

## Known limitations

1. Weekend: không có nến M15 đóng mới → không quan sát fill live.
2. JSON persistence không transactional (crash giữa mutate và replace).
3. API không load file CLI trừ khi bật `PAPER_EXECUTION_ENABLED` (gắn worker). Dashboard lúc worker tắt = mặc định $10,000.
4. Quote MT5 thứ Bảy: Dashboard báo **Dữ liệu cũ**.
5. Paper fill giá (bid/ask lúc phát hiện) **cố ý khác** backtest (close nến). SL-first giữ nguyên.

---

## PHASE 11.5 readiness

Pipeline paper **sẵn sàng tiếp tục research** trên phiên thị trường mở (M15 forming → closed).

**Không sẵn sàng Live Execution.** Chưa có `MT5Executor`, chưa có `order_send`, `EXECUTION_MODE=live` vẫn fail closed.

Không tự chuyển Phase 11.5.
