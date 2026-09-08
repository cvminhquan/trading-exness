"""Phase 16.2.4 — research isolation + core unit tests."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.contract.identity import MTF_STRATEGY_ID
from exness_bot.market_analysis.research.aggregate_v2 import TfScoreInput, aggregate_v2
from exness_bot.market_analysis.research.freeze import DEFAULT_V2_CONFIG
from exness_bot.market_analysis.research.historical import (
    chronological_split,
    count_m15_gaps,
    resample_from_m15,
    validate_dataset,
)
from exness_bot.market_analysis.research.identity import (
    PRODUCTION_STRATEGY_ID,
    RESEARCH_STRATEGY_ID,
)
from exness_bot.market_analysis.research.impulse import ImpulseBreakdown, compute_impulse_score
from exness_bot.market_analysis.research.scenarios import (
    audit_binary_structure_overweight,
    build_scenarios,
    measure_selloff_response_delay,
    run_scenario_suite,
)
from exness_bot.market_analysis.research.scoring_v2 import (
    ScoreBreakdownV2,
    audit_trend_structure_conflict_case,
)
from exness_bot.market_analysis.research.structure_transition import StructureTransition

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "exness_bot"


def test_research_id_not_production() -> None:
    assert RESEARCH_STRATEGY_ID == "mtf_technical_v2_candidate"
    assert RESEARCH_STRATEGY_ID != MTF_STRATEGY_ID
    assert PRODUCTION_STRATEGY_ID == MTF_STRATEGY_ID


def test_production_and_execution_do_not_import_research() -> None:
    banned_prefix = "exness_bot.market_analysis.research"
    offenders: list[str] = []
    scan_dirs = [
        SRC_ROOT / "market_analysis",
        SRC_ROOT / "execution",
        SRC_ROOT / "api",
    ]
    for base in scan_dirs:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "market_analysis" in path.parts and "research" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(banned_prefix):
                            offenders.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod.startswith(banned_prefix):
                        offenders.append(f"{path}: from {mod}")
    assert offenders == []


def test_impulse_closed_only_no_lookahead() -> None:
    closes = [100.0, 100.0, 100.0, 100.0, 97.0]
    out = compute_impulse_score(closes, atr14=2.0)
    assert out.move_1 is not None
    assert out.move_1 == pytest.approx((97 - 100) / 2.0)
    assert out.impulse_score < 0


def test_structure_conflict_dampen_vs_v1_partial() -> None:
    audit = audit_trend_structure_conflict_case()
    # v1: -30+25=-5; v2 dampened structure contributes less cancellation of trend
    assert audit["v1_trend_structure_contribution"] == pytest.approx(-5.0)
    assert float(audit["v2_trend_structure_contribution"]) < -5.0


def test_aggregate_v2_no_implicit_h4_d1_veto() -> None:
    def _score(total: float, direction: str) -> ScoreBreakdownV2:
        return ScoreBreakdownV2(
            trend_score=total,
            structure_score=0.0,
            structure_raw_binary=0.0,
            structure_transition=StructureTransition.TRANSITION,
            momentum_score=0.0,
            location_score=0.0,
            volume_score=0.0,
            impulse_score=total if direction != "NEUTRAL" else 0.0,
            impulse=ImpulseBreakdown(None, None, None, 0.0, None),
            total_score=total,
            confidence=50.0,
            direction=direction,
            conflict_dampened=False,
        )

    # Strong M15 short, H4 long, D1 long — default config must NOT block
    result = aggregate_v2(
        [
            TfScoreInput("M15", _score(-60.0, "SHORT")),
            TfScoreInput("H1", _score(-40.0, "SHORT")),
            TfScoreInput("H4", _score(50.0, "LONG")),
            TfScoreInput("D1", _score(40.0, "LONG")),
        ],
        config=DEFAULT_V2_CONFIG,
    )
    assert "HIGHER_TF_STRONG_CONFLICT" not in result.blockers
    assert "CONTEXT_H4_DISAGREES_M15" in result.context_warnings
    assert result.direction == "SHORT"


def test_explicit_higher_tf_blocker_when_enabled() -> None:
    from dataclasses import replace

    cfg = replace(DEFAULT_V2_CONFIG, higher_tf_strong_conflict_enabled=True)

    def _score(total: float, direction: str) -> ScoreBreakdownV2:
        return ScoreBreakdownV2(
            trend_score=total,
            structure_score=0.0,
            structure_raw_binary=0.0,
            structure_transition=StructureTransition.TRANSITION,
            momentum_score=0.0,
            location_score=0.0,
            volume_score=0.0,
            impulse_score=0.0,
            impulse=ImpulseBreakdown(None, None, None, 0.0, None),
            total_score=total,
            confidence=50.0,
            direction=direction,
            conflict_dampened=False,
        )

    result = aggregate_v2(
        [
            TfScoreInput("M15", _score(-30.0, "SHORT")),
            TfScoreInput("H1", _score(-20.0, "SHORT")),
            TfScoreInput("H4", _score(50.0, "LONG")),
            TfScoreInput("D1", _score(40.0, "LONG")),
        ],
        config=cfg,
    )
    assert "HIGHER_TF_STRONG_CONFLICT" in result.blockers
    assert result.direction == "WAIT"


def test_resample_and_split() -> None:
    base = datetime(2025, 1, 6, tzinfo=UTC)
    m15 = [
        Candle(
            symbol="XAUUSD",
            timeframe=Timeframe.M15,
            timestamp=base + timedelta(minutes=15 * i),
            open=2000 + i,
            high=2001 + i,
            low=1999 + i,
            close=2000.5 + i,
            volume=1.0,
            spread=10,
            tick_volume=1.0,
            real_volume=0.0,
        )
        for i in range(96 * 5)  # 5 days contiguous
    ]
    h1 = resample_from_m15(m15, Timeframe.H1, symbol="XAUUSD")
    assert len(h1) >= 20
    gaps, dupes = count_m15_gaps(m15)
    assert dupes == 0
    assert gaps == 0
    split = chronological_split(m15)
    assert len(split.development) + len(split.validation) + len(split.holdout) == len(m15)
    report, frames = validate_dataset(
        m15, path="synthetic.csv", broker_symbol="XAUUSD", min_m15_for_split=100
    )
    assert report.m15_count == len(m15)
    assert frames["H4"]


def test_scenario_suite_runs() -> None:
    rows = run_scenario_suite()
    names = {r.scenario for r in rows}
    assert "sharp_1h_selloff" in names
    assert "sideways" in names
    assert len(rows) >= 10


def test_structure_audit_v2_more_directional_on_conflict() -> None:
    audit = audit_binary_structure_overweight()
    assert audit["v1_structure"] == 100.0
    assert audit["v2_total"] < audit["v1_total"]


def test_selloff_delay_measurable() -> None:
    m15 = build_scenarios()["sharp_1h_selloff"]
    delay = measure_selloff_response_delay(m15)
    data = delay.as_dict() if hasattr(delay, "as_dict") else delay
    assert data["event_bar"] is not None


def test_selloff_4h_event_detected() -> None:
    from exness_bot.market_analysis.research.delay_metrics import detect_selloff_event

    m15 = build_scenarios()["sharp_4h_selloff"]
    assert detect_selloff_event(m15) is not None


def test_legacy_coverage_explains_sampling() -> None:
    from exness_bot.market_analysis.research.coverage import explain_legacy_coverage

    rep = explain_legacy_coverage(35973)
    assert len(range(250, 35973, 48)) == rep.FINAL_EVALUATED
    assert rep.SAMPLING_EXCLUDED > 30_000


def test_freeze_snapshot_immutable() -> None:
    from exness_bot.market_analysis.research.freeze import (
        DEFAULT_V2_CONFIG,
        assert_freeze_matches_16_2_4,
    )

    assert_freeze_matches_16_2_4(DEFAULT_V2_CONFIG)


def test_impulse_1h_vs_4h_documented() -> None:
    from exness_bot.market_analysis.research.delay_metrics import explain_impulse_at_end

    sc = build_scenarios()
    a = explain_impulse_at_end(sc["sharp_1h_selloff"], label="1h")
    b = explain_impulse_at_end(sc["sharp_4h_selloff"], label="4h")
    assert a["impulse_score"] is not None
    assert b["impulse_score"] is not None
    # Both negative after selloff tails; magnitudes differ by path — not a bug.
    assert a["impulse_score"] < 0
    assert b["impulse_score"] < 0
