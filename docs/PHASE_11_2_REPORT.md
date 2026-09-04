# Phase 11.2 Report — Signal Engine

**Ngày xác nhận:** 2026-08-29  
**Phạm vi:** Signal Engine research-only (`exness_bot.signal_engine`) trên biên `ClosedCandleEvent`  
**Status: CONDITIONAL**

Lý do không ghi PASS:

- Pytest / ruff / mypy đã chạy trong phiên này và **đạt**.
- Smoke Windows + MT5 **đã chạy** (`exness-bot signals --once`), kết nối Exness demo, cold start rồi warm start, **0 tín hiệu lịch sử**.
- Nến đóng **mới** trong phiên (forming → closed → đúng 1 `SignalResult`) **chưa** quan sát: thị trường XAUUSD M15 đóng cuối tuần; Candle Engine trả `CANDLE_ALREADY_PROCESSED`.
- Header Dashboard `signalEngine` trên process API **mới** chưa xác minh (process đang chạy chưa restart code 11.2). Badge **TÍN HIỆU NGHIÊN CỨU — KHÔNG PHẢI LỆNH** trên Tổng quan / Chiến lược **đã** quan sát.

Không suy đoán các hạng mục chưa có bằng chứng.

Tài liệu thiết kế: [`SIGNAL_ENGINE.md`](SIGNAL_ENGINE.md).

---

## Implementation summary

Đã thêm Signal Engine, không khớp lệnh:

| Thành phần | Vị trí |
|------------|--------|
| Engine / adapter / state / loop | `src/exness_bot/signal_engine/` |
| Chiến lược | `EmaRsiAtrStrategy` (`ema_rsi_atr_v1`) — không đổi `_decide` |
| Chỉ báo | `IndicatorCalculator` (EMA 20/50/200, RSI 14, ATR 14) |
| CLI | `exness-bot signals` / `--once` |
| API | `GET /api/v1/status` → `signalEngine`; `GET /api/v1/strategy` đọc `last_result` |
| Dashboard | `SignalCard` nhãn nghiên cứu; `TopHeader` status tối thiểu |
| Cấu hình | `SIGNAL_ENGINE_ENABLED` mặc định `false` |

Luồng:

```
CandleEngine.poll()
  → ClosedCandleEvent (chỉ nến đóng)
SignalEngine.process_events
  → IndicatorCalculator.compute (history <= T)
  → EmaRsiAtrStrategy.evaluate
  → SignalResult (BUY | SELL | NO_SIGNAL | INVALID)
```

`exness-bot signals` gọi `create_trading_data_provider` + `build_candle_engine` + `build_signal_engine`. **Không** gọi `create_trading_engine` / `MT5Adapter`.

---

## Architecture

Không tạo Candle Engine thứ hai, không tạo MT5 client thứ hai.

Hướng phụ thuộc: Signal Engine → `TradingDataProvider` (mock / backtest / `MT5TradingDataProvider` read-only).

Không: Signal Engine → `MT5Adapter` / `TradingClient`.

---

## Strategy

Tái sử dụng `ema_rsi_atr_v1`. Không invent chiến lược mới. Không đổi tham số.

Adapter (`signal_engine/adapter.py`):

- `HOLD` → `NO_SIGNAL`
- ATR là **cổng hợp lệ** trước BUY/SELL (chiến lược gốc không dùng ATR trong `_decide`)
- Điều kiện có cấu trúc (`SignalCondition`)

Backtest execution (spread / slippage / commission / swap / sizing / risk) **không** đụng.

---

## Indicators

Cùng `IndicatorCalculator` với backtest. Test so sánh prefix historical vs incremental trong dung sai `1e-9`.

Không look-ahead: history chỉ `timestamp <= T`. Nến forming bị `FORMING_REJECTED`.

---

## Warm-up behavior

`warmup_bars` lấy từ `BacktestConfig.from_settings` → mặc định **200**. Không hardcode giá trị warmup thứ hai.

Cửa sổ: `CANDLE_HISTORY_COUNT` (250).

Lịch sử warmup **không** emit BUY/SELL.

Test production-like: `test_insufficient_history` với `warmup_bars=200`. Test critical dùng `warmup_bars=4` vì 5 nến không đủ EMA200.

---

## Cold start

Load nến đóng → warmup → neo cursor = nến đóng cuối → `results=()`.

Bằng chứng test: `test_cold_start`, `test_historical_warmup_produces_no_signals`.

Bằng chứng MT5: lần 1 `mode=cold`, `results=0`, `WARMUP_COMPLETE`.

---

## Warm start

File `.signal_engine_state.json`. Khôi phục cursor; không replay nến đã xử lý. Đổi `strategy` version → reset cursor.

Bằng chứng test: `test_warm_start`.

