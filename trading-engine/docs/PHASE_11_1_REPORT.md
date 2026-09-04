# Phase 11.1 Report — Live Candle Engine

**Ngày xác nhận:** 2026-08-29  
**Phạm vi:** vòng đời nến đóng XAUUSD M15 (`exness_bot.candle_engine`)  
**Status: CONDITIONAL**

Lý do không ghi PASS:

- Pytest / ruff / mypy đã chạy lại trong phiên xác nhận này và **đạt**.
- Smoke Windows + MT5 **đã chạy**, nhưng **chưa** quan sát được một lần chuyển forming → closed trong phiên giao dịch (thị trường XAUUSD M15 đã đóng cuối tuần).
- Header Dashboard với API đã restart chứa `candleEngine` **chưa** được xác minh trên trình duyệt.

Không suy đoán các hạng mục chưa có bằng chứng.

Tài liệu thiết kế: [`docs/LIVE_CANDLE_ENGINE.md`](../../docs/LIVE_CANDLE_ENGINE.md).

---

## Implementation summary

Đã thêm engine nến đóng, không chiến lược, không lệnh:

| Thành phần | Vị trí |
|------------|--------|
| Engine / poll / event / state | `src/exness_bot/candle_engine/` |
| Clock | `src/exness_bot/domain/clock.py` (`SystemClock`, `FakeClock`) |
| `get_candles` | `TradingDataProvider` → mock / backtest / `MT5TradingDataProvider` |
| CLI | `exness-bot candles` / `--once` |
| API | `GET /api/v1/status` → `candleEngine` (read-only) |
| Dashboard | `TopHeader` — hiển thị tối thiểu |
| Cấu hình | `CANDLE_ENGINE_ENABLED` mặc định `false` |

Luồng dữ liệu:

```
CandleEngine
  → TradingDataProvider.get_candles(XAUUSD, M15, count)
  → MT5ReadOnlyClient.copy_rates_from_pos
```

Symbol canonical: `XAUUSD`. Suffix broker (`XAUUSDm`) chỉ resolve trong lớp MT5.

`exness-bot candles` gọi `create_trading_data_provider` + `build_candle_engine`. **Không** gọi `create_trading_engine` / `MT5Adapter` (đường `exness-bot run` vẫn tồn tại, không phải Phase 11.1).

---

## Closed candle detection

Công thức: `candle.timestamp + timeframe_duration <= now_utc`.

Bằng chứng test: `test_closed_candle_is_detected`, `test_exact_candle_boundary` (`10:14:59` forming, `10:15:00` đóng).

Bằng chứng MT5: nến đóng mới nhất đọc được `2026-08-28T20:45:00+00:00` (đóng lúc `21:00:00Z`).

---

## Forming candle protection

Engine lọc `closed_candles_only` (sort + dedupe + timestamp), không tin index mảng.

Bằng chứng test: `test_forming_candle_is_ignored`, `test_no_look_ahead_forming_values_not_emitted`.

Bằng chứng MT5 live (forming đang chạy lúc poll): **NOT TESTED** — cuối tuần, 5 bar cuối cùng đều đã đóng theo timestamp.

---

## Idempotency

Khóa: `symbol|timeframe|timestamp`. Con trỏ file `.candle_engine_state.json`.

Bằng chứng test: `test_closed_candle_processed_once`, `test_repeated_polling_does_not_duplicate`, `test_next_candle_processes_once`.

Bằng chứng MT5:

- Lần 1 (cùng ngày, trước khi có file state): `CANDLE_ALREADY_PROCESSED`, `events=0`, warm-start neo `2026-08-28T20:45:00+00:00`.
- Lần 2: `events=0`, “Nến đóng mới nhất đã xử lý.”
- Lần 3 (phiên báo cáo này, 2026-08-29T09:51:18Z): `events=0`, cùng timestamp, process CLI mới — cursor file được giữ.

---

## Restart behavior

Cold start: neo cursor = nến đóng mới nhất, không emit lịch sử. Có file state: không emit lại.

Bằng chứng test: `test_warm_start_seeds_without_emitting`, `test_restart_does_not_reemit` (file JSON tạm).

Bằng chứng MT5: warm-start lần 1 + CLI lần 3 không emit lại. **Không** giả lập crash giữa chừng ngoài việc tắt/mở process CLI.

---

## Reconnect behavior

Disconnect: `BROKER_DISCONNECTED`, không reset cursor. Reconnect: emit nến đóng `timestamp > cursor`, oldest-first.

Bằng chứng test: `test_mt5_disconnect_does_not_reset_cursor`, `test_mt5_reconnect_processes_missing_closed_once`.

