# PHASE 16.2.4A — M15-FIRST RESEARCH VALIDATION HARDENING

**Verdict:** `PROMISING_V2_REQUIRES_MORE_DATA`  
**Freeze:** UNCHANGED (`assert_freeze_matches_16_2_4`)  
**Promotion:** NO  
**Artifact:** `trading-engine/data/historical/m15_first_research_16_2_4A.json`

```text
order_send: NO
broker mutation: NO
ExecutionCandidate: NO
Phase17: NO
mtf_technical_v1: NO
v2 weights/formula retune: NO
```

---

## 1. Coverage audit (35973 → 735 explained)

### Phase 16.2.4 (legacy, incorrect)

Silent `step=48` after warmup=250:

| Field | Value |
|-------|------:|
| TOTAL_M15_BARS | 35973 |
| WARMUP_EXCLUDED | 250 |
| SAMPLING_EXCLUDED | ~34978 |
| FINAL_EVALUATED (legacy) | ~745 (reported ~735 across splits) |
| MTF_ALIGNMENT / DATA_QUALITY / OTHER | 0 |

**Sampling rule (legacy):** `for i in range(250, n, 48)` — undocumented speed hack.

### Phase 16.2.4A (fixed)

| Field | Value |
|-------|------:|
| TOTAL_M15_BARS | 35973 |
| WARMUP_EXCLUDED | 250 |
| MTF_ALIGNMENT_EXCLUDED | 0 |
| DATA_QUALITY_EXCLUDED | 0 |
| SAMPLING_EXCLUDED | **0** |
| OTHER_EXCLUDED | 0 |
| FINAL_EVALUATED | **35723** |
| eval_step | **1** |

Split evals: development 21333 · validation 7195 · holdout 7195.

---

## 2. Gap classification

| Metric | Value |
|--------|------:|
| expected_market_gaps | 389 |
| unexpected_active_session_gaps | 5 |
| expected_missing_bars_est | 16463 |
| unexpected_missing_bars_est | 817 |
| largest_unexpected_gap_minutes | 4395 (~73h) |
| largest unexpected | 2025-04-17T20:45Z → 2025-04-20T22:00Z |
| duplicates | 0 |
| data_quality | **WARN** |

Weekend/session closures counted as expected — not corruption.

---

## 3. Response delay (synthetic)

### sharp_1h_selloff

| Field | v1 | v2 |
|-------|----|----|
| event_bar | 100 | 100 |
| signal_bar | null (no SHORT) | 103 |
| delay_bars | null | 3 |
| delay_minutes | null | 45 |
| missed_price | null | 19.5 |
| missed_atr | null | 7.8 |
| candles_saved | n/a (v1 never signaled) | — |

### sharp_4h_selloff (event detection fixed)

| Field | v1 | v2 |
|-------|----|----|
| event_bar | 99 | 99 |
| signal_bar | 115 | 103 |
| delay_bars | 16 | 4 |
| delay_minutes | 240 | 60 |
| missed_price | 56.0 | 14.0 |
| missed_atr | 28.0 | 7.0 |
| candles_saved | | **12** |

---

## 4. Impulse audit (−20.20 vs −14.65)

End-of-series impulse uses only last 1/3/4 bars / ATR (tanh scale 1.5).

Both scenarios end with a **mild tail** after the dump. Measured at end:

- 1h: moves (−0.14, −0.42, −0.57) ATR → impulse **−20.20**
- 4h: moves (−0.10, −0.30, −0.41) ATR → impulse **−14.65**

Smaller 4h end-impulse is **expected** (grind + milder tail), not a formula bug. Tests cover this.

---

## 5. Holdout signal outcomes (research trade sim)

Assumptions: entry=close[t], SL=1.5·ATR, TP=2R, horizon=96 M15, SL-first, whipsaw≤4 bars. **No execution engine.**

| Metric | v1 holdout | v2 holdout |
|--------|------------|------------|
| trade_count | 391 | 542 |
| win_rate | 34.0% | 35.4% |
| profit_factor | 1.024 | 1.088 |
| expectancy_R | +0.016 | **+0.057** |
| max_drawdown_R | **33** | **58** |
| false_signal_rate | 66.0% | 64.6% |
| whipsaw_rate | 21.0% | 23.4% |
| MAE_R / MFE_R | 1.01 / 1.28 | 1.09 / 1.32 |

Validation caveat: v2 expectancy −0.006 vs v1 +0.026 (not stable across splits).

---

## 6. V2 SHORT while V1 WAIT (holdout)

| | count | wins | losses | win_rate | expectancy_R | MAE | MFE |
|--|------:|-----:|-------:|---------:|-------------:|----:|----:|
| lead SHORT | **121** | 54 | 67 | 44.6% | **+0.339** | 1.09 | 1.45 |
| lead LONG | 113 | 38 | 75 | 33.6% | +0.009 | 1.16 | 1.35 |

Lead SHORT looks like **early capture of real moves**, not pure noise — but overall DD still rises with more trades.

---

## 7. Interpretation answers

**A. Latency reduced?** YES (synthetic 4h: 16→4 bars; 1h: v1 never SHORT, v2 at +3).

**B. How much?** 4h: **12 candles / 180 minutes / ~21 ATR saved** (28→7 missed ATR). 1h: v2 only path (45 min / 7.8 ATR missed vs infinite for v1).

**C. False/whipsaw up?** Mildly: false ↓ slightly, whipsaw 21%→23%, **DD R 33→58 (worse)**.

**D. Holdout 121 V2 SHORT / V1 WAIT?** expectancy_R **+0.34**, win_rate 44.6% — promising early shorts.

**E. Enough evidence M15-first better?** **Not yet for production promote.** Latency + holdout expectancy help, but DD regression + validation negativity + gaps WARN block `V2_OUTPERFORMS_ON_HOLDOUT`.

---

## 8. Verdict

```text
PROMISING_V2_REQUIRES_MORE_DATA
```

Gate note: an earlier auto-pass on expectancy/PF alone was **rejected** after adding drawdown discipline (`max_drawdown_R` must not worsen >+10R or +25%). Holdout DD 33→58 fails that bar.

Next research (not this phase): risk overlays / trade filters — **without** retuning frozen score weights on holdout.

---

## 9. Reproduce

```powershell
.\.venv\Scripts\python.exe -m exness_bot.market_analysis.research.run `
  --csv data/historical/XAUUSD_M15.csv --holdout --eval-step 1 `
  --json-out data/historical/m15_first_research_16_2_4A.json
```
