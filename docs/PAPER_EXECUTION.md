# Paper Execution (Phase 11.3)

Tài liệu này mô tả **Paper Execution Engine**: nhận `SignalResult` actionable, đánh giá rủi ro, rồi mô phỏng khớp lệnh và vị thế **ảo**. Engine **không** gửi lệnh tới Exness / MT5.

## Kiến trúc

```
SignalResult (actionable + executable)
    ↓
ExecutionService.consume / consume_results
    ↓
RiskManager.assess()
    ↓
ExecutionIntent          # không có fill_price
    ↓
persist IN_FLIGHT
    ↓
PaperExecutor.submit()   # ExecutionPort — tự tạo fill
    ↓
ExecutionAck(FILLED) → VirtualOrder → VirtualPosition → VirtualExit
    ↓
PnL / Equity / Journal / IntentRecord (JSON schemaVersion 3)
```

- Signal Engine **không** biết execution.
- `PaperExecutor` **không** import trading adapter / trading client; **không** gọi trading mutation APIs.
- MT5 (nếu có) chỉ dùng **read-only** (`TradingDataProvider` / `MT5ReadOnlyClient`).
- Chưa có `MT5Executor`. `ExecutionPort.submit(intent, quote=…)` là boundary cho phase live sau.

Phase 11.7: catch-up gate tại `ExecutionService` (`executable`, `CATCHUP_IGNORED`, `consume_results`).

Phase 11.8: `IntentStore` persist `IN_FLIGHT` trước `submit`; restart `IN_FLIGHT→UNKNOWN` không resubmit; validation quote/volume/stops/SL-TP trước side effect; `FakeExecutionPort` chỉ cho tests.

Phase 11.9: `BrokerExecutionQuery` reconcile UNKNOWN read-only (`CONFIRMED_*` mới được FILLED/REJECTED); `ExecutionPort` chỉ `submit()`; legacy `exness-bot run` cần `ALLOW_LEGACY_RUN=true`.

Phase 12.1: `DurableIntentStore` — transition tường minh, atomic tmp+fsync+replace, fail-closed corrupt/schema; `schemaVersion` vẫn = 3.

Chạy độc lập:

```bash
exness-bot paper          # vòng poll: nến → thoát vị thế → tín hiệu → paper
exness-bot paper --once   # warmup + một lần poll, rồi thoát
```

Cấu hình:

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `EXECUTION_MODE` | `paper` | Mode khớp lệnh. Giá trị khác (`live`, …) **fail closed** — không fallback live |
| `PAPER_EXECUTION_ENABLED` | `false` | Bật vòng paper trên API. Tắt mặc định để TestClient không spawn thread |

Khi `PAPER_EXECUTION_ENABLED=true`, API chạy **một** thread: candle + signal + paper. Không bật thêm `SIGNAL_ENGINE_ENABLED` / `CANDLE_ENGINE_ENABLED` trên cùng process (tránh double-poll).

Không có `POST /trade`, `POST /order`, `POST /execute`. Khớp lệnh chỉ theo sự kiện `SignalResult` → `ExecutionService.consume`.

## Tiêu thụ tín hiệu

Chỉ consume / execute khi:

* `SignalResult.actionable == true`
* `SignalResult.executable == true`
* `emission == SIGNAL_EMISSION`
* `signal` ∈ {`BUY`, `SELL`}

`NO_SIGNAL` / `INVALID` → `IGNORED`.  
Catch-up / historical / non-executable → `CATCHUP_IGNORED`.  
`consume_results` chỉ cho phép **một** latest executable trong batch.

`NO_SIGNAL` và `INVALID` bị bỏ qua (`IGNORED`). Không khớp lệnh theo text hiển thị.

### Idempotency

Khóa: `symbol|timeframe|candle_timestamp|strategy_version` (`SignalResult.idempotency_key`).

Cùng khóa lần hai → `DUPLICATE`, không mở vị thế thứ hai. Key được ghi cả khi **FILL** lẫn **REJECT** để không retry tín hiệu đã từ chối.

### Catch-up

Paper chỉ consume `actionable`. Signal Engine Phase 11.2 chỉ emit nến **mới nhất** trong batch catch-up. Do đó 10:15 / 10:30 / 10:45 / 11:00 miss **không** tạo bốn vị thế ảo.

