"""Evaluation coverage accounting — no silent sampling."""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Lookback window for MTF features (matches live candle_history-ish research window).
WARMUP_BARS = 250
# Phase 16.2.4 silent bug (documented): step=48. Phase 16.2.4A default = 1.
EVAL_STEP_DEFAULT = 1
LEGACY_SILENT_STEP = 48


@dataclass(frozen=True)
class CoverageReport:
    TOTAL_M15_BARS: int
    WARMUP_EXCLUDED: int
    MTF_ALIGNMENT_EXCLUDED: int
    DATA_QUALITY_EXCLUDED: int
    SAMPLING_EXCLUDED: int
    OTHER_EXCLUDED: int
    FINAL_EVALUATED: int
    eval_step: int
    sampling_rule: str
    legacy_16_2_4_note: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def explain_legacy_coverage(total_m15: int, *, warmup: int = WARMUP_BARS) -> CoverageReport:
    """Explain why Phase 16.2.4 reported ~735 evals on 35973 bars."""
    eligible = max(0, total_m15 - warmup)
    legacy_eval = len(range(warmup, total_m15, LEGACY_SILENT_STEP))
    sampling_excl = max(0, eligible - legacy_eval)
    return CoverageReport(
        TOTAL_M15_BARS=total_m15,
        WARMUP_EXCLUDED=min(warmup, total_m15),
        MTF_ALIGNMENT_EXCLUDED=0,
        DATA_QUALITY_EXCLUDED=0,
        SAMPLING_EXCLUDED=sampling_excl,
        OTHER_EXCLUDED=0,
        FINAL_EVALUATED=legacy_eval,
        eval_step=LEGACY_SILENT_STEP,
        sampling_rule=(
            f"LEGACY BUG: for i in range(warmup={warmup}, n, step={LEGACY_SILENT_STEP}) "
            "— undocumented speed heuristic, not a research design choice."
        ),
        legacy_16_2_4_note=(
            "Phase 16.2.4 silently sampled every 48th eligible M15 bar. "
            "Phase 16.2.4A evaluates every eligible closed M15 bar (step=1)."
        ),
    )


def build_coverage_report(
    total_m15: int,
    *,
    warmup: int = WARMUP_BARS,
    eval_step: int = EVAL_STEP_DEFAULT,
    mtf_alignment_excluded: int = 0,
    data_quality_excluded: int = 0,
    other_excluded: int = 0,
    final_evaluated: int,
) -> CoverageReport:
    warmup_ex = min(warmup, total_m15)
    eligible = max(0, total_m15 - warmup_ex)
    # Sampling excluded = eligible bars skipped by step>1 (should be 0 when step=1)
    max_possible = len(range(warmup_ex, total_m15, eval_step))
    sampling_excl = max(0, eligible - max_possible) if eval_step > 1 else 0
    rule = (
        "Evaluate every closed M15 bar with index >= warmup; "
        f"window=last {warmup} bars; step={eval_step}."
    )
    if eval_step != 1:
        rule += " WARNING: step!=1 — not default 16.2.4A policy."
    return CoverageReport(
        TOTAL_M15_BARS=total_m15,
        WARMUP_EXCLUDED=warmup_ex,
        MTF_ALIGNMENT_EXCLUDED=mtf_alignment_excluded,
        DATA_QUALITY_EXCLUDED=data_quality_excluded,
        SAMPLING_EXCLUDED=sampling_excl,
        OTHER_EXCLUDED=other_excluded,
        FINAL_EVALUATED=final_evaluated,
        eval_step=eval_step,
        sampling_rule=rule,
        legacy_16_2_4_note=explain_legacy_coverage(total_m15, warmup=warmup).legacy_16_2_4_note,
    )
