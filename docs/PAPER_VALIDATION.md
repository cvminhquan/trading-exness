# Paper Trading Validation (Phase 11.4)

Checklist xác minh pipeline **PAPER / RESEARCH** trên MT5 read-only. Không gửi lệnh.

## Cấu hình

```
DATA_SOURCE=mt5
EXECUTION_MODE=paper
PAPER_EXECUTION_ENABLED=true
```

`EXECUTION_MODE=live` (hoặc giá trị khác) **fail closed** — không fallback live.

Không bật cùng lúc `SIGNAL_ENGINE_ENABLED` / `CANDLE_ENGINE_ENABLED` trên process API khi paper đã bật (tránh double-poll).

## Command

```bash
cd trading-engine
exness-bot paper --once
```

Vòng liên tục (mỗi M15):

```bash
exness-bot paper
```

Trong mỗi chu kỳ:

1. Đọc candles
2. Bỏ forming candle
3. Detect closed candle
4. EMA20 / EMA50 / EMA200
5. RSI14
6. ATR14
7. `ema_rsi_atr_v1`
8. Nếu actionable → `RiskManager.assess()`
9. Nếu accepted → `PaperExecutor.open_position()`
10. Cập nhật virtual position / equity

**Không** dùng MT5 trading API (`order_send`, `TRADE_ACTION_*`).

## Broker before / after

Ghi số vị thế broker **trước** và **sau** `paper --once`. Kỳ vọng: không đổi.

Log `paper_validation_summary` gồm:

* `session_id`
* `candles_processed` / `signal_count` / `execution_count` / `rejected_count`
* `paper_open` / `realized_pnl` / `unrealized_pnl` / `drawdown_pct`
* `broker_positions_before` / `broker_positions_after` / `broker_positions_unchanged`

## Restart

1. Chạy `paper --once`
2. Ghi `sessionId` và `executedKeys` trong `.paper_execution_state.json`
3. Chạy lại `paper --once`
4. Cùng `sessionId`; không thêm fill cho cùng khóa tín hiệu

## API

Restart process API sau khi nâng code:

* `GET /api/v1/status` → `candleEngine`, `signalEngine`, `paperExecution`
* `GET /api/v1/paper` → `accountKind=paper` (khác `GET /api/v1/account`)

Dashboard `/dashboard/paper` chỉ đọc. Không POST trade/order.

## Weekend / phiên đóng

Nếu Candle Engine trả `CANDLE_ALREADY_PROCESSED` (không có nến đóng mới): ghi **NOT TESTED** cho forming → closed → fill. Không suy đoán fill.
