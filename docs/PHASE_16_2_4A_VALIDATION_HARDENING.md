# PHASE 16.2.4A — RESEARCH VALIDATION HARDENING

**STATUS:** PASS  
**RESEARCH VERDICT:** `PROMISING_V2_REQUIRES_MORE_DATA`  
**PROMOTION:** NO  
**Freeze:** UNCHANGED (`assert_freeze_matches_16_2_4`)  
**Artifact:** `trading-engine/data/historical/m15_first_research_16_2_4A.json`  
**Research writeup:** `docs/M15_FIRST_SCORING_RESEARCH.md`

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

## Final answers (A–S)

| # | Question | Answer |
|---|----------|--------|
| **A** | Why 35 973 → ~735 evals? | Legacy silent `step=48` after warmup 250 → **745** evals (~735 reported). Not a data bug. |
| **B** | Eligible after harden? | **35 723** (`step=1`, sampling=0) |
| **C** | Gaps expected vs unexpected? | **389** expected · **5** unexpected · quality **WARN** |
| **D** | Resample look-ahead free? | **YES** (prefix resample + unit tests) |
| **E** | V2 improves 1h selloff? | **YES** — v1 WAIT; v2 SHORT @ +3 bars / 45 min |
| **F** | V2 improves 4h selloff? | **YES** — 16→4 bars; **12 candles / 180 min saved** |
| **G** | Bars saved? | Synthetic 4h: **12**; 1h: n/a (v1 never signaled) |
| **H** | Minutes saved? | Synthetic 4h: **180**; 1h path: v2 at 45 vs v1 ∞ |
| **I** | Price/ATR saved? | 4h missed ATR 28→7 (**~21 ATR**); missed price USD 56→14 |
| **J** | False signals ↑? | Holdout **slightly ↓** 66.0%→64.6% |
| **K** | Whipsaws ↑? | Holdout **mildly ↑** 21.0%→23.4% |
| **L** | PF v1 vs v2? | Holdout **1.024 vs 1.088** |
| **M** | Expectancy R? | Holdout **+0.016 vs +0.057** |
| **N** | Max DD R? | Holdout **33 vs 58** (v2 worse — gate fail) |
| **O** | V2 dir / V1 WAIT? | SHORT lead **121**, expectancy **+0.339**; LONG lead 113, ~flat |
| **P** | Prior ~9 SHORT cases? | Artifact of step=48; step=1 → **121** SHORT leads (descriptive) |
| **Q** | Support M15-first? | **Promising latency + lead SHORT**, not promote-ready |
| **R** | Missing evidence? | Unseen future/window; DD control; calendar-grade gaps; live fills |
| **S** | Next validation? | New unseen window **without** freeze retune; optional filters only |

---

## Coverage (summary)

| | Legacy 16.2.4 | 16.2.4A |
|--|--------------:|--------:|
| TOTAL_M15 | 35973 | 35973 |
| WARMUP | 250 | 250 |
| SAMPLING_EXCLUDED | 34978 | **0** |
| FINAL_EVALUATED | 745 | **35723** |
| eval_step | 48 | **1** |

Accounting model: **first-exclusion** mutually exclusive buckets.

---

## Data quality

expected_gaps=389 · unexpected=5 · largest_unexpected≈4395 min · duplicates=0 · **WARN**

Limitation: deterministic Fri/Mon + δ≤4h heuristic — not full Exness calendar.

---

## No-look-ahead / synthetic latency

Resample closed-bucket only. 1h: v2 only. 4h: 12 M15 candles saved. Impulse −20.20 vs −14.65 explained by end-tail ATR path (not bug).

---

## Holdout metrics

| | v1 | v2 |
|--|---:|---:|
| trades | 391 | 542 |
| PF | 1.024 | 1.088 |
| E[R] | +0.016 | +0.057 |
| DD_R | 33 | **58** |
| false | 66.0% | 64.6% |
| whipsaw | 21.0% | 23.4% |

Verdict gate rejects `V2_OUTPERFORMS_ON_HOLDOUT` because DD worsens beyond +10R / +25%.

---

## Tests added / used

- `tests/unit/test_phase_16_2_4a_hardening.py` — freeze, coverage, gaps, outcomes, verdict gate  
- `tests/unit/test_phase_16_2_4a_resample_alignment.py`  
- `tests/unit/test_phase_16_2_4_m15_first_research.py`

---

## Files

| Path | Role |
|------|------|
| `market_analysis/research/*` | Harness (pre-existing + hardened) |
| `tests/unit/test_phase_16_2_4a_hardening.py` | New unit coverage |
| `docs/M15_FIRST_SCORING_RESEARCH.md` | Full 22-section research |
| `docs/PHASE_16_2_4A_VALIDATION_HARDENING.md` | This report |
| `docs/superpowers/plans/2026-09-09-phase-16-2-4a-research-validation-hardening.md` | Plan |

---

## Reproduce

```powershell
cd trading-engine
.\.venv\Scripts\python.exe -m exness_bot.market_analysis.research.run `
  --csv data/historical/XAUUSD_M15.csv --holdout --eval-step 1 `
  --json-out data/historical/m15_first_research_16_2_4A.json
```

**Stop:** do not start 16.2.4B / retune / promote without human review.
