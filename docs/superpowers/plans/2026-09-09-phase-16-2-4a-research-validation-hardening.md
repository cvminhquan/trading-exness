# Phase 16.2.4A — Research Validation Hardening Plan

> **For agentic workers:** Harden existing research harness; do not retune frozen v2; do not promote.

**Goal:** Complete audit + test + report gaps for M15-first v2 research validation without changing production or frozen v2 weights.

**Architecture:** Extend `market_analysis/research/` (already isolated). Prefer small additive tests + report completion over rewrite.

**Tech Stack:** Python, pytest, existing research package

## Global Constraints

- RESEARCH ONLY; no order_send / ExecutionCandidate / Phase17 / v1 modify / v2 retune
- Holdout already observed — no tuning from holdout
- Frozen snapshot must match assert_freeze_matches_16_2_4

## File map

| File | Role |
|------|------|
| `research/freeze.py` | Frozen config (verify only) |
| `research/coverage.py` | Coverage accounting |
| `research/gaps.py` | Gap classification |
| `research/outcomes.py` | Trade sim metrics |
| `research/compare.py` | Orchestrator / verdict |
| `tests/unit/test_phase_16_2_4a_*.py` | Missing unit coverage |
| `docs/M15_FIRST_SCORING_RESEARCH.md` | Full research writeup |
| `docs/PHASE_16_2_4A_VALIDATION_HARDENING.md` | Phase report + A–S |

## Tasks

1. Verify freeze + JSON artifact answers coverage/gaps/latency
2. Add unit tests: outcomes, gaps, walk_series step, verdict gate
3. Refresh docs with required structure + A–S
4. ruff / mypy / pytest
5. Stop for human review (no 16.2.4B)
