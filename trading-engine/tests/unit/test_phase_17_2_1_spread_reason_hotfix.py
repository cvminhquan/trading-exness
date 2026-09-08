"""Phase 17.2.1 hotfix — spread boundary + NO_SETUP reason precedence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from exness_bot.domain.models import Tick
from exness_bot.execution.integration.demo_cli import format_preview_diagnostics
from exness_bot.market_analysis.contract.eligibility import evaluate_eligibility
from exness_bot.market_analysis.contract.identity import (
    ANALYSIS_CONTRACT_VERSION,
    MTF_STRATEGY_ID,
    compute_analysis_fingerprint,
    compute_setup_id,
)
from exness_bot.market_analysis.contract.lifecycle import compute_expires_at
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.spread import (
    compute_raw_spread_points,
    normalize_spread_points,
    spread_exceeds_max,
)
from exness_bot.market_analysis.mtf_service import MultiTimeframeAnalysis
from exness_bot.market_analysis.patterns import PatternSnapshot
from exness_bot.market_analysis.setup import TakeProfitLevel
from exness_bot.market_analysis.structure import StructureLabel
from exness_bot.market_analysis.timeframe_analyzer import TimeframeAnalysis
from exness_bot.market_analysis.trend import TrendLabel
from exness_bot.market_analysis.volume import VolumeSnapshot
from tests.fixtures.risk_data import make_xauusd_symbol

_NOW = datetime(2026, 9, 8, 16, 0, tzinfo=UTC)


def _tf(name: str) -> TimeframeAnalysis:
    return TimeframeAnalysis(
        timeframe=name,
        candle_timestamp=_NOW,
        close=2341.0,
        trend=TrendLabel.UPTREND,
        signal="NEUTRAL",
        confidence=70.0,
        score=None,
        ema20=2340.0,
        ema50=2330.0,
        ema200=2300.0,
        rsi14=55.0,
        atr14=5.0,
        macd=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        macd_momentum="BULLISH",
        structure_classification=StructureLabel.BULLISH,
        sequence=["HH", "HL"],
        latest_swing_high=2360.0,
        latest_swing_low=2320.0,
        nearest_support=2338.0,
        nearest_resistance=2355.0,
        supports=[2338.0],
        resistances=[2355.0],
        volume=VolumeSnapshot("TICK_VOLUME", 1000, 800, 1.25, "NORMAL"),
        pattern=PatternSnapshot("NONE", 0.0, []),
        status="LIVE",
    )


def _analysis(*, final: str = "LONG") -> MultiTimeframeAnalysis:
    return MultiTimeframeAnalysis(
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        current_price=2341.0,
        timeframes={name: _tf(name) for name in ("M15", "H1", "H4", "D1")},
        final_signal=final,
        confidence_score=75.0,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        trend="UPTREND",
        structure_summary="HH → HL",
        key_supports=[2338.0],
        key_resistances=[2355.0],
        setup=None,
        sizing=None,
        execution_assessment="BLOCKED",
        reasons=[],
        warnings=[],
        generated_at=_NOW,
        freshness="LIVE",
    )


def _tick(*, bid: float, ask: float) -> Tick:
    return Tick(
        symbol="XAUUSD",
        bid=bid,
        ask=ask,
        last=(bid + ask) / 2.0,
        volume=1.0,
        timestamp=_NOW,
    )


@pytest.mark.parametrize(
    ("spread_pts", "should_block"),
    [
        (259.0, False),
        (260.0, False),
        (261.0, True),
    ],
)
def test_spread_boundary_points(spread_pts: float, should_block: bool) -> None:
    """spread <= max allowed; spread > max blocked. MAX stays 260."""
    max_pts = 260
    point = 0.01
    bid = 2340.0
    ask = bid + spread_pts * point
    raw = compute_raw_spread_points(bid=bid, ask=ask, point=point)
    normalized = normalize_spread_points(raw)
    print(
        f"boundary spread_pts={spread_pts} "
        f"raw={raw!r} normalized={normalized!r} max={max_pts}"
    )
    assert spread_exceeds_max(raw, max_pts) is should_block

    symbol = make_xauusd_symbol(bid=bid, ask=ask).model_copy(
        update={"point": point, "spread": int(spread_pts)}
    )
    result = evaluate_eligibility(
        strategy_id=MTF_STRATEGY_ID,
        analysis=_analysis(final="LONG"),
        setup=None,
        tick=_tick(bid=bid, ask=ask),
        symbol_info=symbol,
        account_available=True,
        account_fresh=True,
        quote_fresh=True,
        max_spread_points=max_pts,
        broker_executable=True,
        risk_acceptable=True,
        now=_NOW,
        account_updated_at=_NOW,
    )
    if should_block:
        assert "SPREAD_TOO_WIDE" in result.blocking
    else:
        assert "SPREAD_TOO_WIDE" not in result.blocking


def test_float_noise_at_equality_does_not_block() -> None:
    """Display may show 260 while raw float is slightly above — still allow."""
    max_pts = 260
    raw = 260.0 + 1e-10
    normalized = normalize_spread_points(raw)
    print(f"float_noise raw={raw!r} normalized={normalized!r} max={max_pts}")
    assert normalized == 260.0
    assert spread_exceeds_max(raw, max_pts) is False

    point = 0.01
    bid = 2340.0
    ask = bid + 260 * point
    raw2 = compute_raw_spread_points(bid=bid, ask=ask, point=point)
    print(
        f"ask_bid_rebuild raw={raw2!r} normalized={normalize_spread_points(raw2)!r} "
        f"max={max_pts}"
    )
    assert spread_exceeds_max(raw2, max_pts) is False


def test_just_above_max_still_blocks_after_normalize() -> None:
    max_pts = 260
    raw = 260.0 + 1e-3
    print(
        f"above_max raw={raw!r} normalized={normalize_spread_points(raw)!r} max={max_pts}"
    )
    assert spread_exceeds_max(raw, max_pts) is True


def test_no_setup_omits_volume_and_risk_reasons() -> None:
    """WAIT / no geometry must not emit VOLUME_INVALID or RISK_NOT_ACCEPTABLE."""
    max_pts = 260
    point = 0.01
    bid = 2340.0
    ask = bid + 260 * point
    symbol = make_xauusd_symbol(bid=bid, ask=ask).model_copy(update={"point": point})

    result = evaluate_eligibility(
        strategy_id=MTF_STRATEGY_ID,
        analysis=_analysis(final="WAIT"),
        setup=None,
        tick=_tick(bid=bid, ask=ask),
        symbol_info=symbol,
        account_available=True,
        account_fresh=True,
        quote_fresh=True,
        max_spread_points=max_pts,
        broker_executable=False,
        risk_acceptable=False,
        now=_NOW,
        account_updated_at=_NOW,
    )
    assert "FINAL_SIGNAL_WAIT" in result.blocking
    assert "NO_DIRECTIONAL_SETUP" in result.blocking
    assert "VOLUME_INVALID" not in result.blocking
    assert "RISK_NOT_ACCEPTABLE" not in result.blocking
    assert "SPREAD_TOO_WIDE" not in result.blocking

    lines = format_preview_diagnostics(
        bid=bid,
        ask=ask,
        raw_spread_points=260.0,
        normalized_spread_points=260.0,
        current_spread_points=260.0,
        max_spread_points=max_pts,
        entry_zone_low=None,
        entry_zone_high=None,
        executable_price_value=None,
        proposed_volume=None,
        estimated_risk_usd=None,
        risk_budget_usd=None,
        broker_executable=None,
        risk_acceptable=None,
        setup_state="NO_SETUP",
        block_reasons=result.blocking,
    )
    text = "\n".join(lines)
    assert "SETUP_STATE: NO_SETUP" in text
    assert "ENTRY_ZONE_LOW: N/A" in text
    assert "PROPOSED_VOLUME: N/A" in text
    assert "FINAL_SIGNAL_WAIT" in text
    assert "NO_DIRECTIONAL_SETUP" in text
    assert "VOLUME_INVALID" not in text
    assert "RISK_NOT_ACCEPTABLE" not in text


def test_directional_setup_still_emits_volume_risk_when_invalid() -> None:
    """Once trade geometry exists, volume/risk reasons remain valid."""
    c = _NOW - timedelta(minutes=5)
    tps = (TakeProfitLevel(1, 2355.0, 30.0, 1.5, "TP1"),)
    setup_id = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=c,
        direction="LONG",
    )
    fp = compute_analysis_fingerprint(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=c,
        direction="LONG",
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        stop_loss=2330.0,
        take_profit_prices=[2355.0],
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )
    setup = CanonicalTradeSetup(
        setup_id=setup_id,
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        primary_timeframe="M15",
        direction="LONG",
        source_candle_timestamp=c,
        created_at=_NOW,
        expires_at=compute_expires_at(
            source_candle_timestamp=c, primary_timeframe="M15", max_candles=8
        ),
        entry_type="PULLBACK",
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        entry_price=2340.0,
        stop_loss=2330.0,
        take_profits=tps,
        confidence_score=80.0,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        analysis_fingerprint=fp,
        state=SetupLifecycleState.ENTRY_ZONE,
        risk_snapshot={},
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )
    point = 0.01
    bid = 2340.0
    ask = bid + 50 * point
    symbol = make_xauusd_symbol(bid=bid, ask=ask).model_copy(update={"point": point})
    result = evaluate_eligibility(
        strategy_id=MTF_STRATEGY_ID,
        analysis=_analysis(final="LONG"),
        setup=setup,
        tick=_tick(bid=bid, ask=ask),
        symbol_info=symbol,
        account_available=True,
        account_fresh=True,
        quote_fresh=True,
        max_spread_points=260,
        broker_executable=False,
        risk_acceptable=False,
        now=_NOW,
        account_updated_at=_NOW,
    )
    assert "VOLUME_INVALID" in result.blocking
    assert "RISK_NOT_ACCEPTABLE" in result.blocking