Bằng chứng MT5 disconnect/reconnect thật: **NOT TESTED**.

---

## Missed candle handling

Khi đã có cursor: bắt kịp tuần tự oldest-first. Cold start: không dump lịch sử.

Bằng chứng test: `test_multiple_missed_candles_process_chronologically`.

Bằng chứng MT5 miss nhiều nến khi offline: **NOT TESTED**.

Giới hạn đã triển khai: cửa sổ `CANDLE_HISTORY_COUNT` (mặc định 250).

---

## Session gap handling

Gap không phải lỗi; không bịa nến. Malformed → `INVALID_CANDLE`, không nhảy cursor.

Bằng chứng test: `test_normal_market_session_gap`.

Quan sát MT5 cuối tuần: last closed là thứ Sáu `20:45Z`, engine không crash, không emit. Đây **không** phải test gap phiên trong lúc thị trường đang mở.

---

## Event model

`ClosedCandleEvent`: `candle` (UTC), `detected_at`, `source`, `idempotency_key`.

Poll status: `CANDLE_PROCESSED` | `CANDLE_ALREADY_PROCESSED` | `NO_CLOSED_CANDLE` | `DATA_UNAVAILABLE` | `BROKER_DISCONNECTED` | `INVALID_CANDLE`.

Bằng chứng test: `test_closed_events_ten_fifteen_and_ten_forty_five_once` (FakeTradingDataProvider).

Sự kiện `CANDLE_PROCESSED` trên MT5 thật: **NOT TESTED** (cold start / already processed, `events=0`).

---

## Polling

Mặc định 3 giây (`CANDLE_POLL_INTERVAL_SECONDS`). `Event.wait`. SIGINT/SIGTERM trên main thread.

Bằng chứng test: `test_graceful_shutdown` (thread + `stop_event`).

Vòng poll dài trên Windows + MT5 (không `--once`): **NOT TESTED**.

---

## API integration

`GET /api/v1/status` thêm `candleEngine`. Không endpoint mutation mới.

Bằng chứng test: `test_status_connected_mock` — `candleEngine.status == STOPPED`, `dataSource == MOCK` (engine không bật).

`CANDLE_ENGINE_ENABLED` không có trong `.env` lúc xác nhận → mặc định `false`.

`GET /api/v1/status` trên process API đang chạy (code Phase 11.1): **NOT TESTED** — process `127.0.0.1:8000` khởi động trước thay đổi này, chưa restart trong phiên báo cáo.

---

## Dashboard integration

Code: `sessionContextSchema.candleEngine` (optional), `TopHeader` hiển thị trạng thái / nến đóng / nguồn.

Xác minh trình duyệt với API mới: **NOT TESTED**.

---

## Automated tests

File chính: `tests/unit/test_candle_engine.py` — **23** test (thu thập bằng `pytest --collect-only` trước đó trong cùng phase; suite đầy đủ chạy lại bên dưới).

Phủ (tên test):

1. forming bị bỏ qua  
2. nến đóng được phát hiện  
3. biên 10:15  
4. xử lý một lần / poll lặp không trùng / nến tiếp theo  
5. miss chronological  
6. disconnect / reconnect (fake)  
7. malformed / duplicate / non-monotonic  
8. UTC / naive timestamp  
9. session gap / no look-ahead  
10. restart file / warm start / FakeClock / unavailable / shutdown  
11. integration fake 10:15 và 10:45 đúng một lần  
12. safety: source engine+loop không chứa API đặt lệnh  

Thêm: `test_candle_engine_defaults`, `test_get_candles_oldest_first_last_is_forming`, field `candleEngine` trên `/api/v1/status`.

---

## pytest result

Lệnh (cwd `trading-engine`, 2026-08-29, phiên báo cáo):

```text
.\.venv\Scripts\python.exe -m pytest -q --tb=line
```

Kết quả: **352 passed**, 5 skipped, 1 deselected, 1 warning (Starlette/httpx TestClient deprecation).  
**exit code 0.**

`addopts = -m 'not mt5 and not integration'` — 5 skipped / 1 deselected là marker sẵn có, không phải fail Phase 11.1.

---

## ruff result

```text
.\.venv\Scripts\ruff.exe check src tests
```

**All checks passed.** exit code 0.

---

## mypy result

```text
.\.venv\Scripts\mypy.exe src
```

**Success: no issues found in 114 source files.** exit code 0.

---

## Windows + MT5 smoke test

**Đã chạy** trên Windows, `DATA_SOURCE=mt5`, terminal Exness. **Không** PASS toàn bộ checklist spec §31.

Lệnh:

