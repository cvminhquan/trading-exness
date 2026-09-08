# PHASE 16.2 — Multi-Timeframe Technical Analysis Engine

## Kết quả

Phân tích **chỉ đọc** (ANALYSIS ONLY). Không `order_send`, không đóng vị thế tự động, không nối strategy → execution.

Confidence = **EVIDENCE_ALIGNMENT** (đồng thuận bằng chứng kỹ thuật), **không** phải xác suất thắng.

## Kiến trúc timeframe

| Timeframe | Vai trò | Weight mặc định |
|-----------|---------|-----------------|
| M15 | Primary setup / entry timing | 0.20 |
| H1 | Directional confirmation | 0.30 |
| H4 | Higher-structure bias | 0.30 |
| D1 | Macro bias | 0.20 |

Chỉ dùng **closed candles**. Caller lọc qua `closed_candles_only`.

Mỗi TF → `TimeframeAnalysis` độc lập (`timeframe_analyzer.analyze_timeframe`).

Aggregate → `MultiTimeframeAnalysisService.analyze` → API DTO.

Logic nằm trong Python (`market_analysis/`) để tái sử dụng cho backtest / paper / DEMO forward sau này.

## Indicators

| Indicator | Settings | Ghi chú |
|-----------|----------|---------|
| EMA20 / EMA50 / EMA200 | qua `IndicatorCalculator` | tái sử dụng Phase 16 |
| RSI14 | mặc định strategy | |
| ATR14 | | |
| MACD | 12 / 26 / 9 (`MACD_FAST/SLOW/SIGNAL`) | `indicators/macd.py` |
| Volume | `TICK_VOLUME` | không gắn nhãn exchange real volume |

### Volume thresholds

- `volumeRatio = current_tick_volume / avg(previous N closed)` với `N = VOLUME_AVG_PERIOD` (20)
- `HIGH` nếu `ratio >= VOLUME_HIGH_RATIO` (1.5)
- `LOW` nếu `ratio < VOLUME_LOW_RATIO` (0.7)
- ngược lại `NORMAL`
- thiếu dữ liệu → `UNKNOWN`

## Trend

Không dựa một indicator. Evidence:

- price vs EMA200
- EMA20 vs EMA50
- EMA50 vs EMA200
- EMA20 slope
- market structure (HH/HL vs LH/LL)

Mixed → `RANGE`. Insufficient → `UNKNOWN`.

## Market structure & S/R

Reuse Phase 16.1:

- Confirmed swings (no look-ahead: cần đủ right closed bars)
- HH / HL / LH / LL → BULLISH / BEARISH / RANGE / UNDETERMINED
- Support = confirmed swing lows; Resistance = confirmed swing highs
- Cluster theo ATR (`SR_CLUSTER_ATR_MULTIPLIER`)
- Expose `nearestSupport` / `nearestResistance`

## Pattern (conservative)

Chỉ mã deterministic (ví dụ continuation HH/HL, breakout/retest đơn giản).  
Không nhận diện Head & Shoulders / Double Top / V-recovery trừ khi có thuật toán tường minh + test.

`pattern = NONE` khi không đủ bằng chứng.

## Scoring (per timeframe)

Score range: **-100 … +100** (âm = SHORT bias).

| Component | Weight |
|-----------|--------|
| trendScore | 0.30 |
| structureScore | 0.25 |
| momentumScore | 0.20 |
| locationScore | 0.15 |
| volumeScore | 0.10 |

`totalScore = weighted sum`. Direction từ tổng điểm (ngưỡng gần 0 → NEUTRAL).

Confidence 0..100 = độ mạnh/đồng thuận evidence trên TF đó — **không** hardcode 72/74/78.

## Aggregation

Weighted score theo `MTF_WEIGHT_*` (không average % thô).

- H4 vs D1 đối nghịch (không NEUTRAL) → `finalSignal = WAIT`, giảm confidence ×0.6, warning `HIGHER_TF_CONFLICT`
- H1 vs H4 conflict → giảm confidence ×0.75, warning `H1_H4_CONFLICT`
- `total >= +20` → LONG; `<= -20` → SHORT; else WAIT

`finalSignal` **tách** khỏi `executionAssessment` (READY / BLOCKED / NOT_APPLICABLE).

## Setup / entry / SL / TP

- Ưu tiên `PULLBACK` (không chase giá)
- `entryType` / `entryPrice` / `entryZoneLow|High` / `entryReason`
- State machine: `NO_SETUP` | `WAITING_FOR_ENTRY` | `ENTRY_ZONE` | `INVALIDATED` | `EXPIRED`
- LONG trên vùng entry → WAITING; vào zone → ENTRY_ZONE; phá SL trước entry → INVALIDATED
- SL: structure swing + ATR buffer (không để ATR-only xuyên qua cấu trúc quan trọng nếu swing có sẵn)
- TP1/TP2/TP3 từ S/R và R-multiples; allocation mặc định 30/40/30 (sum = 100%)
- Warning ví dụ `TP2_BEYOND_MAJOR_RESISTANCE` khi target vượt mức lớn

## Risk sizing

Reuse Phase 16 `size_position`:

- `brokerExecutable` vs `riskAcceptable`
- Tài khoản ~$10.50: có thể mở được min lot nhưng **không** tăng risk để “cho khớp”
- Lý do điển hình: `MIN_VOLUME_EXCEEDS_RISK_BUDGET`

## Leverage

Không xuất “Leverage: 3x” giả. Chỉ metadata tài khoản/broker khi có (equity / margin fields qua sizing + account overview). MT5 không chọn leverage theo từng lệnh trong phase này.

## API

```
GET /api/v1/analysis/{symbol}/multi-timeframe
```

Read-only. Envelope chuẩn `DataEnvelope`.

`confidenceMeaning` luôn `EVIDENCE_ALIGNMENT`.

## Dashboard

- Card `MultiTimeframeAnalysisCard` trên overview
- Hiển thị bảng TF (M15/H1/H4/D1), FINAL, confidence + tooltip tiếng Việt
- Setup state, entry zone, SL, multi-TP, warnings, summaryVi
- Tooltip: *Confidence đo mức đồng thuận giữa các điều kiện kỹ thuật đã cấu hình. Đây không phải xác suất thắng dự đoán.*

## Tests

`tests/unit/test_phase_16_2_multi_timeframe.py` — MACD, volume, scoring weights, per-TF, aggregation, conflict→WAIT, pullback/do-not-chase, TP alloc=100%, small account fields, no look-ahead, no `order_send` trong `market_analysis/`.

Dashboard: `lib/multi-timeframe-analysis.test.ts`.

## Env keys

Xem `trading-engine/.env.example` section Phase 16.2.

## Known limitations

- Pattern set còn hẹp / conservative
- Chart overlay candle chưa có (giống 16.1)
- `EXPIRED` state cần consumer gắn lifecycle giữa các lần analyze (mỗi response mới độc lập)
- Mock provider volume là synthetic tick_volume
- Không claim profitability

## Safety

Phase này không submit trades. Dashboard chỉ monitor/analysis.
