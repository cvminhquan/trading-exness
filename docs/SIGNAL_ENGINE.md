# Signal Engine (Phase 11.2)

Tài liệu này mô tả **Signal Engine**: nhận nến đóng, tính chỉ báo, đánh giá chiến lược `ema_rsi_atr_v1`, rồi phát `SignalResult`. Engine **không** đặt lệnh giấy, **không** đặt lệnh demo/thật, **không** sửa vị thế / SL / TP.

## Kiến trúc

```
CandleEngine
    ↓  ClosedCandleEvent
SignalEngine
    ↓  IndicatorCalculator (EMA / RSI / ATR)
EmaRsiAtrStrategy (ema_rsi_atr_v1)
    ↓  SignalResult
```

- **Không** tạo Candle Engine thứ hai.
- **Không** tạo MT5 client thứ hai.
- Signal Engine chỉ phụ thuộc **data provider chỉ đọc** (`TradingDataProvider`).
- Hướng phụ thuộc: `SignalEngine → Data Provider`. **Không** `SignalEngine → MT5Adapter / TradingClient`.

Chạy độc lập:

```bash
exness-bot signals          # vòng poll (warmup + ClosedCandleEvent)
exness-bot signals --once   # warmup + một lần poll, rồi thoát
```

API (`GET /api/v1/status`) có thể gắn `signalEngine` khi `SIGNAL_ENGINE_ENABLED=true`. Mặc định **tắt** để TestClient không spawn thread. Khi bật Signal Engine trên API, cùng một thread poll nến + tín hiệu — **không** bật thêm `CANDLE_ENGINE_ENABLED` để tránh double-poll.

## Adapter chiến lược

`EmaRsiAtrStrategy` vốn dùng cho backtest: nhận DataFrame nến đóng + `IndicatorSnapshot`, trả `Signal` với `BUY` / `SELL` / `HOLD`.

Adapter tối thiểu (`signal_engine/adapter.py`):

| Việc | Cách làm |
|------|----------|
| Input | Chỉ nến đóng từ `ClosedCandleEvent` |
| Chỉ báo | `IndicatorCalculator.compute` — cùng EMA 20/50/200, RSI 14, ATR 14 |
| Hợp lệ | EMA, RSI, **ATR** phải hữu hạn trước khi gọi chiến lược |
| Ánh xạ | `HOLD` → `NO_SIGNAL`; `BUY`/`SELL` giữ nguyên |
| Lý do | Điều kiện có cấu trúc (`SignalCondition`), không parse chuỗi |
| ATR | Chiến lược gốc **không** dùng ATR trong `_decide`; Signal Engine dùng ATR như **cổng hợp lệ** trước BUY/SELL |

Không đổi tham số chiến lược. Không đổi mô hình khớp lệnh backtest.

## Tính chỉ báo

Tái sử dụng `IndicatorCalculator`:

- EMA 20, EMA 50, EMA 200
- RSI 14
- ATR 14

Cùng chuỗi nến + cùng cấu hình phải cho cùng giá trị (sai số float rất nhỏ) giữa backtest (`compute_all` trên prefix) và bước incremental live (`compute` trên cùng prefix).

Với mỗi tín hiệu tại nến **T**:

- Chỉ dùng dữ liệu `timestamp <= T`
- Không đọc nến đang hình thành
- Không đọc nến T+1

## Warm-up

Số nến warmup lấy từ cấu hình backtest hiện có: `BacktestConfig.warmup_bars` (**200**). Không hardcode một giá trị warmup thứ hai.

Cửa sổ lịch sử lấy từ `CANDLE_HISTORY_COUNT` (mặc định 250).

Nến lịch sử dùng để tính EMA/RSI/ATR **không** tự phát `BUY` / `SELL`.

## Cold start

Khi chưa có file state:

1. Tải nến đóng lịch sử.
2. Warm-up chỉ báo.
3. Neo cursor = nến đóng mới nhất.
4. **Không** phát tín hiệu cho các nến lịch sử.
5. Chờ `ClosedCandleEvent` **mới**.
6. Chỉ nến đó được đánh giá bình thường.

## Warm start

Khi đã có `.signal_engine_state.json`:

- Khôi phục `lastProcessedTimestamp` và `strategy`.
- Nếu `strategy` khác phiên bản hiện tại → coi như cold start (reset cursor).
- Không xử lý lại cùng nến.
- Không nhân đôi tín hiệu.
- Tiếp tục từ nến đóng tiếp theo.

Không dùng database. State JSON cùng kiểu với Phase 11.1.

## Catch-up — INDICATOR_CATCHUP vs SIGNAL_EMISSION

Phase 11.1 có thể emit nhiều `ClosedCandleEvent` sau reconnect. Signal Engine xử lý **oldest-first**.

| Khái niệm | Hành vi |
|-----------|---------|
| `INDICATOR_CATCHUP` | Mọi nến miss (trừ nến mới nhất) được append vào history và tiến cursor. **Không** tạo `SignalResult`. |
| `SIGNAL_EMISSION` | Chỉ nến đóng **mới nhất** trong batch được `_emit` → đúng **một** `SignalResult`. |

