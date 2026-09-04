# Live Candle Engine (Phase 11.1)

Tài liệu này mô tả vòng đời **nến đóng** XAUUSD M15. Engine **không** tính EMA/RSI/ATR, **không** sinh tín hiệu BUY/SELL, **không** đặt lệnh giấy hay lệnh thật.

## Kiến trúc

```
CandleEngine
    ↓  get_candles(XAUUSD, M15, count)
TradingDataProvider
    ↓  resolve broker symbol (XAUUSDm, …)
MT5ReadOnlyClient
```

- Engine chỉ biết symbol **canonical** `XAUUSD`.
- Suffix broker (`XAUUSDm`, …) được resolve trong lớp MT5/provider, không nằm trong `CandleEngine`.
- Tái sử dụng model `Candle` hiện có (`symbol`, `timeframe`, `timestamp`, OHLC, `tick_volume`, `real_volume`, `spread`).
- Timestamp luôn được chuẩn hóa UTC trước khi phát sự kiện.

Chạy độc lập:

```bash
exness-bot candles          # vòng poll
exness-bot candles --once   # một lần, rồi thoát
```

API (`GET /api/v1/status`) có thể gắn `candleEngine` khi `CANDLE_ENGINE_ENABLED=true`. Mặc định **tắt** để TestClient không spawn thread.

## Định nghĩa nến đóng

Nến M15 mở lúc `10:00:00` UTC:

| Thời điểm UTC | Trạng thái |
|---------------|------------|
| 10:00:00 | Bắt đầu (đang hình thành) |
| 10:14:59 | Vẫn đang hình thành — **không** xử lý |
| 10:15:00 | **Đã đóng** — mới được xử lý |

Công thức:

```
candle.timestamp + timeframe_duration <= now_utc
```

Biên đúng thời điểm: `now == 10:15:00` ⇒ nến 10:00 **đã đóng**.

Nến đang hình thành (index 0 nếu provider trả newest-first) **không bao giờ** được emit. Engine sort oldest-first rồi lọc theo timestamp, không tin vào index mảng.

## Đồng hồ (Clock)

Không gọi `datetime.now()` rải rác trong engine.

- Production: `SystemClock.now_utc()`
- Test: `FakeClock` (`set`, `advance`)

Mọi quyết định đóng/mở nến đi qua `clock.now_utc()`.

## Polling

- Mặc định: `CANDLE_POLL_INTERVAL_SECONDS=3` (khoảng 2–5 giây).
- Không WebSocket, không busy-spin: `Event.wait(interval)`.
- Mỗi chu kỳ: lấy bars → lọc nến đóng → validate → emit nến mới (nếu có).
- LOG DEBUG cho poll lặp lại; INFO chỉ khi start / nến mới / processed / reconnect / stop. WARNING khi MT5 unavailable hoặc nến lỗi.

## Idempotency

Khóa:

```
canonical_symbol + timeframe + candle.timestamp
```

Ví dụ: `XAUUSD|M15|2026-08-29T10:15:00+00:00`

Con trỏ `last_processed_candle_timestamp` nằm trong:

- RAM: `InMemoryCandleStateStore` (test)
- File JSON: `.candle_engine_state.json` (CLI / API) — **không** dùng database trong phase này

Poll lại 1 giây hoặc 5 giây sau **không** emit trùng. Nến M15 tiếp theo mới được xử lý một lần.

## Hành vi khởi động (restart)

1. Đọc bars, xác định nến đóng mới nhất.
2. Nếu file state đã có cursor → khôi phục, **không** emit lại nến đã xử lý.
3. Nếu **chưa có** persistence (cold start):
   - Neo cursor = nến đóng mới nhất.
   - **Không** phát sự kiện lịch sử.

Lý do an toàn cho Signal Engine (Phase 11.2): không đổ hàng loạt nến cũ vào chiến lược như thể chúng vừa đóng.

## Hành vi reconnect

Khi MT5 mất kết nối:

- Engine không crash.
- Không xử lý dữ liệu invalid.
- **Không** reset cursor.

Khi MT5 nối lại:

- Lấy bars hiện tại.
- Mọi nến đóng có `timestamp > cursor` được xử lý **đúng một lần**, oldest-first.
- Nến đang hình thành vẫn bị bỏ qua.

Ví dụ: đã xử lý 10:15 → disconnect → 10:30 đóng → reconnect lúc 10:32 (nến 10:30–10:45 còn forming) → chưa emit 10:30. Lúc 10:45 mới emit nến 10:30 đúng một lần.

## Nến bị miss (offline nhiều nến)

Khi cursor **đã tồn tại**, engine bắt kịp tuần tự:

```
10:15 → 10:30 → 10:45 → 11:00
```

