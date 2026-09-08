"""Full-series validation walk — every eligible M15 bar (step=1 by default)."""

from __future__ import annotations

from dataclasses import dataclass, field

from exness_bot.domain.models import Candle
from exness_bot.market_analysis.research.analyze import evaluate_mtf_window
from exness_bot.market_analysis.research.coverage import (
    WARMUP_BARS,
    build_coverage_report,
)
from exness_bot.market_analysis.research.freeze import V2FrozenConfig
from exness_bot.market_analysis.research.historical import chronological_split
from exness_bot.market_analysis.research.outcomes import (
    LeadGroupStats,
    OutcomeStats,
    ResearchTrade,
    simulate_trade,
    summarize_lead_group,
    summarize_trades,
)


@dataclass
class SplitBundle:
    signal_stats: dict[str, object]
    outcomes_v1: OutcomeStats
    outcomes_v2: OutcomeStats
    lead_long: LeadGroupStats
    lead_short: LeadGroupStats


@dataclass
class WalkResult:
    coverage: dict[str, object]
    development: SplitBundle
    validation: SplitBundle
    holdout: SplitBundle | None
    mtf_alignment_excluded: int = 0


def _empty_counts() -> dict[str, int]:
    return {"LONG": 0, "SHORT": 0, "WAIT": 0}


def walk_series(
    m15: list[Candle],
    *,
    config: V2FrozenConfig,
    run_holdout: bool,
    eval_step: int = 1,
    warmup: int = WARMUP_BARS,
    progress_every: int = 1000,
) -> WalkResult:
    """Evaluate every eligible closed M15 bar; assign to chrono splits by index."""
    n = len(m15)
    split = chronological_split(m15)
    i_dev = len(split.development)
    i_val = i_dev + len(split.validation)

    # Per-split accumulators
    @dataclass
    class Acc:
        v1: dict[str, int] = field(default_factory=_empty_counts)
        v2: dict[str, int] = field(default_factory=_empty_counts)
        agree: int = 0
        n: int = 0
        trades_v1: list[ResearchTrade] = field(default_factory=list)
        trades_v2: list[ResearchTrade] = field(default_factory=list)
        lead_long: list[ResearchTrade] = field(default_factory=list)
        lead_short: list[ResearchTrade] = field(default_factory=list)
        prev_v1: str = "WAIT"
        prev_v2: str = "WAIT"

    accs = {
        "development": Acc(),
        "validation": Acc(),
        "holdout": Acc(),
    }

    def which_split(idx: int) -> str | None:
        if idx < i_dev:
            return "development"
        if idx < i_val:
            return "validation"
        if run_holdout:
            return "holdout"
        return None

    mtf_excl = 0
    evaluated = 0

    for i in range(warmup, n, eval_step):
        bucket = which_split(i)
        if bucket is None:
            continue
        acc = accs[bucket]
        v1, v2, atr = evaluate_mtf_window(
            m15[: i + 1], config=config, min_bars=60, lookback=warmup
        )
        if v1.weighted_score is None and v2.weighted_score is None:
            mtf_excl += 1
            continue

        evaluated += 1
        acc.n += 1
        acc.v1[v1.direction] = acc.v1.get(v1.direction, 0) + 1
        acc.v2[v2.direction] = acc.v2.get(v2.direction, 0) + 1
        if v1.direction == v2.direction:
            acc.agree += 1

        # Rising-edge signals → forward outcome
        if atr is not None and atr > 0:
            if v1.direction in {"LONG", "SHORT"} and acc.prev_v1 == "WAIT":
                t = simulate_trade(
                    m15, signal_index=i, direction=v1.direction, atr=atr, source="v1"
                )
                if t:
                    acc.trades_v1.append(t)
            if v2.direction in {"LONG", "SHORT"} and acc.prev_v2 == "WAIT":
                t = simulate_trade(
                    m15, signal_index=i, direction=v2.direction, atr=atr, source="v2"
                )
                if t:
                    acc.trades_v2.append(t)
            # V2 leads while V1 WAIT
            if v2.direction == "LONG" and v1.direction == "WAIT" and acc.prev_v2 != "LONG":
                t = simulate_trade(
                    m15, signal_index=i, direction="LONG", atr=atr, source="v2_lead_long"
                )
                if t:
                    acc.lead_long.append(t)
            if v2.direction == "SHORT" and v1.direction == "WAIT" and acc.prev_v2 != "SHORT":
                t = simulate_trade(
                    m15,
                    signal_index=i,
                    direction="SHORT",
                    atr=atr,
                    source="v2_lead_short",
                )
                if t:
                    acc.lead_short.append(t)

        acc.prev_v1 = v1.direction
        acc.prev_v2 = v2.direction

        if progress_every and evaluated % progress_every == 0:
            print(f"[research-walk] evaluated={evaluated} bar={i}/{n}", flush=True)

    def bundle(acc: Acc) -> SplitBundle:
        return SplitBundle(
            signal_stats={
                "bars_evaluated": acc.n,
                "v1_long": acc.v1.get("LONG", 0),
                "v1_short": acc.v1.get("SHORT", 0),
                "v1_wait": acc.v1.get("WAIT", 0),
                "v2_long": acc.v2.get("LONG", 0),
                "v2_short": acc.v2.get("SHORT", 0),
                "v2_wait": acc.v2.get("WAIT", 0),
                "agreement_rate": round(acc.agree / acc.n, 4) if acc.n else 0.0,
                "v2_led_long_while_v1_wait": len(acc.lead_long),
                "v2_led_short_while_v1_wait": len(acc.lead_short),
            },
            outcomes_v1=summarize_trades(acc.trades_v1),
            outcomes_v2=summarize_trades(acc.trades_v2),
            lead_long=summarize_lead_group(acc.lead_long),
            lead_short=summarize_lead_group(acc.lead_short),
        )

    coverage = build_coverage_report(
        n,
        warmup=warmup,
        eval_step=eval_step,
        mtf_alignment_excluded=mtf_excl,
        final_evaluated=evaluated,
    )
    return WalkResult(
        coverage=coverage.as_dict(),
        development=bundle(accs["development"]),
        validation=bundle(accs["validation"]),
        holdout=bundle(accs["holdout"]) if run_holdout else None,
        mtf_alignment_excluded=mtf_excl,
    )
