# M15-First Scoring Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Research-only `mtf_technical_v2_candidate` package + comparison vs v1 + `docs/M15_FIRST_SCORING_RESEARCH.md`.

**Architecture:** Isolated `market_analysis/research/` importing production helpers; never imported by production/execution.

**Tech Stack:** Python, existing export_history + load_candles_from_csv, pytest, ruff, mypy.

---

### Task 1: Research scaffolding + isolation

**Files:**
- Create `trading-engine/src/exness_bot/market_analysis/research/__init__.py`
- Create `trading-engine/src/exness_bot/market_analysis/research/identity.py`
- Create `trading-engine/tests/unit/test_phase_16_2_4_research_isolation.py`

- [ ] Add `STRATEGY_ID = "mtf_technical_v2_candidate"`
- [ ] Test: production modules under `market_analysis` (excluding research) and `execution` do not import research
- [ ] Test: identity not equal to `mtf_technical_v1`

### Task 2: Impulse + structure transition + scoring_v2

**Files:**
- Create `impulse.py`, `structure_transition.py`, `scoring_v2.py`, `freeze.py`
- Create unit tests

- [ ] Impulse from closed closes + ATR14 → [-100,100]
- [ ] Transition states + soft scores
- [ ] Soften conflict TREND=-100 STRUCTURE=+100
- [ ] Freeze dataclass with frozen config constants

### Task 3: Aggregate v2 + HTF context

**Files:**
- Create `aggregate_v2.py` + tests

- [ ] Weights 0.50/0.30/0.15/0.05
- [ ] Separate direction_score, context_warnings, blockers (explicit rules only)
- [ ] No implicit H4/D1 veto

### Task 4: Synthetic scenarios

**Files:**
- Create `scenarios.py` + `test_phase_16_2_4_scenarios.py`

- [ ] Deterministic OHLC builders for required scenarios
- [ ] Compare v1 vs v2 outputs

### Task 5: Historical pipeline

**Files:**
- Create `historical.py` (load M15, resample, gaps, split 60/20/20)
- Create tests with synthetic M15 series

- [ ] Document timezone/boundary
- [ ] Dataset report fields

### Task 6: Compare runner + CLI

**Files:**
- Create `compare.py`, CLI hook or `python -m exness_bot.market_analysis.research.run`
- Optional: try export if no CSV

- [ ] Dev → validation → freeze → holdout order
- [ ] Delay / missed ATR / false signal metrics

### Task 7: Report + validation

- [ ] Write `docs/M15_FIRST_SCORING_RESEARCH.md`
- [ ] Run pytest subset, ruff, mypy
- [ ] Single verdict; never promote v2
