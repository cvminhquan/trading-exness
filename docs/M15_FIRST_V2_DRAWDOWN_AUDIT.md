# M15-First V2 Drawdown Audit

**Phase:** 16.2.4A.1  
**Date:** 2026-09-09  
**Candidate:** `mtf_technical_v2_candidate` (FROZEN — unchanged)  
**Scope:** Descriptive root-cause only  
**Artifact:** `trading-engine/data/historical/m15_first_v2_drawdown_audit.json`

```text
PROMOTION: NO
v2 freeze modified: NO
filters added: NO
strategy changed: NO
order_send: NO
```

All counterfactuals are labeled **POST-HOC DESCRIPTIVE COUNTERFACTUAL**.

---

## 1. Question

Why does holdout Max DD rise from **33R (V1)** to **58R (V2)** (+25R)?

---

## 2. Equity / max DD window

| | V1 | V2 |
|--|----|----|
| Max DD | **33.0R** | **58.0R** |
| Peak cumulative R | +17.0 | +38.0 |
| Trough cumulative R | −16.0 | −20.0 |
| Peak time | 2026-06-11T07:45Z | 2026-06-16T02:45Z |
| Trough time | 2026-07-16T11:15Z | 2026-08-19T04:45Z |
| Recovery | **UNRECOVERED** | **UNRECOVERED** |
| Duration (trades) | 327 | 421 |
| Duration (M15 bars / hours) | 2282 / 570.5h | 4208 / **1052h** |
| Final cumulative R | +6.1 | **+30.8** |

V2 ends higher in R but suffers a deeper, longer unrecovered drawdown after mid-June 2026.

---

## 3. Trade frequency

| | V1 | V2 |
|--|----|----|
| Trades | 391 | **542** (+39%) |
| Trades/day | 5.22 | **7.23** |
| Median bars between trades | 12 | **8** |
| Gaps ≤8 bars | 155 | **282** |
| SIGNAL_CLUSTER rate | n/a (0) | **63.8%** (346/542) |

**SIGNAL_CLUSTER (research definition):** consecutive same-direction V2 rising-edge entries with **1…8** M15 bars between entries.

---

## 4. Cohort attribution (V2)

| Cohort | n | E[R] | PF | total_R | standalone_max_DD |
|--------|--:|-----:|---:|--------:|------------------:|
| SAME_DIRECTION (V1=V2 dir) | 313 | −0.033 | 0.95 | −10.2 | **58.0** |
| V2_SHORT_WHILE_V1_WAIT | 118 | **+0.348** | **1.63** | **+41.0** | 13.0 |
| V2_LONG_WHILE_V1_WAIT | 111 | 0.000 | 1.00 | 0.0 | 18.0 |

**Key finding:** The **58R standalone DD sits inside the SAME_DIRECTION cohort**, not inside the V2-only lead cohorts. Lead SHORT is a **net positive** edge; lead LONG is flat with moderate standalone DD.

### POST-HOC DESCRIPTIVE COUNTERFACTUAL (not a strategy)

| Exclusion | Remaining | Max DD | E[R] |
|-----------|----------:|-------:|-----:|
| Exclude LONG-while-WAIT | 431 | 56.0 | +0.072 |
| Exclude SHORT-while-WAIT | 424 | **63.0** (worse) | −0.024 |
| Exclude both leads | 313 | 58.0 | −0.033 |
| Exclude SIGNAL_CLUSTER | 196 | **51.0** | +0.066 |

Removing SHORT leads **hurts**. Removing clusters shaves ~7R DD (descriptive only).

---

## 5. LONG vs SHORT

| Side | V1 DD / E[R] | V2 DD / E[R] |
|------|--------------|--------------|
| LONG | 27 / −0.043 | **46 / −0.011** |
| SHORT | 13 / +0.070 | 30 / **+0.122** |

V2’s worse side is **LONG** (deeper DD, near-flat expectancy). SHORT remains the stronger side.

---

## 6. Regime / session

- Worst regime by standalone DD: **TRENDING_BULLISH (~50R)** — consistent with LONG toxicity in bullish/choppy continuation.
- Worst session bucket: **Asia (~32R)**.

(Session buckets are deterministic UTC hours; not a full Exness calendar.)

---

## 7. Score / impulse / latency