Ví dụ reconnect: đã xử lý 10:15, rồi 10:30 / 10:45 / 11:00 đóng. Catch-up cập nhật chỉ báo cho 10:30 và 10:45; chỉ 11:00 có thể tạo tín hiệu.

`actionable=True` chỉ khi `BUY` hoặc `SELL`. `NO_SIGNAL` và `INVALID` không actionable. Phase này không có execution — hợp đồng này để Phase sau không bắn lệnh hàng loạt.

## Idempotency

Một nến sinh tối đa một `SignalResult`.

Khóa:

```
symbol|timeframe|candle_timestamp|strategy
```

Ví dụ: `XAUUSD|M15|2026-08-29T10:15:00+00:00|ema_rsi_atr_v1`

Sự kiện lặp lại → `ALREADY_PROCESSED`, `results=()`.

## SignalResult

| Trường | Ý nghĩa |
|--------|---------|
| `symbol` / `timeframe` | Canonical, ví dụ XAUUSD / M15 |
| `candle_timestamp` | Timestamp nến đóng |
| `signal` | `BUY` / `SELL` / `NO_SIGNAL` / `INVALID` |
| `generated_at` | Thời điểm đánh giá (clock, không đọc MT5) |
| `source` | `MOCK` / `MT5` / `TEST` |
| `strategy` | `ema_rsi_atr_v1` |
| `indicators` | Snapshot EMA / RSI / ATR |
| `reason` | Lý do từ chiến lược hoặc cổng hợp lệ |
| `conditions` | Điều kiện có cấu trúc |
| `idempotency_key` | Khóa trên |
| `actionable` | `True` chỉ BUY/SELL hợp lệ |

**Không** có ticket, fill price, execution status.

`INVALID` khi EMA/RSI/ATR thiếu, NaN, Infinity, hoặc None. Không biến giá trị lỗi thành BUY/SELL.

## Cấu hình

Tái sử dụng settings hiện có. Không invent tham số mới.

| Khóa | Nguồn |
|------|--------|
| `ema_rsi_atr_v1` | `EmaRsiAtrStrategy.name` |
| EMA 20/50/200, RSI 14, ATR 14 | `IndicatorCalculator` |
| `RSI_LONG_MIN` / `RSI_LONG_MAX` | Settings (mặc định 50 / 70) |
| `RSI_SHORT_MIN` / `RSI_SHORT_MAX` | Settings (mặc định 30 / 50) |
| Warm-up 200 bars | `BacktestConfig.warmup_bars` |
| `CANDLE_HISTORY_COUNT` | Settings (mặc định 250) |
| `SIGNAL_ENGINE_ENABLED` | Mặc định `false` |

## API

Chỉ đọc. `GET /api/v1/status` → `signalEngine`:

- `status` (`RUNNING` / `STOPPED`)
- `strategy`
- `lastProcessedCandle`
- `lastSignal`
- `lastSignalAt`
- `dataSource`

Không có endpoint kích hoạt giao dịch. `GET /api/v1/strategy` hiển thị `currentSignal` từ `last_result` khi engine đã emit; nếu chưa có thì giữ HOLD nghiên cứu (không phải lệnh).

## Dashboard

Hiển thị tối thiểu, không redesign:

- Chiến lược `ema_rsi_atr_v1`
- Tín hiệu BUY / SELL / NO_SIGNAL / INVALID / HOLD
- Timestamp nến
- EMA, RSI, ATR
- Nhãn **TÍN HIỆU NGHIÊN CỨU — KHÔNG PHẢI LỆNH**

Header: trạng thái Signal Engine, strategy, tín hiệu gần nhất.

## Logging

| Mức | Sự kiện |
|-----|---------|
| INFO | `signal_engine_started`, `new_signal`, `signal_engine_stopped` |
| DEBUG | `indicator_calculation`, `no_signal` |
| WARNING | `invalid_indicator`, `insufficient_history` |

Không log secret.

## Linux / mock

`DATA_SOURCE=mock` đủ cho unit test, Signal Engine test, và Dashboard. Không cần Windows MT5.

## Safety

`exness_bot/signal_engine/` không import `MT5Adapter`, `TradingClient`, không gọi `order_send`.

CLI `signals` dùng `create_trading_data_provider` + `build_candle_engine` + `build_signal_engine` — **không** đi qua `exness-bot run` / `MT5Adapter`.

## Kiểm thử

Test deterministic với `FakeClock` + snapshot inject khi cần BUY/SELL ổn định. Warm-up production vẫn 200 bars; test critical dùng `warmup_bars=4` vì 5 nến lịch sử không đủ EMA200.

Kịch bản bắt buộc: warmup 10:00 … 11:00 → 0 tín hiệu; nến 11:15 đóng → đúng 1 `SignalResult`.
