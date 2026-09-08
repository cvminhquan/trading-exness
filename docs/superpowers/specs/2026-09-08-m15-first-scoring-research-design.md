# Design: Phase 16.2.4 — M15-First Strategy Scoring Research

**Date:** 2026-09-08  
**Status:** APPROVED  
**Approach:** Research package song song (`market_analysis/research/`)  
**Strategy id (research-only):** `mtf_technical_v2_candidate`

---

## 1. Goal

Thiết kế và đánh giá scoring M15-first cho XAUUSD intraday so với `mtf_technical_v1`, nhằm trả lời:

> Vì sao v1 có thể vẫn WAIT khi XAUUSD đã giảm mạnh vài giờ?

và định lượng delay / missed ATR move / false signals / whipsaw / risk metrics.

**Không** promote v2 sang execution trong phase này.

---

## 2. Hard boundaries

| Boundary | Rule |
|----------|------|
| `mtf_technical_v1` | **KHÔNG sửa** production scoring / MTF service behavior |
| Phase 17 | **KHÔNG sửa** |
| ExecutionCandidate | **KHÔNG** wire `mtf_technical_v2_candidate` |
| `order_send` / broker mutation | **KHÔNG** |
| Research isolation | Production `market_analysis/` (ngoài `research/`) và `execution/` **không được import** research modules |
| Leverage | 1:2000 **không** vào signal score / confidence / volume |

---

## 3. Research isolation

```
exness_bot/market_analysis/research/   # v2 candidate + comparison only
  ├── identity.py                      # STRATEGY_ID = mtf_technical_v2_candidate
  ├── scoring_v2.py
  ├── impulse.py
  ├── structure_transition.py
  ├── aggregate_v2.py
  ├── compare.py
  ├── historical.py                    # load/resample/validate/split
  ├── scenarios.py
  └── freeze.py                        # frozen config snapshot for holdout
```

- Research **được** import production helpers (candles, ATR, swings, v1 score for comparison).
- Production **không** import `market_analysis.research.*`.
- Enforcement: unit test / import-linter style check trong test suite.

---

## 4. Historical data pipeline

**Primary source:** Exness DEMO / MT5 via existing `exness_bot.tools.export_history` (read-only).

**Canonical:** XAUUSD M15 CSV.

**Derive:** deterministic resample M15 → H1 / H4 / D1 (closed bars only; document timezone + candle boundary).

**Horizon target:** 3–6 months M15 minimum; 6–12 months preferred if export is light.

**Dataset report fields:** start/end, M15 count, H1/H4/D1 counts after resample, gaps, duplicates, timezone, broker symbol.

**If insufficient:** synthetic + partial historical → verdict ceiling = `PROMISING_V2_REQUIRES_MORE_DATA`. Không claim v2 tốt hơn bằng cách hạ tiêu chuẩn.

**Không** mix public/external market data trừ khi không còn lựa chọn (ưu tiên broker Exness).

---

## 5. Chronological split & holdout discipline

```
development = first 60%
validation  = next 20%
holdout     = final 20%
```

No shuffle.

**Freeze trước holdout** (ghi vào `freeze.py` / report snapshot):

- scoring formula
- component weights
- timeframe weights
- thresholds
- structure-transition rules
- impulse mapping

**Cấm:** tune sau khi xem holdout rồi vẫn claim holdout result.

---

## 6. V2 scoring design (initial hypothesis)

### Timeframe roles & weights (configurable)

| TF | Role | Initial weight |
|----|------|----------------|
| M15 | PRIMARY SIGNAL | 0.50 |
| H1 | CONFIRMATION | 0.30 |
| H4 | TREND CONTEXT | 0.15 |
| D1 | MACRO CONTEXT | 0.05 |

Không grid-search hàng trăm tổ hợp để max PnL.

### Outputs tách lớp

1. **direction score** (M15-primary weighted)
2. **context warning** (H4/D1 disagreement flags)
3. **execution blocker** — chỉ khi **explicit named rule** có diagnostic reason + deterministic test + impact reported riêng

H4/D1 **không** implicit veto M15.

### M15 component audit

V1: Trend 30 / Structure 25 / Momentum 20 / Location 15 / Volume 10 với structure ±100 binary.

V2 research:

- Structure **transition** states → soft scores (không chỉ ±100)
- **Impulse** ATR-normalized (1/3/4 closed bars) ∈ [-100, 100]
- Không cho stale confirmed structure triệt tiêu strong trend/momentum một cách vô lý

### Impulse (closed only, no look-ahead)

```
move_1 = (close[t] - close[t-1]) / ATR14
move_3 = (close[t] - close[t-3]) / ATR14
move_4 = (close[t] - close[t-4]) / ATR14
```

Normalize → [-100, 100] với mapping documented (không hardcode case 2026-09-08).

### Structure transition states

`CONFIRMED_BULLISH` | `WEAKENING_BULLISH` | `TRANSITION` | `WEAKENING_BEARISH` | `CONFIRMED_BEARISH`

Dựa swing break / distance / recent closed candles — no look-ahead.

---

## 7. Evaluation

### Synthetic scenarios (deterministic)

sideways; normal bull/bear; sharp 1h/4h selloff; bullish pullback in bearish trend; false breakout; V reversal; M15 bearish vs H4 bullish; M15 bullish vs D1 bearish.

Compare: scenario, v1 score/decision, v2 score/decision, M15 impulse, HTF context.

### Historical metrics

trade count; long/short; win rate; PF; expectancy R; max DD; avg/median R; MAE/MFE; **entry delay**; false breakout rate; whipsaw; **candles saved**; **ATR move missed**.

Signal scoring **independent** of leverage.

---

## 8. Deliverables

1. Spec (this file)
2. Implementation plan
3. Research package + CLI/runner
4. Tests: unit, synthetic, historical validation, isolation, freeze discipline
5. `docs/M15_FIRST_SCORING_RESEARCH.md` with single verdict:

`KEEP_V1` | `PROMISING_V2_REQUIRES_MORE_DATA` | `V2_OUTPERFORMS_ON_HOLDOUT`

**Không promote v2** dù kết quả tốt.

---

## 9. Safety checklist

```
REAL order_send: NO
Broker mutation: NO
Execution integration: NO
Strategy v1 modification: NO
Phase17 modification: NO
Production import of research: NO
```
