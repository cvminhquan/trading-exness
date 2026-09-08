# PHASE 16 — Market Analysis & Trade Proposal

## Status

```text
CONDITIONAL
```

**Ngày:** 2026-09-07  
**Phạm vi:** Phân tích thị trường + đề xuất giao dịch **chỉ đọc**.  
**Không** bật autonomous execution. **Không** claim lợi nhuận chiến lược.

Lý do CONDITIONAL (không FAIL chức năng):

- `npm run build` bị `EPERM` khi xóa `dashboard/.next` (dev server đang giữ lock).
- `npm run lint` còn lỗi sẵn có ở `TrendingQuotesCard.tsx` (không thuộc diff Phase 16).
- Backend: `pytest` / `ruff` / `mypy` **PASS**.
- Dashboard: `tsc --noEmit` **PASS**, vitest **39 passed**.

---

## 1. Architecture

```text
Closed M15 Candle (provider + closed_candles_only)
        ↓
IndicatorCalculator (EMA20/50/200, RSI14, ATR14)
        ↓
Market regime (BULLISH / BEARISH / NEUTRAL)
        ↓
Strategy decision ema_rsi_atr_v1 (Phase-16 rules)
        ↓
Trade proposal (ASK/BID entry, ATR SL, RR TP)
        ↓
Position sizing (broker symbol specs)
        ↓
signal: BUY | SELL | WAIT
executionStatus: READY | BLOCKED | NOT_APPLICABLE
        ↓
GET /api/v1/analysis[/XAUUSD]
        ↓
Dashboard TradeAnalysisCard
```

Package: `trading-engine/src/exness_bot/market_analysis/`

Orchestrator: `MarketAnalysisService.analyze()` — **không** import `ExecutionOrchestrator` / `LiveMT5ExecutionTransport`, **không** gọi `order_send(`.

Strategy loop live vẫn tách; phase này là on-demand analysis qua API.

---

## 2. Indicator definitions

Nguồn duy nhất: `IndicatorCalculator` (`indicators/calculator.py`).

| Field | Period |
|-------|--------|
| EMA20 / EMA50 / EMA200 | 20 / 50 / 200 |
| RSI14 | 14 |
| ATR14 | 14 |

Chỉ tính trên **nến đã đóng** (`closed_candles_only`). Không phân tích nến đang forming.

---

## 3. Strategy rules (`ema_rsi_atr_v1` — Phase 16 analysis)

**Regime**

- `BULLISH`: `close > EMA200` AND `EMA20 > EMA50`
- `BEARISH`: `close < EMA200` AND `EMA20 < EMA50`
- else `NEUTRAL`

**BUY**

- regime = BULLISH
- EMA20 > EMA50
- close > EMA200
- `RSI_LONG_MIN <= RSI14 <= RSI_LONG_MAX`
- ATR14 available

**SELL** — đối xứng với short RSI range.

**WAIT** — không tạo trade plan.

Config: `RSI_LONG_*`, `RSI_SHORT_*`, `ATR_SL_MULTIPLIER`, `REWARD_RISK_RATIO`, `RISK_PER_TRADE_PCT`, `MAX_SPREAD_POINTS`.

> Ghi chú: Live `EmaRsiAtrStrategy` (signal engine) vẫn dùng rule xếp tầng EMA chặt hơn (`EMA20>EMA50>EMA200`, `close>EMA20`). Phase 16 analysis dùng rule + regime theo TASK 3–4; không đổi execution path.

---

## 4. Entry calculation

| Signal | Entry |
|--------|-------|
| BUY | broker **ASK** |
| SELL | broker **BID** |

Giá được `normalize_price` theo `point` / `digits`. Quote stale/unavailable → `executionStatus=BLOCKED`.

---

## 5. ATR Stop Loss

```text
SL_distance = ATR14 * ATR_SL_MULTIPLIER
BUY:  SL = entry - SL_distance
SELL: SL = entry + SL_distance
```

Validate khoảng cách với `stops_level` / `freeze_level` khi metadata có sẵn (`validate_sl_tp_distance`).

---

## 6. Take Profit / R:R

```text
TP distance = |entry - SL| * REWARD_RISK_RATIO
BUY:  TP = entry + TP distance
SELL: TP = entry - TP distance
```

API trả `riskRewardRatio` thực tế sau normalize giá.

---

## 7. Position sizing

Dùng metadata broker:

- `volume_min` / `volume_step` / `volume_max`
- `trade_contract_size`, `point`, `digits`
- optional `trade_tick_size` / `trade_tick_value` (map từ MT5 khi có)

```text
risk_budget_usd = equity * risk_per_trade_pct / 100
raw_volume = risk_budget / (sl_points * money_per_point_per_lot)
normalized = floor-to-step (không round-up unsafely)
```

Sau normalize / khi buộc lấy `volume_min`: **tính lại** `estimatedRiskUsd` rồi mới quyết định `riskAcceptable`.