- Near-threshold **|score| 20–30**: n=373, E[R]=+0.13, DD=44 — large share of trades; DD high because volume is high, not uniquely toxic expectancy.
- High |impulse| (60–80): modest positive E[R], DD≈10 — impulse alone is not the DD driver.
- **Latency (lead only):**
  - 1–2 bars early: E[R]=**+0.63**, PF=2.38
  - 3–4 bars: E[R]=**+0.76**, PF=2.86
  - 5–8 bars: E[R]=+0.12
  - 9+ bars: E[R]=**−0.08**, DD=18
  - V1 never same: n=11, E[R]=**−1.0**

**Earlier is better only for short leads (≈1–4 bars).** Very early leads that V1 never confirms are toxic.

---

## 8. Concentration

- Worst 10% of losing trades account for a large share of total loss mass (see JSON `drawdown_concentration`).
- Max-DD window V2-only (lead) R contribution ≈ **−5R** with ~44% of window trades — **not** the +25R gap by itself.
- V2-only leads overall total_R ≈ **+41R** (SHORT lead dominated).

---

## 9. Loss streaks

| | V1 | V2 |
|--|----|----|
| Max consecutive losses | (see JSON) | higher frequency → longer sequences in SAME_DIRECTION path |
| Max-DD losing sequence | listed in JSON `v2_max_dd_losing_sequence` | |

---

## 10. Required answers A–M

**A. Why 33R→58R?**  
V2 takes **more trades** (391→542), with **tighter clustering** (median gap 12→8; 64% SIGNAL_CLUSTER). The unrecovered max-DD path is carried primarily by **SAME_DIRECTION** trades (standalone DD=58R). V2 **LONG** side is the weak side (DD 46R). Lead SHORT is **not** the DD culprit (E[R]+0.35).

**B. Primarily more trades?**  
**Partially.** Frequency amplifies DD, but **quality mix** matters: SAME_DIRECTION expectancy slightly negative while SHORT lead is strongly positive.

**C. Concentrated in V2-only signals?**  
**No.** Max-DD window V2-only R ≈ −5R; lead cohorts overall are net **+41R**. DD concentration is in **agreed directional** trading densified by V2.

**D. LONG or SHORT?**  
**LONG** is responsible for the worse V2 DD profile (46R vs SHORT 30R).

**E. V2_SHORT_WHILE_V1_WAIT?**  
n≈118, E[R]≈**+0.35**, PF≈1.63, standalone DD 13R — **edge cohort**, not DD source. Removing it (counterfactual) **worsens** DD to 63R.

**F. V2_LONG_WHILE_V1_WAIT?**  
n≈111, E[R]≈0, standalone DD 18R — **neutral expectancy, moderate DD**. Removing it only trims DD 58→56 (small).

**G. Regime?**  
Worst: **TRENDING_BULLISH** (~50R standalone).

**H. Session?**  
Worst: **Asia** (~32R).

**I. Near-threshold (±20–30)?**  
Large n (373) with positive E[R] but high path DD (44R) — volume effect, not uniquely bad expectancy.

**J. Impulse-driven?**  
High-impulse buckets are not the main DD engine (modest positive E[R], limited DD).

**K. Clustered?**  
**Yes.** 64% of V2 trades meet SIGNAL_CLUSTER; exclude-clustered counterfactual DD **51R**.

**L. Earlier better?**  
**Yes for 1–4 M15 bars** on lead trades. **No for 9+ / never-confirmed** leads.

**M. Next hypotheses (FUTURE UNSEEN only — do not implement now):**  
1. **Asymmetric lead quality:** preserve SHORT-while-WAIT edge; scrutinize LONG-while-WAIT / bullish-regime LONGs — without retuning freeze weights.  
2. **De-cluster / one-position semantics** for same-direction entries within ≤8 bars — test only on unseen window.

---

## 11. Safety

```text
mtf_technical_v1 modified: NO
v2 frozen config modified: NO
v2 promoted: NO
ExecutionCandidate modified: NO
Phase17 modified: NO
order_send: NO
broker mutation: NO
```

---

## 12. Reproduce

```powershell
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.market_analysis.research.run `
  --csv data/historical/XAUUSD_M15.csv --drawdown-audit `
  --json-out data/historical/m15_first_v2_drawdown_audit.json
```

**STOP.** Do not start 16.2.4B / V3 / filters / threshold changes without human review.
