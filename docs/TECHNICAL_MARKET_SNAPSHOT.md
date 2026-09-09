# Technical Market Snapshot

## Purpose

Phase **16.3.1** cung cấp `TechnicalMarketSnapshot` — chân lý kỹ thuật **deterministic, structured, auditable, read-only** cho symbol hiện tại (mặc định XAUUSD).

Snapshot là input chuẩn cho:

- 16.3.2 External Intelligence / Google Search Grounding
- 16.3.3 AI Synthesis
- 16.3.4 Dashboard Market Context
- 16.3.5 AI Market Analyst Chat

## Architecture

```
MT5 / Historical Data (read-only provider)
        |
        v
closed_candles_only + analyze_timeframe (+ swings/structure/levels/regime)
        |
        v
TechnicalSnapshotBuilder
        |
        v
TechnicalMarketSnapshot
        |
        +---- API GET /api/v1/analysis/{symbol}/technical-snapshot
        +---- compact: ?view=compact | to_compact_context()
```

Package: `exness_bot.market_analysis.technical_snapshot/`

- `models.py` — schema typed + JSON-safe serialization
- `builder.py` — orchestration
- `trend_segment.py` — neo trend từ confirmed swing
- `wick_detector.py` — morphology + rejection (snapshot descriptive)
- `swing_summary.py` — swings / S/R distance / moves / pullback
- `alignment.py` — MTF alignment enums

## Technical Truth Principle

Mọi số liệu kỹ thuật đến từ:

- broker market data
- indicator / market_analysis canonical hiện có
- deterministic helpers trong package này

**Không** từ LLM, Google, commentary bên ngoài, hay suy diễn bịa.

AI tương lai **consume** snapshot — không thay thế.

## Closed Candle Semantics

- Quote (`bid`/`ask`/`current_price`): có thể live.
- Indicator / structure / wick / trend segment: **chỉ CLOSED candles**.
- Phân biệt `market_data_timestamp` vs `last_closed_candle_timestamp` từng TF.

## Timeframe Roles

| TF | Role |
|----|------|
| M15 | PRIMARY |
| H1 | CONFIRMATION |
| H4 | CONTEXT |
| D1 | MACRO_CONTEXT |

## Indicators

Reuse `analyze_timeframe`:

- EMA20 / EMA50 / EMA200
- RSI14
- ATR14
- MACD (canonical 12/26/9 trong project)

## Trend Segment

Algorithm (documented in `trend_segment.py`):

1. Cần structure BULLISH/BEARISH hoặc trend UPTREND/DOWNTREND rõ.
2. BEARISH → neo = confirmed swing high gần nhất (`index < last`).
3. BULLISH → neo = confirmed swing low gần nhất.
4. Không đủ pivot → `trend_segment = null`, reason `INSUFFICIENT_CONFIRMED_STRUCTURE`.

Không invent BOS/CHOCH.

## Swing Structure

Reuse `detect_confirmed_swings` + `label_swings` → HH/HL/LH/LL sequence.

## Support / Resistance

Reuse Phase 16.1 `build_support_resistance` + nearest levels + distance price/ATR.

## Wick / Rejection

Snapshot descriptive constants (`wick_detector.py`):

- `WICK_BODY_MULTIPLIER = 2.0`
- `WICK_RANGE_SHARE_MIN = 0.40`
- close-position gates

**Không** ảnh hưởng MTF score / ExecutionCandidate / strategy.

Level context: `AT_SUPPORT` / `AT_RESISTANCE` / `NO_LEVEL_CONTEXT` (near band 0.35 ATR).

## Impulse / Price Move

`DESCRIPTIVE_IMPULSE` only: last 1/3/4 bar move (price / % / ATR).

**Không** gắn `research` V2 impulse vào production snapshot.

## Pullback

Chỉ khi có trend segment confirmed. Không Fibonacci trading rules.

## MTF Alignment

Enums: `ALIGNED` | `PARTIALLY_ALIGNED` | `CONFLICTING` | `MIXED` | `NEUTRAL` | `INSUFFICIENT_DATA`

Không win-probability.

## Bot Analysis

Production only: `mtf_technical_v1` via `MultiTimeframeAnalysisService`.

- signal / mtf_score / setup_state / execution_assessment (descriptive)
- **Không** gọi `ExecutionContractService` (tránh lifecycle side-effect)
- **Không** expose V2 research signal

## Data Quality / Freshness

Per-TF: `OK` | `STALE` | `INSUFFICIENT_DATA` | `INVALID_DATA`

Top-level: `FRESH` | `STALE` | `PARTIAL` | `UNAVAILABLE`

Reuse `LIVE_DATA_STALE_SECONDS` + timeframe duration.

## Compact Context

`GET .../technical-snapshot?view=compact` hoặc `snapshot.to_compact_context()`.

## API

```
GET /api/v1/analysis/{symbol}/technical-snapshot
GET /api/v1/analysis/{symbol}/technical-snapshot?view=compact
```

Read-only. No POST.

## Safety Boundary

- Không sửa V1 / V2 freeze / forward validation
- Không `order_send` / broker mutation
- Không Google / LLM
- Không strategy modification

## Limitations

- Trend segment phụ thuộc confirmed swings; có thể `null`.
- Wick rules là descriptive snapshot — không phải tín hiệu giao dịch.
- V2 research intentionally omitted.
- Không chart image / multimodal.

## Future Phase 16.3.2 Integration

External intelligence phải **nhận** compact snapshot làm technical ground truth, không tự tính lại EMA/RSI/structure từ text/search.
