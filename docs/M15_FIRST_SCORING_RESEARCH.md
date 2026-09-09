# M15-First Scoring Research

**Phase:** 16.2.4 → **16.2.4A (validation hardening)**  
**Date:** 2026-09-09  
**Candidate:** `mtf_technical_v2_candidate` (RESEARCH ONLY)  
**Production:** `mtf_technical_v1` — **unchanged**  
**Artifact:** `trading-engine/data/historical/m15_first_research_16_2_4A.json`  
**Phase report:** `docs/PHASE_16_2_4A_VALIDATION_HARDENING.md`

```text
order_send: NO
broker mutation: NO
ExecutionCandidate / Phase17: NO
v2 promoted: NO
freeze retuned after holdout: NO
```

---

## 1. Scope

Audit + harden the research harness so M15-first weighting can be compared fairly to production v1 on historical XAUUSD M15 — **without** promoting v2 or changing frozen weights.

Research question:

> Does M15-first (PRIMARY) + HTF confirmation/context improve reaction latency and signal quality vs v1 HTF-heavy scoring?

---

## 2. Safety Boundary

| Constraint | Status |
|------------|--------|
| Production imports `research/` | **NO** (AST-enforced) |
| Research CSV offline | YES |
| Execution / MT5 order APIs | **ZERO** in research path |
| Leverage in scoring | **NO** — sizing/margin only |

---

## 3. Frozen V2 Snapshot

Verified `assert_freeze_matches_16_2_4` — **CONFIG_DRIFT: NO**

| Item | Value |
|------|-------|
| TF | M15=0.50 · H1=0.30 · H4=0.15 · D1=0.05 |
| Components | trend 0.25 · structure 0.15 · mom 0.20 · loc 0.10 · vol 0.10 · impulse 0.20 |
| Aggregate | LONG ≥ +20 · SHORT ≤ −20 |
| Structure dampen | 0.35 |
| Impulse | scale 1.5 · w 0.50/0.30/0.20 |
| `higher_tf_strong_conflict_enabled` | **false** |

---

## 4. Dataset

| Field | Value |
|-------|-------|
| Path | `data/historical/XAUUSD_M15.csv` |
| Broker symbol | XAUUSDm |
| Timezone | UTC |
| Start | 2025-03-02T23:00:00+00:00 |
| End | 2026-09-08T16:00:00+00:00 |
| M15 / H1 / H4 / D1 | 35 973 / 9 000 / 2 433 / 474 |
| Duplicates | 0 |

---

## 5. Coverage Accounting

**Model:** first-exclusion, mutually exclusive buckets.

### Legacy 16.2.4 (incorrect)

Silent `for i in range(250, n, 48)`:

| Field | Value |
|-------|------:|
| TOTAL_M15_BARS | 35 973 |
| WARMUP_EXCLUDED | 250 |
| SAMPLING_EXCLUDED | 34 978 |
| FINAL_EVALUATED | **745** (~735 reported across splits) |

### Hardened 16.2.4A

| Field | Value |
|-------|------:|
| TOTAL_M15_BARS | 35 973 |
| WARMUP_EXCLUDED | 250 |
| MTF_ALIGNMENT / DATA_QUALITY / OTHER | 0 |
| SAMPLING_EXCLUDED | **0** |
| FINAL_ELIGIBLE ≈ FINAL_EVALUATED | **35 723** |
| eval_step | **1** |
| sampling_enabled | **false** |

Split evals: development 21 333 · validation 7 195 · holdout 7 195.

---

## 6. Gap Classification

Heuristic (documented limitation — not full Exness calendar): Fri/Mon or δ≤4h → expected; mid-week δ>4h → unexpected.

| Metric | Value |
|--------|------:|
| expected_market_gaps | 389 |
| unexpected_active_session_gaps | 5 |
| expected_missing_bars_est | 16 463 |
| unexpected_missing_bars_est | 817 |
| largest_unexpected_gap | ~4 395 min (~73h) |
| largest unexpected range | 2025-04-17T20:45Z → 2025-04-20T22:00Z |
| duplicates | 0 |
| data_quality | **WARN** |

---

## 7. Resampling / No Look-Ahead

Pipeline: closed M15 → H1 → H4 → D1 via UTC floor buckets; incomplete HTF buckets dropped.

At evaluation index `i`, only `m15[:i+1]` is resampled. Tests: `test_phase_16_2_4a_resample_alignment.py`.

**Look-ahead:** none detected in unit tests.

---

## 8. Chronological Splits

Order: Development → Validation → Holdout (60/20/20 by index). **No shuffle.**

Warmup: first 250 bars excluded from eval; each eval window uses last 250 closed bars (past-only) — matches live closed-candle semantics.

---

## 9. Synthetic Scenarios

Suite preserved (sideways, bull/bear, sharp 1h/4h selloff, pullback, false breakout, V-reversal, TF conflicts).

| Scenario | v1 | v2 |
|----------|----|----|
| sharp_1h_selloff | WAIT (no SHORT) | SHORT @ +3 bars |
| sharp_4h_selloff | SHORT @ +16 | SHORT @ +4 (**12 candles saved**) |

`event_bar` for 4h selloff: **fixed** (was null in earlier run).

---

## 10. Impulse Audit

End-of-series impulse uses last 1/3/4 closed moves / ATR14, tanh(scale=1.5).