Thứ tự trên mỗi nến đóng mới:

1. Kiểm tra SL/TP vị thế đang mở (`on_closed_candle`)
2. `SignalEngine.process_events`
3. `ExecutionService.consume` từng `SignalResult`

## Định giá vào lệnh

Không coi giá trên `SignalResult` là fill đảm bảo.

| Thuật ngữ | Công thức |
|-----------|-----------|
| `requested_price` | Mid = `(bid + ask) / 2` từ quote read-only hiện tại |
| BUY fill | `ask + slippage` |
| SELL fill | `bid - slippage` |
| Spread | Ưu tiên `SymbolInfo.spread` / spread nến; fallback `BacktestConfig.spread_points` |
| Slippage | `BacktestConfig.slippage_points` (mặc định 1 point) |

Ví dụ XAUUSD: bid 2350.10, ask 2350.30, slippage 1 point (`point=0.01`) → requested 2350.20, BUY fill 2350.31.

Giả định này **cố ý khác** backtest (backtest fill quanh close nến tín hiệu). Paper dùng **quote thị trường tại thời điểm phát hiện**, vì bot live sẽ nhìn bid/ask chứ không tin giá trên tín hiệu.

Thoát lệnh: giá chạm SL/TP ± half-spread ± slippage **bất lợi** cho trader (cùng tinh thần backtest `exit_costs`).

## SL / TP và sizing

Tái sử dụng `RiskManager` / `calculate_stop_loss` / `calculate_take_profit` / `calculate_position_size`.

- SL = ATR × `ATR_SL_MULTIPLIER` (1.5)
- TP = RR `REWARD_RISK_RATIO` (2.0)
- Volume = `(equity × risk%) / (SL distance × contract)` — **không** hardcode 0.01 lot
- ATR/SL không hợp lệ → **không mở** vị thế (`INVALID_SL`)

Defaults dự án (không invent):

* Số dư ban đầu: $10,000
* Risk mỗi lệnh: 0.5%
* Max vị thế mở: 1
* Max lỗ ngày: 2%
* Max drawdown: 5%
* Max lot: 1.0

## Thoát lệnh

Mỗi `ClosedCandleEvent` (nến **sau** nến vào lệnh):

* LONG: SL nếu `low <= SL`; TP nếu `high >= TP`
* SHORT: SL nếu `high >= SL`; TP nếu `low <= TP`
* Cùng nến chạm cả SL và TP: **SL trước** (quy tắc conservative hiện có)

Không kiểm tra exit trên nến có `timestamp <= opened_at` (nến tín hiệu).

Lý do exit Phase 11.3: `SL`, `TP`. Enum còn `MANUAL` / `END_OF_SESSION` / `RISK_LIMIT` nhưng chưa dùng.

## Chi phí

Tái sử dụng `BacktestConfig`:

* Commission: `commission_per_lot × volume × 2` lúc **đóng** (round-trip), trừ vào net PnL
* Swap: `swap_per_lot_per_day × volume` khi vị thế **qua ngày lịch** (`candle.date != last_calendar_day`)
* Mặc định commission/swap = 0 (giống backtest) trừ khi cấu hình khác

## Equity

| Đại lượng | Công thức |
|-----------|-----------|
| `balance` (`cash_balance`) | Chỉ đổi khi đóng lệnh: `+= net_pnl` |
| `unrealized_pnl` | Mark-to-market: LONG dùng bid, SHORT dùng ask |
| `equity` | `balance + unrealized_pnl` |
| `daily_pnl` | `equity − day_start_equity` |
| `drawdown_pct` | `(peak_equity − equity) / peak_equity × 100` |

Không nhầm balance với equity khi còn vị thế mở.

## Risk

Trước khi mở:

`SignalResult` → `RiskManager.assess()` → approved / rejected.

Từ chối **không** tạo vị thế. Mã quan sát được:

* `MAX_DAILY_LOSS`
* `MAX_DRAWDOWN`
* `MAX_OPEN_POSITIONS`
* `POSITION_SIZE_LIMIT`
* `INVALID_SL`
* `INVALID_RISK`

Journal từ chối phải nhìn như tín hiệu bị reject, không phải giao dịch đã khớp.

## Persistence

