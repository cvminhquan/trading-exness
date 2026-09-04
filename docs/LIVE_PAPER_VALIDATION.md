# Live Paper Session Validation (Phase 11.5)

Tài liệu này mô tả cách **xác minh** pipeline PAPER/RESEARCH trên market data MT5 thật khi phiên XAUUSD đang mở. Phase 11.5 **không** thêm Live Execution.

## Mục tiêu

```
MT5 Read-only
    → M15 forming (bỏ qua)
    → M15 đóng → ClosedCandleEvent
    → EMA20/50/200, RSI14, ATR14
    → ema_rsi_atr_v1 → SignalResult
    → RiskManager.assess()
    → Paper fill nếu actionable + approved
    → Virtual Position / Virtual PnL
    → API / Dashboard
```

Không tạo live order. `NO_SIGNAL` là kết quả hợp lệ. Không sửa strategy để ép BUY/SELL.

## Pipeline hiện có

Tái sử dụng Phase 11.1–11.4:

| Lớp | Package | Vai trò |
|-----|---------|---------|
| Nến đóng | `candle_engine` | Bỏ forming; emit theo timestamp + duration, không tin index 0 |
| Tín hiệu | `signal_engine` | History `timestamp <= T`; warmup không burst tín hiệu |
| Khớp ảo | `paper_execution` | Chỉ `actionable`; fill ask+slip / bid−slip; SL first |
| Đọc | API `GET /status`, `GET /paper` | `accountKind=paper` ≠ broker |

`PaperExecutor` là execution boundary duy nhất. Không có `MT5Executor`.

## Forming candle

Nến M15 mở `10:00:00` UTC:

| Thời điểm | Engine |
|-----------|--------|
| 10:00:00 → 10:14:59 | Forming — **không** emit `ClosedCandleEvent`, **không** signal, **không** paper |
| 10:15:00 | Nến `10:00:00` **đã đóng** → `CANDLE_PROCESSED` |

`ClosedCandleEvent.timestamp` = open time của nến đóng (`10:00:00Z`).  
`detected_at` = lúc poll phát hiện (có thể `10:15:00Z` hoặc muộn hơn). **Không** nhầm hai field.

Nếu provider newest-first: engine sort + lọc closed; **không** coi index 0 là closed.

## No look-ahead

Khi evaluate nến `T`:

```
history.timestamp <= T
```

Không dùng forming, không dùng `T+15m`.

## Signal

Sau `ClosedCandleEvent`:

```
history <= T → EMA/RSI/ATR → ema_rsi_atr_v1 → SignalResult
```

`BUY` / `SELL` / `NO_SIGNAL` / `INVALID`. Warmup lịch sử **không** emit burst.

## Risk và paper fill

Chỉ consume `actionable == true`.

| Outcome | Ý nghĩa |
|---------|---------|
| Risk PASS | `PaperExecutor.open_position()` — đúng 1 fill / 1 vị thế ảo cho khóa đó |
| Risk REJECT | `PaperRejection` — không mở vị thế |

Fill (Phase 11.3, không đổi):

* BUY: requested = mid `(bid+ask)/2`; fill = `ask + slippage`
* SELL: fill = `bid - slippage`

Không dùng close nến làm fill.

Mark-to-market: LONG = bid, SHORT = ask.  
`equity = paper.balance + unrealized_pnl` — không thay bằng số dư broker.

## Idempotency

Khóa thực thi: `symbol|timeframe|timestamp|strategy` (`ema_rsi_atr_v1`).

Poll lặp lại cùng nến: không duplicate `ClosedCandleEvent` / `SignalResult` / paper fill / vị thế.

## Restart

File `.paper_execution_state.json` (và cursor nến/tín hiệu) giữ `sessionId`, vị thế, khóa, số dư, PnL. Restart không reset paper vì broker disconnect.

## Broker safety

```
broker_positions_before == broker_positions_after
```

Paper **không** gọi `order_send` / `TRADE_ACTION_*`.

## API / Dashboard

Restart process API sau khi nâng code:

* `GET /api/v1/status` → `candleEngine`, `signalEngine`, `paperExecution` (`accountKind=paper`)
* `GET /api/v1/paper` → PAPER ACCOUNT
* `GET /api/v1/account` / `GET /api/v1/positions` → BROKER ACCOUNT

Không có `POST /order`, `POST /trade`, `POST /execute`.

Dashboard:

* `/dashboard` — BROKER ACCOUNT; banner paper $10,000
* `/dashboard/paper` — cảnh báo **PAPER ONLY — KHÔNG PHẢI VỊ THẾ THẬT TRÊN EXNESS**
* `/dashboard/positions` — BROKER ACCOUNT, không gồm PAPER POSITION

Không có nút BUY / SELL / OPEN / CLOSE / EXECUTE.

Khi `PAPER_EXECUTION_ENABLED=false`, API **không** gắn worker; `GET /paper` mặc định $10,000 (`sessionId=null`). CLI `exness-bot paper` vẫn chạy vòng paper.

## Manual smoke (Windows + MT5)

Chỉ khi XAUUSD đang mở. Không dùng `EXECUTION_MODE=live`.

```bash
cd trading-engine
# DATA_SOURCE=mt5
# EXECUTION_MODE=paper
exness-bot paper
```

Hoặc một chu kỳ:

```bash
exness-bot paper --once
```

### Checklist

**A. Kết nối** — server, canonical `XAUUSD` → broker symbol, `CONNECTED`.

**B. Forming** — `ClosedCandleEvent=0`, signal=0, paper=0.

**C. Nến đóng** — ghi timestamp, `detected_at`, OHLC; 1 `ClosedCandleEvent`.

**D. Signal** — EMA20/50/200, RSI14, ATR14, action, actionable. `NO_SIGNAL` hợp lệ.

**E. Risk** — PASS hoặc REJECT (cả hai hợp lệ).

**F. Paper fill** — nếu actionable + PASS: đúng 1 execution, 1 vị thế ảo (side, entry, SL, TP, size, key).

**G. Poll tiếp** — không duplicate.

**H. Broker** — số vị thế trước = sau.

**I. Dashboard** — paper ≠ broker.

Nếu không chờ được phiên mở: chạy unit/integration fake provider; ghi MT5 live step là **NOT TESTED**; status phase **CONDITIONAL**. Không giả mạo evidence.

## Automated tests

`trading-engine/tests/unit/test_live_paper_session.py` (FakeClock, không phụ thuộc MT5):

* `test_live_pipeline_uses_closed_candle_only`
* `test_live_pipeline_no_lookahead`
* `test_live_pipeline_signal_to_paper`
* `test_live_pipeline_risk_rejection`
* `test_live_pipeline_duplicate_poll_is_idempotent`
* `test_live_pipeline_restart_preserves_state`
* `test_live_pipeline_does_not_touch_broker_positions`

Unit test **không** phải bằng chứng MT5 live.

## Known limitations

* Weekend / phiên đóng: không có nến M15 mới → forming→closed live **NOT TESTED**.
* JSON persistence không transactional.
* Fill paper khác backtest (quote lúc phát hiện vs close nến).
* API worker tắt thì Dashboard không hiện session CLI.