```text
.\.venv\Scripts\python.exe -m exness_bot.cli candles --once
```

| Hạng mục spec | Kết quả | Bằng chứng |
|---------------|---------|------------|
| Engine kết nối MT5 | Có | log `mt5_connection_manager_connected` server `Exness-MT5Trial17` |
| Canonical symbol | `XAUUSD` | log / diagnostic |
| Broker symbol | `XAUUSDm` | `MT5_SYMBOL` trong `.env` (adapter, không nằm trong engine) |
| Nến đóng mới nhất | `2026-08-28T20:45:00Z` | log `latest_closed_at` |
| OHLC nến đó | O 4456.968 H 4460.167 L 4452.972 C 4456.134 | script `get_candles` cùng máy |
| Close time | `2026-08-28T21:00:00Z` | `candle_close_time` |
| Detection time (lần 3) | `2026-08-29T09:51:18Z` | log `candle_engine_once` |
| Emit forming | Không thấy emit | `events=0` |
| Sau đóng nến, đúng 1 event | **NOT TESTED** | không có nến M15 đang forming; không chờ phiên mở |
| Poll sau không trùng | Có (trong điều kiện already-processed) | lần 2 và lần 3 `events=0` |
| Reconnect MT5 không trùng | **NOT TESTED** | không tắt terminal giữa chừng |
| Không đặt lệnh | Có trên đường `candles` | CLI không gọi `order_send` (xem safety) |

Kết luận smoke: **PARTIAL** — kết nối + nến đóng + idempotency file/CLI. Chuyển nến live trong phiên: **NOT TESTED**.

---

## Safety audit

Tìm trong repo (2026-08-29): `order_send`, `TRADE_ACTION_DEAL`, `TRADE_ACTION_PENDING`, `TRADE_ACTION_SLTP`, `TRADE_ACTION_REMOVE`.

### Code execution sẵn có (không phải Phase 11.1)

| Vị trí | Nội dung |
|--------|----------|
| `broker/mt5/trading_client.py` | `order_send` |
| `broker/mt5/adapter.py` | gọi `order_send` (mở/đóng/SLTP) |
| `broker/mt5/mapper.py` | `MT5_TRADE_ACTION_DEAL` (1), `MT5_TRADE_ACTION_SLTP` (6) — build dict |
| `cli.py` → `handle_run` | `MT5Adapter` + `create_trading_engine` |

`TRADE_ACTION_PENDING` / `TRADE_ACTION_REMOVE`: **không** có trong `src/` (chỉ chuỗi cấm trong test).

### Đường Phase 11.1 (read-only)

| Đường | Client / API |
|-------|----------------|
| `candle_engine/` | **Không** khớp `order_send` / `TRADE_ACTION_*` |
| `data/mt5_provider.py` | `copy_rates_from_pos` qua `MT5ReadOnlyClient` |
| `broker/mt5/connection_manager.py` | chỉ `MT5ReadOnlyClient` |
| `handle_candles` | `create_trading_data_provider` — không `MT5Adapter` |
| `api/` | **Không** khớp `order_send` / `TRADE_ACTION_*` |

Kết luận audit: Phase 11.1 **remain READ-ONLY**. Code đặt lệnh cũ vẫn trong repo nhưng **không** nằm trên đường Candle Engine / `exness-bot candles` / read-only API.

Test: `TestSafetyBoundary.test_candle_engine_has_no_trading_or_strategy` (source engine + loop).

---

## Known limitations

1. Smoke chưa bắt nến M15 đóng live trong phiên.  
2. Disconnect/reconnect MT5 thật chưa chạy.  
3. Poll loop dài + SIGINT trên Windows chưa chạy.  
4. `CANDLE_PROCESSED` trên MT5 thật chưa quan sát (`events=0`).  
5. API/Dashboard live với process mới chưa xác minh.  
6. Catch-up chỉ trong `CANDLE_HISTORY_COUNT`.  
7. State file JSON, chưa database.  
8. `CANDLE_ENGINE_ENABLED` mặc định tắt.  
9. Chưa Signal Engine / EMA / RSI / ATR / paper / real order.

---

## Phase 11.2 readiness

**Sẵn sàng bắt đầu Signal Engine** trên biên `ClosedCandleEvent`.

Chưa sẵn sàng execution.

Bắt buộc 11.2:

- Chỉ consume nến đóng.  
- Chính sách catch-up: warmup chỉ báo, không bắn lệnh hàng loạt.  
- Không gọi `order_send` trong 11.2 nếu phase đó vẫn research-only.  
- Nên hoàn tất smoke forming→closed trong phiên XAUUSD M15 trước khi tin tưởng vòng đời nến trên live.
