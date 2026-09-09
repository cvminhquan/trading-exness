# Phase 16.2.4A.1 — V2 Drawdown Root-Cause Audit Plan

> **For agentic workers:** Descriptive audit only. Do NOT retune freeze or add filters.

**Goal:** Explain why V2 holdout max DD rises 33R→58R via equity reconstruction and cohort attribution.

**Architecture:** New research-only module `drawdown_audit.py` + CLI flag; reuse `evaluate_mtf_window` / `simulate_trade`; freeze asserted; no strategy changes.

**Tech Stack:** Python research package, pytest

## Global Constraints

- Frozen V2 immutable
- POST-HOC DESCRIPTIVE COUNTERFACTUAL only for exclusions
- No 16.2.4B / filters / promotion

## Files

| File | Role |
|------|------|
| `research/drawdown_audit.py` | Collect enriched trades + analyze |
| `research/run.py` | `--drawdown-audit` CLI |
| `tests/unit/test_phase_16_2_4a1_drawdown_audit.py` | Deterministic unit tests |
| `docs/M15_FIRST_V2_DRAWDOWN_AUDIT.md` | Report A–M |
| `data/historical/m15_first_v2_drawdown_audit.json` | Machine output |

## Tasks

1. Unit tests for equity/DD episode helpers on synthetic trades
2. Implement collect + analyze
3. Run holdout audit on CSV
4. Write markdown answers A–M
5. Stop for human review
