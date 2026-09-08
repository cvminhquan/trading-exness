# M15_FIRST_SCORING_RESEARCH

**Phase:** 16.2.4  
**Date:** 2026-09-08  
**Candidate id:** `mtf_technical_v2_candidate` (research-only)  
**Production:** `mtf_technical_v1` — **unchanged**

```text
REAL order_send: NO
Broker mutation: NO
Execution integration: NO
Phase 17 modification: NO
v2 wired to ExecutionCandidate: NO
Promotion to production: NO
```

Spec: `docs/superpowers/specs/2026-09-08-m15-first-scoring-research-design.md`  
Plan: `docs/superpowers/plans/2026-09-08-m15-first-scoring-research.md`  
Package: `trading-engine/src/exness_bot/market_analysis/research/`

---

## 1. Current v1 formula audit

### Per-TF components (`scoring.py`)

| Component | Weight | Binary / continuous |
|-----------|--------|---------------------|
| Trend | 0.30 | UPTREND=+100, DOWNTREND=−100 |
| Structure | 0.25 | BULLISH=+100, BEARISH=−100 |
| Momentum | 0.20 | RSI + MACD |
| Location | 0.15 | support/resistance vs ATR |
| Volume | 0.10 | HIGH/LOW/NORMAL |

### MTF weights (`mtf_service.py`)

M15=0.20, H1=0.30, H4=0.30, D1=0.20 · thresholds ±20.

### Conflict behavior (v1)

H4 ≠ D1 (both non-NEUTRAL) → **final WAIT** (implicit HTF veto of base direction).

### Why v1 can WAIT after a multi-hour XAUUSD drop

1. **Structure ±100 cancels trend.**  
   `TREND=−100` + `STRUCTURE=+100` → contribution `0.30*(−100)+0.25*(+100)=−5`. Stale bullish HH/HL can nearly wipe a strong downtrend before momentum/impulse.

2. **M15 underweighted.**  
   M15 only 20% of aggregate; H1+H4 = 60%. A sharp M15 selloff is diluted by slower HTF scores still bullish/neutral.

3. **H4/D1 conflict → WAIT.**  
   Even if weighted score is directional, H4 vs D1 disagreement forces WAIT.

4. **No impulse term.**  
   ATR-normalized 1/3/4-bar closed moves are invisible to v1 scoring.

**Audit case (synthetic conflict):**

| Metric | v1 | v2 candidate |
|--------|----|--------------|
| trend | −100 | −100 |
| structure | +100 | +35 (`WEAKENING_BULLISH` + dampen 0.35) |
| total (with bearish mom/impulse) | −25 SHORT | −58.7 SHORT |
| trend+structure partial only | −5 | −19.75 |

Binary structure **is overweight** relative to intraday responsiveness.

---

## 2. V2 candidate behavior (frozen hypothesis)

### Roles / TF weights

| TF | Role | Weight |
|----|------|--------|
| M15 | PRIMARY SIGNAL | 0.50 |
| H1 | CONFIRMATION | 0.30 |
| H4 | TREND CONTEXT | 0.15 |
| D1 | MACRO CONTEXT | 0.05 |

### M15 components

Trend 0.25 · Structure 0.15 · Momentum 0.20 · Location 0.10 · Volume 0.10 · **Impulse 0.20**

### Impulse (closed only)

```
move_k = (close[t] - close[t-k]) / ATR14[t]
n(x) = 100 * tanh(x / 1.5)
impulse = 0.50*n(move_1) + 0.30*n(move_3) + 0.20*n(move_4)
```

### Structure transition

`CONFIRMED_BULLISH(+100)` · `WEAKENING_BULLISH(+40)` · `TRANSITION(0)` ·  
`WEAKENING_BEARISH(−40)` · `CONFIRMED_BEARISH(−100)`

Conflict dampen: if strong trend opposes strong structure → structure × 0.35.

### HTF semantics

- Context warnings: `CONTEXT_H4_DISAGREES_M15`, `CONTEXT_D1_DISAGREES_M15`, …
- **No implicit H4/D1 veto**
- Explicit rule `HIGHER_TF_STRONG_CONFLICT` exists, **disabled** in frozen config (tested ON/OFF)

### Leverage

Not used in scoring / confidence / volume.

---

## 3. Historical dataset

| Field | Value |
|-------|-------|
| Source | Exness DEMO MT5 via `export_history` (read-only) |
| Broker symbol | XAUUSDm (canonical XAUUSD) |
| Path | `trading-engine/data/historical/XAUUSD_M15.csv` |
| Timezone | UTC |
| Start | 2025-03-02T23:00:00+00:00 |
| End | 2026-09-08T16:00:00+00:00 |
| M15 candles | 35 973 |
| H1 (resample) | 9 000 |
| H4 (resample) | 2 433 |
| D1 (resample) | 474 |
| Duplicates | 0 |
| Session/missing gaps (est.) | present (weekend + thin sessions); exporter reported unexpected gaps=5 |
| Split | chronological 60% / 20% / 20% |
| Sufficient for split | YES (≥5 000 M15) |