Bằng chứng MT5: lần 2 `mode=warm`, `results=0`.

---

## Catch-up / signal emission policy

| Khái niệm | Hành vi đã triển khai |
|-----------|------------------------|
| `INDICATOR_CATCHUP` | Nến miss (không phải nến mới nhất) cập nhật history + cursor, **không** tạo `SignalResult` |
| `SIGNAL_EMISSION` | Chỉ nến đóng mới nhất trong batch → đúng 1 `SignalResult` |

Reconnect 10:15 đã xử lý, rồi 10:30 / 10:45 / 11:00: `catchup_count=2`, một kết quả tại 11:00.

Bằng chứng test: `test_missed_candle_catchup_no_burst`, `test_reconnect_catchup_emits_only_latest`, `test_chronological_processing`.

Bằng chứng MT5 miss nhiều nến khi reconnect thật: **NOT TESTED**.

---

## Signal idempotency

Khóa: `symbol\|timeframe\|timestamp\|ema_rsi_atr_v1`.

Bằng chứng test: `test_signal_idempotency`, `test_repeated_candle`, `test_strategy_version_included_in_idempotency`.

Bằng chứng MT5 poll lặp: lần 2 `CANDLE_ALREADY_PROCESSED`, `results=0` — không nhân tín hiệu. Nến đóng **mới** trong phiên: **NOT TESTED**.

---

## API

`GET /api/v1/status` thêm `signalEngine` (read-only). Không endpoint mutation mới.

Bằng chứng test: `test_status_connected_mock` — `signalEngine.status == STOPPED`, `strategy == ema_rsi_atr_v1`, `dataSource == MOCK`, `lastSignal == null` (engine không bật).

`SIGNAL_ENGINE_ENABLED` không có trong `.env` lúc xác nhận → mặc định `false`.

Khi `true`, API chạy **một** thread poll candle+signal, không double-poll với `CANDLE_ENGINE_ENABLED`.

---

## Dashboard

Code: `signalEngine` optional trên session schema; `signalActionSchema` thêm `NO_SIGNAL` / `INVALID`; `SignalCard` badge nghiên cứu; `TopHeader` status tối thiểu.

Xác minh trình duyệt (2026-08-29, Dashboard `localhost:3000`, **Nguồn API** tới process API đang chạy):

| Bề mặt | Kết quả |
|--------|---------|
| Tổng quan — `SignalCard` | Có nhãn **TÍN HIỆU NGHIÊN CỨU — KHÔNG PHẢI LỆNH**; action **Giữ** (HOLD) |
| Chiến lược — `ema_rsi_atr_v1`, EMA/RSI/ATR | Có; giá trị `—` vì engine chưa emit trên process API này |
| Header `signalEngine` | **Không hiện** — process API hiện tại chưa trả field / chưa bật `SIGNAL_ENGINE_ENABLED` |

Không coi đây là xác minh Signal Engine live trên API mới (cần restart API với code 11.2). Badge nghiên cứu trên UI **đã** quan sát.

---

## Automated tests

File chính: `tests/unit/test_signal_engine.py` — **27** test.

Phủ (đúng yêu cầu spec §25–27):

1. insufficient history  
2. indicator warm-up (0 tín hiệu)  
3. forming rejected  
4. closed accepted  
5. BUY  
6. SELL  
7. NO_SIGNAL  
8–12. invalid EMA / RSI / ATR / NaN / infinity  
13. no look-ahead  
14–15. idempotency / repeated candle  
16–17. warm start / cold start  
18. historical warmup no signals  
19–20. catch-up / chronological  
21. strategy determinism  
22. indicator consistency with backtest  
23. strategy version in key  
24. source read-only (toàn bộ package `signal_engine/`)  
25. critical 10:00…11:00 warmup → 11:15 đúng 1 result  
26. reconnect: chỉ nến latest emit  

Thêm: `test_candle_engine_defaults` assert `signal_engine_enabled is False`; field `signalEngine` trên `/api/v1/status`.

---

## pytest result

Lệnh (cwd `trading-engine`, 2026-08-29, phiên báo cáo):

```text
.\.venv\Scripts\python.exe -m pytest -q --tb=line
```

Kết quả: **379 passed**, 5 skipped, 1 deselected, 1 warning (Starlette/httpx TestClient deprecation).  
**exit code 0.**

`addopts = -m 'not mt5 and not integration'` — 5 skipped / 1 deselected là marker sẵn có, không phải fail Phase 11.2.

Backtest tests nằm trong suite và **đạt** — không đổi execution model.

---

## ruff result

```text
.\.venv\Scripts\python.exe -m ruff check src tests
```

**All checks passed.** exit code 0.

---

## mypy result

