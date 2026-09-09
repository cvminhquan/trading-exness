# Phase 16.2.4A.2 — Unseen Forward Validation Protocol

## Goal

Lock a research-only forward validation harness for `mtf_technical_v1` vs frozen `mtf_technical_v2_candidate` without optimizing either strategy.

## Files

| Path | Responsibility |
|------|----------------|
| `research/forward/protocol.py` | Cutoff, hypotheses, fingerprints, evidence gates, contamination |
| `research/forward/store.py` | Isolated forward CSV + provenance + quality |
| `research/forward/journal.py` | Append-only signal journal (PRECOMMITTED schema + RETROSPECTIVE) |
| `research/forward/collect.py` | Manual idempotent read-only MT5 collector |
| `research/forward/evaluate.py` | Warmup + forward walk + outcome maturation |
| `research/forward/report.py` | State/report JSON builders |
| `research/forward/__main__.py` | CLI: collect \| status \| evaluate \| report \| init |
| `tests/unit/test_phase_16_2_4a2_forward_validation.py` | Deterministic protocol tests |
| `docs/M15_FIRST_FORWARD_VALIDATION.md` | Human report |
| `data/forward/*` | Artifacts |

## Constraints

- No V1/V2/Execution/Phase17/order_send changes
- PRECOMMITTED journal support only — no CandleEngine wire
- Init uses RETROSPECTIVE_REPLAY
- Expected evidence: `INSUFFICIENT_FORWARD_DATA`
