"""Unit tests for PHASE 16.2.4A.1 drawdown audit helpers."""

from __future__ import annotations

from exness_bot.market_analysis.research.drawdown_audit import (
    AuditTrade,
    build_equity_curve,
    classify_cohort,
    counterfactual_exclude,
    find_max_drawdown_window,
    mark_clusters,
    score_bucket,
)


def _t(
    i: int,
    r: float,
    *,
    direction: str = "SHORT",
    cohort: str = "V1_AND_V2_DIRECTIONAL_SAME_DIRECTION",
    source: str = "v2",
    clustered: bool = False,
) -> AuditTrade:
    return AuditTrade(
        bar_index=i * 10,
        timestamp=f"2025-01-01T{i:02d}:00:00+00:00",
        direction=direction,
        source=source,
        exit_r=r,
        mae_r=1.0,
        mfe_r=1.0,
        bars_held=4,
        exit_reason="SL" if r < 0 else "TP",
        whipsaw=r < 0,
        false_signal=r < 0,
        entry=2000.0,
        atr=2.0,
        v1_direction="WAIT",
        v2_direction=direction,
        v1_score=0.0,
        v2_score=-25.0,
        m15_score=-30.0,
        impulse_score=-40.0,
        structure_transition="WEAKENING_BULLISH",
        cohort=cohort,
        regime="TRENDING_BEARISH",
        utc_hour=12,
        session="Overlap_LN_NY",
        abs_v2_score=25.0,
        bars_until_v1_same=3,
        clustered=clustered,
    )


def test_classify_cohort() -> None:
    assert classify_cohort("WAIT", "SHORT") == "V2_SHORT_WHILE_V1_WAIT"
    assert classify_cohort("WAIT", "LONG") == "V2_LONG_WHILE_V1_WAIT"
    assert classify_cohort("SHORT", "SHORT") == "V1_AND_V2_DIRECTIONAL_SAME_DIRECTION"
    assert classify_cohort("LONG", "SHORT") == "V1_AND_V2_DIRECTIONAL_DIFFERENT_DIRECTION"


def test_equity_and_max_dd() -> None:
    trades = [_t(0, 2.0), _t(1, -1.0), _t(2, -1.0), _t(3, 2.0)]
    curve = build_equity_curve(trades)
    assert curve[-1].cumulative_R == 2.0
    mdd = find_max_drawdown_window(curve)
    assert mdd["depth_R"] == 2.0
    assert mdd["recovered"] is True


def test_counterfactual_exclude_is_labeled() -> None:
    trades = [
        _t(0, -1.0, cohort="V2_LONG_WHILE_V1_WAIT"),
        _t(1, 2.0, cohort="V2_SHORT_WHILE_V1_WAIT"),
        _t(2, -1.0, cohort="V1_AND_V2_DIRECTIONAL_SAME_DIRECTION"),
    ]
    cf = counterfactual_exclude(trades, exclude_cohorts={"V2_LONG_WHILE_V1_WAIT"})
    assert cf["label"] == "POST-HOC DESCRIPTIVE COUNTERFACTUAL"
    assert cf["remaining_trades"] == 2


def test_mark_clusters() -> None:
    trades = [
        _t(0, -1.0),
        _t(1, -1.0),  # bar 10 apart — within 8? 10 > 8 so NOT cluster
    ]
    # bar_index = i*10 → gap 10 > 8
    mark_clusters(trades)
    assert trades[0].clustered is False
    trades2 = [
        _t(0, -1.0),
        AuditTrade(
            **{
                **_t(0, -1.0).__dict__,
                "bar_index": 5,
                "timestamp": "2025-01-01T01:00:00+00:00",
            }
        ),
    ]
    mark_clusters(trades2)
    assert trades2[0].clustered is True
    assert trades2[1].clustered is True


def test_score_bucket() -> None:
    assert score_bucket(25.0) == "20-30"
    assert score_bucket(65.0) == "60+"
