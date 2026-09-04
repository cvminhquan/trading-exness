# Phase 11.3 Report — Paper Execution Engine

**Ngày xác nhận:** 2026-08-29  
**Phạm vi:** Paper execution (`exness_bot.paper_execution`) trên biên `SignalResult` actionable  
**Status: CONDITIONAL**

Lý do không ghi PASS:

- Pytest / ruff / mypy đã chạy trong phiên này và **đạt**.
- Smoke Windows + MT5 **đã chạy** (`exness-bot paper --once`): kết nối Exness demo read-only, warm start, **0 paper fill** vì `CANDLE_ALREADY_PROCESSED`.
- Nến đóng **mới** trong phiên (forming → closed → tín hiệu actionable → 1 vị thế ảo) **chưa** quan sát: 2026-08-29 là thứ Bảy; Candle Engine trả `CANDLE_ALREADY_PROCESSED`.
- Dashboard: nav + trang Paper Trading + badge **PAPER / RESEARCH** **đã** quan sát trên `localhost:3000`. `GET /api/v1/paper` trên process API **đang chạy** trả 404 vì process đó chưa restart với code 11.3.

Không suy đoán các hạng mục chưa có bằng chứng.

Tài liệu thiết kế: [`PAPER_EXECUTION.md`](PAPER_EXECUTION.md).

---

## Implementation summary

Đã thêm Paper Execution, **không** gửi lệnh MT5:

| Thành phần | Vị trí |
|------------|--------|
| Models / port / pricing / state | `src/exness_bot/paper_execution/` |
| `PaperExecutor` (`ExecutionPort`) | `executor.py` |
| `ExecutionService` | `service.py` |
| CLI | `exness-bot paper` / `--once` |
| API | `GET /api/v1/status` → `paperExecution`; `GET /api/v1/paper` |
| Dashboard | `/dashboard/paper`, badge PAPER / RESEARCH |
| Cấu hình | `EXECUTION_MODE=paper` (fail closed); `PAPER_EXECUTION_ENABLED` mặc định `false` |

Luồng:

```
CandleEngine.poll()
  → on_closed_candle (SL/TP, SL first nếu cùng nến)
SignalEngine.process_events
  → SignalResult
ExecutionService.consume (chỉ actionable)
  → RiskManager.assess
  → PaperExecutor.open_position
```

`exness-bot paper` gọi `create_trading_data_provider` + candle + signal + paper. **Không** gọi `create_trading_engine` / `MT5Adapter`.

---

## Architecture

Hướng phụ thuộc:

* Signal Engine → `TradingDataProvider` (không đổi, không import paper)
* Execution Service → `RiskManager` + `PaperExecutor`
* Paper package **không** chứa `MT5Adapter` / `TradingClient` / `order_send` / `TRADE_ACTION_*`

`ExecutionPort`: `open_position` / `close_position` / `get_open_positions` / `get_account_state`. **Không** implement live executor.

---

## Paper execution model

* Market order ảo fill ngay (`FILLED`)
* Không pending order
* Một vị thế mở mặc định (`MAX_OPEN_POSITIONS=1`)
* Idempotency: `symbol|timeframe|timestamp|strategy` — ghi key cả FILL lẫn REJECT

Catch-up: chỉ consume `actionable=True`. Signal Engine 11.2 chỉ emit nến latest.

---

## Risk integration

Tái sử dụng `RiskManager.assess()`. Không duplicate rule.

Từ chối ghi `PaperRejection` + mã `MAX_DAILY_LOSS` / `MAX_DRAWDOWN` / `MAX_OPEN_POSITIONS` / `POSITION_SIZE_LIMIT` / `INVALID_SL` / `INVALID_RISK`.

---

## Position sizing

`calculate_position_size(equity, risk 0.5%, SL ATR, contract)`. Không hardcode 0.01 lot. ATR/SL invalid → không mở.

Defaults: balance $10,000, risk 0.5%, max positions 1, max daily loss 2%, max drawdown 5%, max lots 1.0.

---

## Entry / SL / TP / spread / slippage / commission / swap

* `requested_price` = mid `(bid+ask)/2`
* BUY fill = `ask + slippage`; SELL fill = `bid - slippage`
* Không tin giá trên `SignalResult` là fill đảm bảo
* Khác backtest (backtest fill quanh close nến) — **có document**, không copy thầm
* SL = ATR × 1.5; TP = RR 2.0
* Cùng nến SL+TP → **SL first**
* Commission round-trip lúc đóng; swap khi qua ngày lịch
* Defaults chi phí giống `BacktestConfig` (commission/swap 0, slippage 1 point)

---

## PnL / Equity

| Đại lượng | Công thức |
|-----------|-----------|
| `balance` | Chỉ đổi khi đóng: `+= net_pnl` |
| `unrealized_pnl` | LONG = bid; SHORT = ask |
| `equity` | `balance + unrealized_pnl` |
| `daily_pnl` | `equity − day_start_equity` |
| `drawdown_pct` | `(peak − equity) / peak × 100` |

---

## Persistence

JSON `.paper_execution_state.json`. Ghi `.tmp` rồi `replace`. Mutate in-memory (position **và** key) rồi **một** lần ghi.

JSON **không** transactional. Crash có thể mất cả hai hoặc giữ cả hai. Không phải durability production.

---

## API

Read-only. Không `POST /trade` / `/order` / `/execute`.

Bằng chứng test (TestClient process mới):

