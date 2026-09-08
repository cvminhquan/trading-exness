"""Deterministic synthetic scenarios for v1 vs v2 comparison."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.research.analyze import evaluate_mtf_window
from exness_bot.market_analysis.research.freeze import DEFAULT_V2_CONFIG
from exness_bot.market_analysis.research.scoring_v2 import (
    audit_trend_structure_conflict_case,
    compute_timeframe_score_v2,
)
from exness_bot.market_analysis.scoring import compute_timeframe_score
from exness_bot.market_analysis.structure import StructureLabel, StructureSnapshot
from exness_bot.market_analysis.trend import TrendLabel


@dataclass(frozen=True)
class ScenarioRow:
    scenario: str
    v1_score: float | None
    v1_decision: str
    v2_score: float | None
    v2_decision: str
    m15_impulse: float | None
    htf_context: str


def _m15_candle(i: int, price: float, *, base: datetime, vol: float = 1000.0) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=base + timedelta(minutes=15 * i),
        open=price - 0.2,
        high=price + 1.0,
        low=price - 1.0,
        close=price,
        volume=vol,
        spread=20,
        tick_volume=vol,
        real_volume=0.0,
    )


def _series_from_returns(
    returns: list[float],
    *,
    start: float = 2400.0,
    base: datetime | None = None,
) -> list[Candle]:
    t0 = base or datetime(2025, 1, 6, 0, 0, tzinfo=UTC)  # Monday
    price = start
    out: list[Candle] = []
    for i, r in enumerate(returns):
        price = price + r
        out.append(_m15_candle(i, price, base=t0))
    return out


def _pad_trend(n: int, step: float) -> list[float]:
    return [step] * n


def build_scenarios() -> dict[str, list[Candle]]:
    """Named M15 closed series (≥80 bars) for deterministic tests."""
    _pad_trend(80, 0.15)
    scenarios: dict[str, list[Candle]] = {}

    scenarios["sideways"] = _series_from_returns(
        _pad_trend(40, 0.05) + [0.1, -0.1, 0.05, -0.05] * 20
    )
    scenarios["normal_bullish"] = _series_from_returns(_pad_trend(120, 0.6))
    scenarios["normal_bearish"] = _series_from_returns(_pad_trend(120, -0.6))

    # Sharp ~1h selloff = 4 M15 bars of large drops after mild uptrend
    scenarios["sharp_1h_selloff"] = _series_from_returns(
        [*_pad_trend(100, 0.3), -8.0, -7.0, -6.5, -6.0, *_pad_trend(8, -0.4)]
    )
    # Sharp ~4h selloff = 16 M15 bars
    scenarios["sharp_4h_selloff"] = _series_from_returns(
        _pad_trend(100, 0.3) + [-3.5] * 16 + _pad_trend(8, -0.3)
    )
    scenarios["bullish_pullback_in_bearish"] = _series_from_returns(
        [*_pad_trend(90, -0.7), 2.0, 1.8, 1.5, 1.2, 0.5, *_pad_trend(10, -0.5)]
    )
    scenarios["false_breakout"] = _series_from_returns(
        [*_pad_trend(90, 0.4), 5.0, 4.0, -6.0, -5.0, -2.0, *_pad_trend(10, 0.2)]
    )
    scenarios["v_reversal"] = _series_from_returns(
        [*_pad_trend(70, -0.8), -5.0, -4.0, 4.0, 5.0, 4.5, *_pad_trend(20, 0.6)]
    )
    # Same series used; HTF context comes from resample — tag by name
    scenarios["m15_bearish_vs_h4_bullish"] = _series_from_returns(
        _pad_trend(200, 0.5) + [-4.0] * 12
    )
    scenarios["m15_bullish_vs_d1_bearish"] = _series_from_returns(
        _pad_trend(400, -0.35) + [3.0] * 20
    )
    return scenarios


def run_scenario_suite() -> list[ScenarioRow]:
    rows: list[ScenarioRow] = []
    for name, m15 in build_scenarios().items():
        v1, v2, _atr = evaluate_mtf_window(m15, config=DEFAULT_V2_CONFIG, min_bars=60)
        ctx = ",".join(v2.context_warnings) if v2.context_warnings else "—"
        rows.append(
            ScenarioRow(
                scenario=name,
                v1_score=v1.weighted_score,
                v1_decision=v1.direction,
                v2_score=v2.weighted_score,
                v2_decision=v2.direction,
                m15_impulse=v2.m15_impulse,
                htf_context=ctx,
            )
        )
    return rows


# Back-compat: tests may expect a mapping
def measure_selloff_response_delay(m15: list[Candle], **kwargs: object) -> object:
    from exness_bot.market_analysis.research.delay_metrics import (
        measure_selloff_response_delay as _measure,
    )

    return _measure(m15, **kwargs)  # type: ignore[arg-type]


def audit_binary_structure_overweight() -> dict[str, object]:
    """Case: TREND=-100, STRUCTURE=+100 — v1 near-neutral partial vs v2 dampened."""
    v1 = compute_timeframe_score(
        trend=TrendLabel.DOWNTREND,
        structure=StructureLabel.BULLISH,
        rsi=35.0,
        macd_momentum="BEARISH",
        close=2400.0,
        support=2390.0,
        resistance=2420.0,
        atr=5.0,
        volume_state="HIGH",
    )
    snap = StructureSnapshot(
        classification=StructureLabel.BULLISH,
        sequence=["HH", "HL", "HH", "HL"],
        labeled=[],
        latest_swing_high=2410.0,
        latest_swing_low=2395.0,
    )
    # Weakening: close breaks swing low while label still bullish book
    snap_break = StructureSnapshot(
        classification=StructureLabel.BULLISH,
        sequence=["HH", "HL", "LH", "LL"],
        labeled=[],
        latest_swing_high=2410.0,
        latest_swing_low=2395.0,
    )
    closes = [2410 - i * 2.0 for i in range(10)] + [2380.0]
    v2 = compute_timeframe_score_v2(
        trend=TrendLabel.DOWNTREND,
        structure_snapshot=snap_break,
        rsi=35.0,
        macd_momentum="BEARISH",
        close=2380.0,
        support=2370.0,
        resistance=2410.0,
        atr=5.0,
        volume_state="HIGH",
        closes=closes,
        apply_impulse=True,
    )
    partial = audit_trend_structure_conflict_case()
    return {
        "v1_total": v1.total_score,
        "v1_direction": v1.direction,
        "v1_trend": v1.trend_score,
        "v1_structure": v1.structure_score,
        "v2_total": v2.total_score,
        "v2_direction": v2.direction,
        "v2_structure": v2.structure_score,
        "v2_transition": v2.structure_transition.value,
        "v2_impulse": v2.impulse_score,
        "v2_conflict_dampened": v2.conflict_dampened,
        "partial_audit": partial,
        "binary_snapshot_score_v1_style": compute_timeframe_score(
            trend=TrendLabel.DOWNTREND,
            structure=snap.classification,
            rsi=35.0,
            macd_momentum="BEARISH",
            close=2380.0,
            support=2370.0,
            resistance=2410.0,
            atr=5.0,
            volume_state="HIGH",
        ).total_score,
    }