| Scenario | moves (ATR) | impulse |
|----------|-------------|---------|
| sharp_1h end | (−0.14, −0.42, −0.57) | **−20.20** |
| sharp_4h end | (−0.10, −0.30, −0.41) | **−14.65** |

Smaller 4h end-impulse is expected (grind + milder tail), **not** a formula bug. Formula **not** retuned.

---

## 11. Structure Transition Audit

Stale `STRUCTURE=+100` vs `TREND=−100`:

| | v1 | v2 |
|--|----|----|
| structure state | binary BULLISH | WEAKENING_BULLISH |
| after dampen 0.35 | n/a | ~+35 |
| trend+structure contrib | ~−5 | ~−19.75 |
| + impulse | none | strongly bearish |

Transition + dampen reduces stale structure’s ability to cancel M15 trend.

---

## 12. Response Latency

Units explicit: **bars** = M15 candles; **minutes** = bars×15; **missed_price** = XAUUSD **price units (USD)**; **missed_atr** = price/ATR.

### sharp_1h_selloff

| | v1 | v2 |
|--|----|----|
| signal_bar | null | 103 |
| delay_bars / minutes | — | 3 / **45** |
| missed_price (USD) | — | 19.5 |
| missed_ATR | — | 7.8 |

### sharp_4h_selloff

| | v1 | v2 |
|--|----|----|
| delay_bars / minutes | 16 / 240 | 4 / 60 |
| candles_saved | — | **12** |
| missed_price (USD) | 56.0 | 14.0 |
| missed_ATR | 28.0 | 7.0 |

---

## 13. Outcome Methodology

Research-only sim (`outcomes.py`) — **not** ExecutionOrchestrator / MT5.

| Assumption | Value |
|------------|-------|
| Entry | close[t] |
| SL | 1.5 × ATR14 |
| TP | 2R |
| Horizon | 96 M15 (~24h) |
| Path | bars t+1.. (no same-bar entry look-ahead) |
| Same-bar SL+TP | **SL first** |
| FALSE_SIGNAL | realized R < 0 |
| WHIPSAW | SL within first 4 bars |

---

## 14. V1 Results (holdout)

| Metric | Value |
|--------|------:|
| trades | 391 |
| win_rate | 34.0% |
| profit_factor | 1.024 |
| expectancy_R | +0.016 |
| max_drawdown_R | **33** |
| false_signal_rate | 66.0% |
| whipsaw_rate | 21.0% |

---

## 15. V2 Results (holdout)

| Metric | Value |
|--------|------:|
| trades | 542 |
| win_rate | 35.4% |
| profit_factor | **1.088** |
| expectancy_R | **+0.057** |
| max_drawdown_R | **58** (worse) |
| false_signal_rate | 64.6% |
| whipsaw_rate | 23.4% |

Agreement holdout ≈ **0.741**.

---

## 16. V2 Directional While V1 WAIT

| Cohort (holdout) | count | win_rate | expectancy_R | MAE | MFE |
|------------------|------:|---------:|-------------:|----:|----:|
| V2 SHORT / V1 WAIT | **121** | 44.6% | **+0.339** | 1.09 | 1.45 |
| V2 LONG / V1 WAIT | 113 | 33.6% | +0.009 | 1.16 | 1.35 |

Lead SHORT looks like early capture of real moves — not pure noise — but more trades raise DD.

**Note:** legacy step=48 reported ~9 holdout SHORT leads; step=1 expands to **121** (same freeze, denser sampling).

---

## 17. Holdout Cohort Audit

Descriptive only — **no retune**.

Lead SHORT expectancy positive; case-level table lives in runner aggregates (`v2_lead_short_while_v1_wait`). Per-bar score dumps for all 121 are available by re-running with JSON artifact (not retuned).

---

## 18. False Signal / Whipsaw

Definitions (frozen):

- **FALSE_SIGNAL:** exit_r < 0  
- **WHIPSAW:** SL within ≤4 M15 bars  

Holdout: false slightly ↓ (66.0→64.6%); whipsaw ↑ (21.0→23.4%).

---

## 19. Drawdown / MAE / MFE

| | v1 | v2 |
|--|----|----|
| max_drawdown_R | 33 | **58** |
| MAE_R | 1.01 | 1.09 |
| MFE_R | 1.28 | 1.32 |

DD regression blocks `V2_OUTPERFORMS_ON_HOLDOUT` gate (+10R / +25% rule).

---

## 20. Limitations

1. Holdout **already observed** — not independent future proof.  
2. Gap heuristic ≠ full Exness session calendar (`data_quality=WARN`).  
3. Outcome sim ≠ live fill/slippage/commission.  
4. Validation expectancy slightly negative for v2 vs v1 in prior notes — split instability.  
5. Leverage 1:2000 irrelevant to scores.

---

## 21. Verdict

```text
PROMISING_V2_REQUIRES_MORE_DATA
PROMOTION: NO
```

Evidence supports **earlier reaction** (synthetic + lead SHORT expectancy) but **not** production promote (DD ↑, holdout observed, gaps WARN).

---

## 22. Next Research Window

**Do not** retune freeze on this holdout.

Next (separate phase, human-gated):

1. New unseen historical window **or** future live paper/demo observation window.  
2. Optional risk overlays / trade filters **without** changing TF/component weights.  
3. Only then re-evaluate promotion criteria.

---

## Reproduce

```powershell
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.market_analysis.research.run `
  --csv data/historical/XAUUSD_M15.csv --holdout --eval-step 1 `
  --json-out data/historical/m15_first_research_16_2_4A.json
```