File JSON `.paper_execution_state.json` (write `.tmp` rồi `replace`).

Snapshot gồm: số dư, realized PnL, peak, day start, khóa idempotency, vị thế mở, lệnh, exit, rejection.

**Thứ tự an toàn:** mutate in-memory (position **và** idempotency key) → **một** lần ghi file.

JSON **không** transactional. Crash giữa chừng có thể mất cả position lẫn key (tín hiệu có thể khớp lại) hoặc giữ cả hai. Đây **không** phải durability production.

Log `WARNING paper_execution_state_recovery` khi load file hiện có.

## Paper Trading Session (Phase 11.4)

Mỗi file state có một phiên giấy:

| Field | Ý nghĩa |
|-------|---------|
| `sessionId` | UUID (hoặc `paper-{unix}` nếu file cũ chưa có id) |
| `startedAt` | Thời điểm tạo phiên |
| `initialBalance` / `balance` / `equity` | Số dư giấy — **không** đọc từ broker |
| `unrealizedPnl` / `realizedPnl` / `dailyPnl` / `drawdownPct` | PnL giấy |
| `openPositions` | Số vị thế ảo đang mở |
| `executionCount` | Số lệnh ảo đã fill (`orders`) |
| `signalCount` | Số lần `consume` (kể cả IGNORED / DUPLICATE) |
| `candlesProcessed` | Số lần `on_closed_candle` |
| `rejectedCount` | Số lần risk reject |

Restart cùng file JSON: **cùng** `sessionId`, cùng vị thế, cùng khóa idempotency → không duplicate fill.

Mất kết nối broker (`get_tick` = None): không reset paper state; mark-to-market bỏ qua cho đến khi có tick.

## Khác biệt: backtest / paper / MT5 live quotes

| | Backtest | Paper execution | MT5 live (chỉ đọc) |
|---|----------|-----------------|--------------------|
| Nến | File lịch sử, không forming | Closed candle từ provider (bỏ forming) | Cùng Candle Engine |
| Fill vào lệnh | Gần close nến tín hiệu ± spread/slippage | Bid/ask **tại lúc phát hiện**: BUY = ask+slippage, SELL = bid−slippage | Quote `symbol_info_tick` — **không** gửi lệnh |
| Mark-to-market | Thường close nến | LONG = bid, SHORT = ask | Bid/ask thật, chỉ để hiển thị / paper mark |
| SL/TP | Closed candle, SL first nếu cùng nến | Giống backtest trên nến **sau** nến vào lệnh | Không modify SL/TP trên broker |
| Tài khoản | Simulated equity trong report | PAPER ACCOUNT $10,000 JSON | BROKER ACCOUNT Exness |
| Persistence | Báo cáo run | `.paper_execution_state.json` atomic `.tmp`+replace | Terminal MT5 |

Paper **cố ý** khác backtest ở fill giá: bot vận hành nhìn bid/ask hiện tại, không tin giá trên tín hiệu.

## API / Dashboard

* `GET /api/v1/status` → `candleEngine`, `signalEngine`, `paperExecution` (`accountKind=paper`, `sessionId`)
* `GET /api/v1/paper` → PAPER ACCOUNT + `positions[]` (PAPER POSITION)
* `GET /api/v1/account` / `GET /api/v1/positions` → BROKER ACCOUNT / vị thế Exness

Dashboard: trang **Paper Trading**, badge **PAPER / RESEARCH**, cảnh báo **"PAPER ONLY — KHÔNG PHẢI VỊ THẾ THẬT TRÊN EXNESS"**. Vị thế giấy **không** trộn với bảng vị thế Exness. Không gọi API mutation từ Dashboard.

## Logging

| Level | Event |
|-------|--------|
| INFO | `paper_execution_started` |
| INFO | `paper_order_filled` |
| INFO | `paper_position_closed` |
| INFO | `paper_execution_rejected` |
| DEBUG | `paper_position_marked_to_market` |
| WARNING | `paper_execution_state_recovery` |

Không log mật khẩu / secret.

## Biên an toàn

Phase 11.4 kết thúc tại validation:

```
Market Data → Closed Candle → Indicators → Strategy → Signal → Risk → Paper Execution → Virtual Position
```

**Không** có `Signal → Real MT5 Order`. Không có công tắc live trading.