```text
.\.venv\Scripts\python.exe -m mypy src
```

**Success: no issues found in 122 source files.** exit code 0.

---

## Windows + MT5 smoke test

**Đã chạy** trên Windows, `DATA_SOURCE=mt5`, terminal Exness. **Không** PASS toàn bộ checklist spec §29.

Lệnh:

```text
.\.venv\Scripts\python.exe -m exness_bot.cli signals --once
```

Lần 1 (2026-08-29T10:05:24Z):

| Hạng mục spec | Kết quả | Bằng chứng |
|---------------|---------|------------|
| MT5 connected | Có | `mt5_connection_manager_connected` server `Exness-MT5Trial17` |
| Closed candle received (mới) | **NOT TESTED** | `candle_status=CANDLE_ALREADY_PROCESSED` |
| Indicators calculated (warmup) | Có | `signal_engine_started mode=cold`, `WARMUP_COMPLETE`, `results=0` |
| Strategy evaluated on new closed candle | **NOT TESTED** | không có `ClosedCandleEvent` mới |
| Signal displayed | Không có tín hiệu mới | `results=0` — đúng với cold start / already-processed |
| Next poll không duplicate | Có (trong điều kiện already-processed) | lần 2 `mode=warm`, `results=0` |
| Không đặt lệnh | Có trên đường `signals` | CLI không gọi `order_send` |

Lần 2 (2026-08-29T10:05:39Z): `mode=warm`, `CANDLE_ALREADY_PROCESSED`, `results=0`.

Kết luận smoke: **PARTIAL** — kết nối + warmup không burst + warm start idempotent. Chuyển nến live trong phiên: **NOT TESTED**.

---

## Safety audit

Tìm trong repo (2026-08-29): `order_send`, `TRADE_ACTION_DEAL`, `TRADE_ACTION_PENDING`, `TRADE_ACTION_SLTP`, `TRADE_ACTION_REMOVE`.

### Code execution sẵn có (không phải Phase 11.2)

| Vị trí | Nội dung |
|--------|----------|
| `broker/mt5/trading_client.py` | `order_send` |
| `broker/mt5/adapter.py` | gọi `order_send` |
| `broker/mt5/mapper.py` | `MT5_TRADE_ACTION_DEAL` / `SLTP` |
| `cli.py` → `handle_run` | `MT5Adapter` + `create_trading_engine` |

### Đường Phase 11.2 (research-only)

| Đường | Kết quả grep |
|-------|----------------|
| `signal_engine/` | **Không** khớp `order_send` / `TRADE_ACTION_*` / `MT5Adapter` / `TradingClient` |
| `handle_signals` | `create_trading_data_provider` — không `MT5Adapter` |
| `api/` | **Không** khớp `order_send` / `TRADE_ACTION_*` |

Kết luận audit: Phase 11.2 **remain READ-ONLY / SIGNAL ONLY**. Code đặt lệnh cũ vẫn trong repo nhưng **không** nằm trên đường Signal Engine.

Test: `TestSafety.test_source_remains_read_only` (toàn bộ `*.py` trong package).

---

## Known limitations

1. Smoke chưa bắt nến M15 đóng live trong phiên → chưa có `SignalResult` từ MT5 thật.  
2. Disconnect/reconnect MT5 thật chưa chạy.  
3. Poll loop dài + SIGINT trên Windows chưa chạy.  
4. API/Dashboard: process API đang chạy **chưa** restart với code 11.2 — header `signalEngine` chưa thấy; badge nghiên cứu trên `SignalCard` **đã** quan sát.  
5. Catch-up chỉ trong cửa sổ `CANDLE_HISTORY_COUNT`.  
6. State file JSON, chưa database.  
7. `last_result` trên API là in-memory; restart API mất tín hiệu hiển thị cho đến nến đóng tiếp theo (cursor vẫn chống trùng).  
8. `SIGNAL_ENGINE_ENABLED` mặc định tắt.  
9. ATR là cổng hợp lệ, không phải điều kiện vào lệnh của `_decide`.  
10. Chưa paper / demo / real order.

---

## Phase 11.3 readiness

**Sẵn sàng bắt đầu phase execution/paper sau khi review riêng.** Biên hiện tại kết thúc ở:

```
Market Data → Closed Candle → Indicators → Strategy → Signal
```

Chưa sẵn sàng đặt lệnh.

Bắt buộc 11.3 (nếu có):

- Chỉ consume `SignalResult` có `actionable=True`.  
- Tôn trọng catch-up: không biến burst nến miss thành burst lệnh.  
- Không nối Signal Engine thẳng vào `MT5Adapter`.  
- Nên hoàn tất smoke forming→closed→1 signal trong phiên XAUUSD M15 trước khi tin tưởng vòng đời live.