---

## 8. XAUUSD broker metadata

- Canonical: `XAUUSD`
- Broker thường: `XAUUSDm` (`resolve_broker_symbol` / `MT5_SYMBOL`)
- Provider mới: `get_symbol_info()`, `resolve_broker_symbol()` trên MT5 + mock

Không hardcode `contract_size=100` trên dashboard risk card nữa — sizing lấy từ API analysis.

---

## 9. Small-account behavior (~$10.50)

Phân biệt:

| Khái niệm | Ý nghĩa |
|-----------|---------|
| `brokerExecutable` | Broker cho phép mở (vd. 0.01) |
| `riskAcceptable` | Rủi ro tiền tại volume đề xuất ≤ ngân sách % |

Ví dụ: raw 0.001 → hiển thị normalized 0.01, `signal=BUY`, `executionStatus=BLOCKED`, reason `MIN_VOLUME_EXCEEDS_RISK_BUDGET`  
Message: *broker-executable but exceeds configured risk budget* — **không** nói “không mở được 0.01”.

---

## 10. BUY / SELL / WAIT / BLOCKED semantics

| Field | Giá trị |
|-------|---------|
| `signal` | Kết quả chiến lược (có thể BUY dù không khớp được) |
| `executionStatus` | `READY` / `BLOCKED` / `NOT_APPLICABLE` (WAIT) |
| Stale candle/quote | status `STALE`, execution `BLOCKED` |
| Spread > `MAX_SPREAD_POINTS` | signal giữ BUY/SELL, block `SPREAD_TOO_WIDE` |

---

## 11. API contract

| Method | Path |
|--------|------|
| GET | `/api/v1/analysis?symbol=XAUUSD` |
| GET | `/api/v1/analysis/{symbol}` |

Envelope: `{ "data": TradeAnalysisDTO }` (camelCase).

Không có POST/PUT đóng hoặc mở lệnh.

---

## 12. Dashboard UI

- `TradeAnalysisCard` thay `TradeAnalysisRiskCard` (hardcoded stop/contract) trên `/dashboard`.
- Hiển thị: signal, market, trade plan, sizing, execution assessment, reasons ✓/✕.
- WAIT: Entry/SL/TP/volume = `—`.
- Hook: `useTradeAnalysis("XAUUSD")` ~5s.

---

## 13. Test results

### Backend

```text
pytest: 821 passed, 5 skipped, 1 deselected
ruff check src tests: All checks passed
mypy src: Success (179 source files)
```

Phase 16 unit/API: `tests/unit/test_phase_16_market_analysis.py` (12 tests).

### Dashboard

```text
tsc --noEmit: PASS
vitest: 39 passed (gồm trade-analysis.test.ts)
lint: FAIL — lỗi sẵn có TrendingQuotesCard (không thuộc Phase 16)
build: FAIL — EPERM lock .next (dev server đang chạy)
```

---

## 14. Safety audit

Đã rà `market_analysis/`, routes analysis, `TradeAnalysisCard`:

- Không có lời gọi `order_send(`
- Không wire `ExecutionOrchestrator` / `LiveMT5ExecutionTransport`
- Dashboard không có nút đặt/đóng lệnh trên card phân tích
- Docstring/comment có thể nhắc “no order_send” mang tính cảnh báo — không phải API mutation

`GET /api/v1/analysis` chỉ đọc.

---

## 15. Remaining risks

1. Rule analysis (regime) ≠ rule live `EmaRsiAtrStrategy` — có thể lệch tín hiệu giữa Strategy page và Trade Analysis.
2. Fallback symbol specs khi thiếu `get_symbol_info` vẫn có `contract_size=100` — chỉ khi provider không trả metadata.
3. Candle stale heuristic = `timeframe_duration + LIVE_DATA_STALE_SECONDS` — có thể chặt/lỏng tùy phiên giao dịch.
4. `.env` local: `MAX_SPREAD_POINTS=260`, `EXECUTION_MODE=live` — analysis dùng max spread từ settings; không kích hoạt khớp lệnh qua endpoint này.
5. Cần restart API process để nạp route analysis nếu uvicorn không reload.
6. Build dashboard cần dừng dev server / giải phóng `.next` rồi chạy lại `npm run build`.

---

## Key files

| Area | Path |
|------|------|
| Engine | `trading-engine/src/exness_bot/market_analysis/` |
| API | `api/routes/v1.py`, `ReadService.get_trade_analysis` |
| DTO | `TradeAnalysisDTO` trong `api/schemas/dashboard.py` |
| UI | `dashboard/components/account/TradeAnalysisCard.tsx` |
| Tests | `tests/unit/test_phase_16_market_analysis.py`, `dashboard/lib/trade-analysis.test.ts` |
| Config example | `trading-engine/.env.example` → `MAX_SPREAD_POINTS=260` |