oldest first, không đảo ngược, không nhân đôi.

**Lựa chọn mặc định:** bắt kịp tuần tự các nến đóng còn thiếu (data plane). Không chỉ lấy nến đóng mới nhất, vì reconnect (mục 12) yêu cầu không bỏ nến 10:30.

**Không** tự coi toàn bộ lịch sử miss như tín hiệu giao dịch. Phase 11.2 phải quyết định: dùng catch-up để warmup chỉ báo, **không** bắn lệnh hàng loạt.

Cold start (không cursor) vẫn **không** dump lịch sử — chỉ neo.

Cửa sổ bắt kịp bị giới hạn bởi `CANDLE_HISTORY_COUNT` (mặc định 250 nến M15 ≈ 62 giờ). Lâu hơn thế, nến cũ hơn cửa sổ sẽ không được emit.

## Khoảng trống phiên (session gap)

Gap cuối tuần / phiên Exness là bình thường. Engine:

- Không bịa nến thiếu.
- Không coi gap là lỗi engine.
- Log INFO `candle_engine_session_gap` rồi vẫn xử lý nến đóng tiếp theo.

Dữ liệu malformed (OHLC sai, timestamp lỗi) khác gap — bị `INVALID_CANDLE`, cursor **không** nhảy qua nến lỗi.

## Sự kiện và kết quả poll

`ClosedCandleEvent`:

- `candle` — chỉ nến **đã đóng**, timestamp UTC
- `detected_at`
- `source` (`MT5` / `MOCK` / …)
- `idempotency_key`

Trạng thái poll (không dùng exception cho luồng bình thường):

| Status | Ý nghĩa |
|--------|---------|
| `CANDLE_PROCESSED` | Có nến đóng mới |
| `CANDLE_ALREADY_PROCESSED` | Đã xử lý / cold-start seed |
| `NO_CLOSED_CANDLE` | Chỉ có nến đang hình thành |
| `DATA_UNAVAILABLE` | Provider trả `None` / rỗng |
| `BROKER_DISCONNECTED` | MT5 mất kết nối |
| `INVALID_CANDLE` | Nến lỗi; không tiến cursor |

## Cấu hình

| Biến | Mặc định | Ghi chú |
|------|----------|---------|
| `CANDLE_ENGINE_ENABLED` | `false` | Bật poll nền khi chạy API |
| `CANDLE_TIMEFRAME` | `M15` | Có thể mở rộng sau; chưa có logic đa timeframe |
| `CANDLE_POLL_INTERVAL_SECONDS` | `3` | 1–60 |
| `CANDLE_SYMBOL` | `SYMBOL` (`XAUUSD`) | Canonical |
| `CANDLE_HISTORY_COUNT` | `250` | Số bar lấy mỗi poll |

## Tắt máy sạch

`SIGINT` / `SIGTERM` (main thread): dừng poll, kết thúc chu kỳ an toàn, log `candle_engine_stopped`. CLI `candles` dùng cùng cơ chế.

## API & Dashboard

- `GET /api/v1/status` → `candleEngine`: `status`, `lastProcessedAt`, `lastClosedAt`, `lastUpdateAt`, `dataSource`.
- Không có endpoint mutation.
- Header Dashboard hiển thị tối thiểu: RUNNING/STOPPED, nến đóng gần nhất (ISO UTC), nguồn dữ liệu.

## Kiểm thử

Test deterministic với `FakeClock` + `FakeTradingDataProvider`. **Không** cần MT5 thật.

Phủ: forming bị bỏ qua, biên 10:15, idempotency, nến tiếp theo, miss chronological, disconnect/reconnect, malformed, duplicate, non-monotonic (sort), UTC, restart file state, no look-ahead, session gap, shutdown, FakeClock.

## Smoke Windows + MT5

1. `DATA_SOURCE=mt5`, terminal Exness đang chạy.
2. `exness-bot candles --once` — xác nhận kết nối, nến forming không emit.
3. Chờ nến M15 đóng, chạy lại / để poll — đúng **một** event.
4. Poll ngay sau đó — không trùng.
5. Không đặt lệnh.

Ghi nhận thủ công: broker symbol, timestamp nến, OHLC, `detected_at`. Timestamp phải là nến **đã đóng**.

## Ranh giới an toàn

`candle_engine/` không gọi `order_send`, không `TRADE_ACTION_*`, không import `EmaRsiAtrStrategy`, không paper/real order, không quản lý vị thế.

## Phase 11.2 (đề xuất)

Signal Engine **consume** `ClosedCandleEvent` (EMA/RSI/ATR trên nến đóng). Vẫn chưa execution. Cần chính sách catch-up: warmup chỉ báo vs không phát lệnh trên burst nến miss.