Pipeline: **M15 canonical → deterministic UTC resample H1/H4/D1 → closed candles only.**

---

## 4. Synthetic scenario comparison

Representative end-of-series decisions (rolling window analysis):

| Scenario | v1 score | v1 | v2 score | v2 | M15 impulse |
|----------|----------|----|----------|----|-------------|
| sideways | +6.6 | WAIT | ~0..−13 | WAIT | ~−2 |
| normal_bullish | +20.2 | LONG | ~+27 | LONG | ~+39 |
| normal_bearish | −20.2 | SHORT | ~−27 | SHORT | ~−39 |
| **sharp_1h_selloff** | **−16.2** | **WAIT** | **~−21..−23** | **SHORT** | ~−20 |
| sharp_4h_selloff | −20.2 | SHORT | ~−22 | SHORT | ~−15 |
| bullish_pullback_in_bearish | −9.6 | WAIT | WAIT | WAIT | ~−33 |
| false_breakout | +10.3 | WAIT | WAIT | WAIT | ~+12 |
| v_reversal | −0.6 | WAIT | varies | WAIT/LONG | ~+36 |
| m15_bearish_vs_h4_bullish | −29 | SHORT | more short | SHORT | strong − |
| m15_bullish_vs_d1_bearish | +31 | LONG | LONG | LONG | strong + |

### Signal delay (sharp 1h selloff synthetic)

| Metric | v1 | v2 |
|--------|----|----|
| Delay after event (M15 bars) | **never SHORT in window** (`null`) | **0** |
| Price move missed to first SHORT | n/a (no signal) | ~0 |
| Candles saved | n/a | v2 leads |

This is the clearest answer to *“why WAIT while gold already dumped for hours?”*: v1 score stuck in WAIT zone (−16) under M15-light weights + no impulse; v2 crosses −20.

---

## 5. Historical split results (signal timing walk, step=48, lookback=250)

Config **frozen before holdout** (see `freeze_snapshot` in research JSON).

| Split | bars | v1 L/S/W | v2 L/S/W | agree | v2 SHORT while v1 WAIT |
|-------|------|----------|----------|-------|-------------------------|
| Development 60% | 445 | 175/115/155 | 178/107/160 | 78.2% | 16 |
| Validation 20% | 145 | 44/49/52 | 41/51/53 | 82.8% | 6 |
| Holdout 20% | 145 | 41/45/59 | 43/45/57 | 75.2% | 9 |

Interpretation: v2 is **somewhat more willing to leave WAIT into SHORT** on the same windows, without exploding disagreement (agree ~75–83%). Not a full trade backtest.

---

## 6. Risk / performance comparison (trade-sim)

| Metric | Status |
|--------|--------|
| Trade count / win rate / PF / expectancy R | **Not computed** (no execution simulator on v2 setups this phase) |
| Max drawdown / MAE / MFE / avg R | **Not computed** |
| False breakout rate / whipsaw PnL | **Qualitative only** via synthetic false_breakout (both WAIT) |

Claiming `V2_OUTPERFORMS_ON_HOLDOUT` would require frozen trade rules + holdout PnL edge. **Not available → cannot claim outperform.**

---

## 7. Limitations

1. Historical walk samples every 48 M15 bars (speed); not every bar.
2. HTF built by resampling M15 (broker-native H1/H4/D1 may differ slightly at session edges).
3. No full SL/TP / spread / slippage trade simulation for v1 vs v2.
4. Synthetic HTF depth limited on short series (H4/D1 often insufficient).
5. Impulse/weights are **initial hypothesis**, not grid-searched (by design).
6. CSV is local/gitignored; reproduce via `export_history`.

---

## 8. Safety / isolation

- Production `market_analysis` (excluding `research/`) + `execution` + `api` **do not import** research (AST test).
- `mtf_technical_v2_candidate` ≠ `mtf_technical_v1`.
- CLI: `python -m exness_bot.market_analysis.research.run --csv ... [--holdout]`

---

## 9. Recommendation

Keep **production** on `mtf_technical_v1`. Continue research on v2 for:

- impulse + soft structure as responsiveness levers  
- optional later: setup/trade simulator on frozen config  
- only then reconsider holdout PnL verdict

**Do not promote v2 to Phase 17 / ExecutionCandidate in this phase.**

---

## 10. Final verdict

```text
PROMISING_V2_REQUIRES_MORE_DATA
```

Rationale:

- Synthetic + audit show **clear mechanism** for v1 WAIT lag after sharp M15 selloffs.
- Phase **16.2.4A** fixed silent `step=48` sampling → full **35723** eligible bars; holdout expectancy/PF improved and V2-lead SHORT expectancy +0.34, but **max_drawdown_R worsened 33→58** and validation was unstable.
- See `docs/PHASE_16_2_4A_VALIDATION_HARDENING.md`.

**Do not promote v2** to Phase 17 / ExecutionCandidate.

---

## 11. Master phase follow-up

Combined dashboard + research report:

`docs/MASTER_PHASE_RESEARCH_DASHBOARD_REPORT.md`

Holdout discipline unchanged: freeze immutable; no retune on observed holdout; independent proof needs forward/unseen window.
