"""Research comparison runner — Phase 16.2.4A validation hardening."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from exness_bot.market_analysis.research.coverage import explain_legacy_coverage
from exness_bot.market_analysis.research.delay_metrics import (
    explain_impulse_at_end,
    measure_selloff_response_delay,
)
from exness_bot.market_analysis.research.freeze import (
    DEFAULT_V2_CONFIG,
    V2FrozenConfig,
    assert_config_frozen,
    assert_freeze_matches_16_2_4,
    freeze_snapshot_dict,
)
from exness_bot.market_analysis.research.gaps import classify_m15_gaps
from exness_bot.market_analysis.research.historical import (
    discover_default_m15_path,
    load_m15_csv,
    validate_dataset,
)
from exness_bot.market_analysis.research.scenarios import (
    audit_binary_structure_overweight,
    build_scenarios,
    run_scenario_suite,
)
from exness_bot.market_analysis.research.validate_walk import walk_series


def _bundle_dict(bundle: Any) -> dict[str, Any]:
    return {
        "signal_stats": bundle.signal_stats,
        "outcomes_v1": bundle.outcomes_v1.as_dict(),
        "outcomes_v2": bundle.outcomes_v2.as_dict(),
        "v2_lead_long_while_v1_wait": bundle.lead_long.as_dict(),
        "v2_lead_short_while_v1_wait": bundle.lead_short.as_dict(),
    }


def _interpret(
    *,
    selloff_1h: dict[str, Any],
    selloff_4h: dict[str, Any],
    historical: dict[str, Any],
) -> dict[str, Any]:
    v2_faster_1h = False
    d1 = selloff_1h.get("v1_delay_bars")
    d2 = selloff_1h.get("v2_delay_bars")
    if d2 is not None and (d1 is None or (isinstance(d1, int) and d2 < d1)):
        v2_faster_1h = True

    holdout = historical.get("holdout") if historical.get("available") else None
    lead = None
    if holdout:
        lead = holdout.get("v2_lead_short_while_v1_wait")

    return {
        "A_latency_reduced": v2_faster_1h,
        "B_latency_delta": {
            "candles_saved_1h": selloff_1h.get("candles_saved"),
            "v1_delay_minutes_1h": selloff_1h.get("v1_delay_minutes"),
            "v2_delay_minutes_1h": selloff_1h.get("v2_delay_minutes"),
            "missed_atr_v1_1h": selloff_1h.get("missed_atr_v1"),
            "missed_atr_v2_1h": selloff_1h.get("missed_atr_v2"),
            "selloff_4h": {
                "v1_delay_bars": selloff_4h.get("v1_delay_bars"),
                "v2_delay_bars": selloff_4h.get("v2_delay_bars"),
                "candles_saved": selloff_4h.get("candles_saved"),
                "missed_atr_v1": selloff_4h.get("missed_atr_v1"),
                "missed_atr_v2": selloff_4h.get("missed_atr_v2"),
            },
        },
        "C_false_signal_whipsaw": {
            "note": "See development/validation/holdout outcomes_v1 vs outcomes_v2",
            "holdout_v1": None if not holdout else holdout.get("outcomes_v1"),
            "holdout_v2": None if not holdout else holdout.get("outcomes_v2"),
        },
        "D_holdout_v2_short_while_v1_wait": lead,
        "E_enough_evidence_m15_first_better": False,
        "E_rationale": (
            "Latency improvement on synthetic is clear; historical lead-group and "
            "full-coverage expectancy must both be favorable without large whipsaw "
            "regression before claiming outperform."
        ),
    }


def _decide_verdict(
    *,
    historical: dict[str, Any],
    interpretation: dict[str, Any],
    gaps_quality: str,
) -> str:
    if not historical.get("available"):
        return "PROMISING_V2_REQUIRES_MORE_DATA"
    if gaps_quality == "FAIL":
        return "PROMISING_V2_REQUIRES_MORE_DATA"
    if not historical.get("holdout_ran"):
        return "PROMISING_V2_REQUIRES_MORE_DATA"

    holdout = historical.get("holdout") or {}
    ov1 = holdout.get("outcomes_v1") or {}
    ov2 = holdout.get("outcomes_v2") or {}
    lead = holdout.get("v2_lead_short_while_v1_wait") or {}

    # Strict gate for V2_OUTPERFORMS_ON_HOLDOUT
    latency_ok = interpretation.get("A_latency_reduced") is True
    cov = historical.get("coverage") or {}
    coverage_ok = cov.get("eval_step") == 1 and cov.get("SAMPLING_EXCLUDED", 1) == 0
    exp1 = ov1.get("expectancy_R")
    exp2 = ov2.get("expectancy_R")
    pf1 = ov1.get("profit_factor")
    pf2 = ov2.get("profit_factor")
    whip1 = ov1.get("whipsaw_rate")
    whip2 = ov2.get("whipsaw_rate")

    expectancy_ok = (
        exp1 is not None
        and exp2 is not None
        and exp2 >= exp1 - 0.05  # no significant degradation
    )
    pf_ok = True
    if pf1 is not None and pf2 is not None:
        pf_ok = pf2 >= pf1 * 0.9
    whip_ok = True
    if whip1 is not None and whip2 is not None:
        whip_ok = whip2 <= whip1 + 0.05
    dd1 = ov1.get("max_drawdown_R")
    dd2 = ov2.get("max_drawdown_R")
    dd_ok = True
    if isinstance(dd1, (int, float)) and isinstance(dd2, (int, float)):
        # Drawdown must not worsen materially (absolute +10R or +25%)
        dd_ok = dd2 <= max(dd1 + 10.0, dd1 * 1.25)
    lead_exp = lead.get("expectancy_R")
    lead_count = int(lead.get("count") or 0)
    lead_ok = lead_count == 0 or (isinstance(lead_exp, (int, float)) and lead_exp > 0)

    if (
        latency_ok
        and coverage_ok
        and expectancy_ok
        and pf_ok
        and whip_ok
        and dd_ok
        and lead_ok
        and exp2 is not None
        and exp2 > 0
        and ov2.get("trade_count", 0) >= 20
    ):
        return "V2_OUTPERFORMS_ON_HOLDOUT"

    return "PROMISING_V2_REQUIRES_MORE_DATA"


def run_research(
    *,
    csv_path: Path | None = None,
    config: V2FrozenConfig = DEFAULT_V2_CONFIG,
    run_holdout: bool = False,
    eval_step: int = 1,
) -> dict[str, Any]:
    """Execute research pipeline with 16.2.4A hardening. Does not retune freeze."""
    assert_config_frozen(config)
    assert_freeze_matches_16_2_4(config)

    scenarios = [asdict(r) for r in run_scenario_suite()]
    sc = build_scenarios()
    selloff_1h = measure_selloff_response_delay(sc["sharp_1h_selloff"], label="sharp_1h").as_dict()
    selloff_4h = measure_selloff_response_delay(sc["sharp_4h_selloff"], label="sharp_4h").as_dict()
    impulse_audit = {
        "sharp_1h": explain_impulse_at_end(sc["sharp_1h_selloff"], label="sharp_1h_selloff"),
        "sharp_4h": explain_impulse_at_end(sc["sharp_4h_selloff"], label="sharp_4h_selloff"),
    }
    audit = audit_binary_structure_overweight()

    path = csv_path or discover_default_m15_path()
    if path is not None and path.exists():
        m15 = load_m15_csv(path, symbol="XAUUSD")
        report, _frames = validate_dataset(
            m15, path=path, broker_symbol="XAUUSDm"
        )
        gap_report = classify_m15_gaps(m15)
        legacy = explain_legacy_coverage(len(m15))
        walk = walk_series(
            m15, config=config, run_holdout=run_holdout, eval_step=eval_step
        )
        historical: dict[str, Any] = {
            "available": True,
            "dataset": {
                "broker_symbol": report.broker_symbol,
                "path": report.path,
                "timezone": report.timezone,
                "start": report.start.isoformat() if report.start else None,
                "end": report.end.isoformat() if report.end else None,
                "m15_count": report.m15_count,
                "h1_count": report.h1_count,
                "h4_count": report.h4_count,
                "d1_count": report.d1_count,
                "sufficient_for_split": report.sufficient_for_split,
                "notes": list(report.notes),
            },
            "gaps": gap_report.as_dict(),
            "coverage_legacy_16_2_4": legacy.as_dict(),
            "coverage": walk.coverage,
            "freeze_snapshot": freeze_snapshot_dict(config),
            "development": _bundle_dict(walk.development),
            "validation": _bundle_dict(walk.validation),
            "holdout": _bundle_dict(walk.holdout) if walk.holdout else None,
            "holdout_ran": walk.holdout is not None,
            "research_trade_assumptions": {
                "entry": "close of signal bar",
                "sl_atr_mult": 1.5,
                "tp_r_mult": 2.0,
                "horizon_m15_bars": 96,
                "whipsaw_bars": 4,
                "execution_engine": False,
            },
        }
        gaps_quality = gap_report.data_quality
    else:
        historical = {
            "available": False,
            "reason": "No M15 CSV under data/historical — export via export_history",
        }
        gaps_quality = "OK"

    interpretation = _interpret(
        selloff_1h=selloff_1h, selloff_4h=selloff_4h, historical=historical
    )
    # Fill E from holdout lead expectancy if available
    if historical.get("holdout"):
        lead = historical["holdout"]["v2_lead_short_while_v1_wait"]
        ov2 = historical["holdout"]["outcomes_v2"]
        interpretation["E_enough_evidence_m15_first_better"] = bool(
            interpretation["A_latency_reduced"]
            and lead.get("expectancy_R") is not None
            and lead.get("expectancy_R") > 0
            and ov2.get("expectancy_R") is not None
            and ov2.get("expectancy_R") > 0
        )

    verdict = _decide_verdict(
        historical=historical,
        interpretation=interpretation,
        gaps_quality=gaps_quality,
    )

    return {
        "phase": "16.2.4A",
        "strategy_v1": "mtf_technical_v1",
        "strategy_v2": config.strategy_id,
        "scenarios": scenarios,
        "selloff_1h": selloff_1h,
        "selloff_4h": selloff_4h,
        "impulse_audit": impulse_audit,
        "structure_audit": audit,
        "historical": historical,
        "interpretation": interpretation,
        "verdict": verdict,
        "leverage_note": "Leverage excluded from scoring; not used in this research.",
        "promotion": "NO — research only",
        "freeze_discipline": "UNCHANGED from Phase 16.2.4 snapshot",
    }