* `test_status_connected_mock` — `paperExecution.status == STOPPED`, `mode == paper`, `openPositions == 0`
* `test_paper_readonly_snapshot`
* `test_paper_has_no_mutation_routes`

Process API đang chạy (`127.0.0.1:8000`) **chưa** restart: `GET /api/v1/status` không có `paperExecution`; `GET /api/v1/paper` 404 trên Dashboard.

---

## Dashboard

Code: nav Paper Trading; `/dashboard/paper`; badge **PAPER / RESEARCH — KHÔNG PHẢI VỊ THẾ EXNESS**; Tổng quan nhãn `Vị thế đang mở · Exness`.

Xác minh trình duyệt (2026-08-29, `localhost:3000`, **Nguồn API**):

| Bề mặt | Kết quả |
|--------|---------|
| Nav Paper Trading | Có, trang hiện tại khi mở `/dashboard/paper` |
| Heading + badge + banner $10,000 | Có |
| Bảng nhật ký / số dư giấy | **Không tải** — `Không tìm thấy tài nguyên yêu cầu` (API cũ) |
| Header `PAPER ONLY` | Chưa — `paperExecution` không có trên status API cũ |
| Tổng quan nhãn Exness | Có `Vị thế đang mở · Exness` |

---

## Tests

`tests/unit/test_paper_execution.py` phủ các case spec (BUY/SELL, ignore, duplicate, risk gates, sizing, spread/slippage, commission/swap, SL/TP/SL-first, equity, persistence, catch-up, E2E BUY→TP, static safety, fail-closed `EXECUTION_MODE=live`).

---

## pytest

```
410 passed, 5 skipped, 1 deselected
```

Chạy: `python -m pytest` trong `trading-engine` (2026-08-29).

---

## ruff

```
ruff check src tests
All checks passed!
```

---

## mypy

```
mypy src
Success: no issues found in 132 source files
```

---

## Safety audit

Tìm trong `src/exness_bot/paper_execution/` (2026-08-29): `order_send`, `TRADE_ACTION_DEAL`, `TRADE_ACTION_PENDING`, `TRADE_ACTION_SLTP`, `TRADE_ACTION_REMOVE`, `MT5Adapter`, `TradingClient`.

**Không khớp.**

| Đường | Kết quả |
|-------|---------|
| `paper_execution/` | Không `order_send` / `TRADE_ACTION_*` / adapter trading |
| `handle_paper` | `create_trading_data_provider` — không `MT5Adapter` |
| `handle_run` | Vẫn import `MT5Adapter` (đường cũ, **không** phải 11.3) |

Test: `test_paper_executor_cannot_call_mt5_trading_apis`, `test_execution_interface_does_not_depend_on_mt5`, `test_signal_engine_remains_independent_of_execution`.

---

## Windows + MT5 smoke test

Lệnh: `exness-bot paper --once`  
Thời điểm: 2026-08-29T10:22:43Z (thứ Bảy)

```
mt5_readonly_initialized
mt5_connection_manager_connected login=463864158 server=Exness-MT5Trial17
paper_execution_started mode=paper
signal_engine_started mode=warm
signal_engine_warmup results=0 status=WARMUP_COMPLETE
paper_execution_once
  candle_status=CANDLE_ALREADY_PROCESSED
  paper_open=0
  paper_balance=10000.0
  paper_equity=10000.0
  last_execution=None
  broker_positions_before=3
  broker_positions_after=3
paper_execution_stopped
```

| Hạng mục | Kết quả |
|----------|---------|
| MT5 connected (read-only) | Có |
| Candle received (mới trong phiên) | **NOT TESTED** — `CANDLE_ALREADY_PROCESSED` |
| Signal generated (mới) | Không — warmup 0, không nến mới |
| Paper order simulated | Không — không có tín hiệu mới; **không bịa** |
| Real MT5 order | Không trên đường `paper`: CLI không `order_send`; số vị thế broker **3 → 3** |

Kết luận smoke: **PARTIAL** — kết nối + paper loop không burst + không đổi vị thế MT5. Fill ảo từ nến live: **NOT TESTED**.

---

## Known limitations

1. JSON state không transactional.
2. Quote fill khác backtest (backtest dùng close nến).
3. Contract spec lấy từ `BacktestConfig` + bid/ask tick; không gọi adapter trading để lấy `symbol_info` đầy đủ.
4. `PAPER_EXECUTION_ENABLED` mặc định tắt.
5. Smoke forming→closed→paper fill trong phiên XAUUSD M15 **NOT TESTED**.
6. Process API đang chạy chưa restart code 11.3.
7. Chưa live executor, chưa công tắc live.
8. Swap/commission mặc định 0 trừ khi cấu hình (giống backtest).

---

## Phase 11.4 readiness

**Chưa sẵn sàng live execution.** Biên 11.3 kết thúc tại:

```
Market Data → Closed Candle → Indicators → Strategy → Signal → Risk → Paper Execution → Virtual Position → Virtual PnL
```

Không có `Signal → Real MT5 Order`.

Bắt buộc trước 11.4 (nếu có):

- Review riêng executor live implementing `ExecutionPort`
- Không nối `PaperExecutor` vào `order_send`
- `EXECUTION_MODE` vẫn fail closed với giá trị không hỗ trợ
- Restart API rồi xác minh `paperExecution` + `GET /api/v1/paper`
- Hoàn tất smoke nến live trong phiên trước khi tin vòng đời đầy đủ
