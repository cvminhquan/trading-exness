"""Phase 17.2.1 — PREVIEW diagnostics are display-only (no eligibility mutation)."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from exness_bot.controlled_demo.identity import DemoMarketSnapshot
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.models import Tick
from exness_bot.execution.integration.demo_cli import (
    build_preview_diagnostics_lines,
    format_preview_diagnostics,
)
from exness_bot.market_analysis.contract.candidate import build_execution_candidate
from exness_bot.market_analysis.contract.identity import (
    ANALYSIS_CONTRACT_VERSION,
    MTF_STRATEGY_ID,
    compute_analysis_fingerprint,
    compute_setup_id,
)
from exness_bot.market_analysis.contract.lifecycle import compute_expires_at
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    EligibilityResult,
    SetupLifecycleState,
)
from exness_bot.market_analysis.models import PositionSizingSnapshot
from exness_bot.market_analysis.setup import TakeProfitLevel
from tests.fixtures.risk_data import make_xauusd_symbol

_NOW = datetime(2026, 9, 8, 16, 0, tzinfo=UTC)


def _setup() -> CanonicalTradeSetup:
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
    return CanonicalTradeSetup(
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
        risk_snapshot={"risk_budget_usd": 50.0},
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )


def _candidate(setup: CanonicalTradeSetup, *, eligible: bool = False):
    sizing = PositionSizingSnapshot(
        equity=10_000.0,
        risk_percent=0.5,
        risk_budget_usd=50.0,
        raw_volume=0.01,
        normalized_volume=0.01,
        broker_min_volume=0.01,
        broker_max_volume=100.0,
        broker_volume_step=0.01,
        estimated_risk_usd=12.5,
        estimated_risk_pct=0.125,
        broker_executable=True,
        risk_acceptable=False,
    )
    elig = EligibilityResult(
        eligible=eligible,
        reasons=("SPREAD_TOO_WIDE",) if not eligible else ("ALL_CHECKS_PASSED",),
        blocking=("SPREAD_TOO_WIDE",) if not eligible else (),
        warnings=(),
    )
    built = build_execution_candidate(
        setup=setup, sizing=sizing, eligibility=elig, now=_NOW
    )
    assert built is not None
    return built


def _market() -> DemoMarketSnapshot:
    sym = make_xauusd_symbol(bid=2340.9, ask=2341.4).model_copy(
        update={"trade_tick_size": 0.01, "trade_tick_value": 1.0}
    )
    tick = Tick(
        symbol="XAUUSDm",
        bid=2340.9,
        ask=2341.4,
        last=2341.0,
        volume=1.0,
        timestamp=_NOW,
    )
    return DemoMarketSnapshot(
        symbol=sym,
        tick=tick,
        freshness=QuoteFreshness.LIVE,
        age_seconds=1.0,
        spread_points=50.0,
    )


def test_format_preview_diagnostics_contains_required_labels() -> None:
    lines = format_preview_diagnostics(
        bid=2340.9,
        ask=2341.4,
        current_spread_points=50.0,
        max_spread_points=50,
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        executable_price_value=2341.4,
        proposed_volume=0.01,
        estimated_risk_usd=12.5,
        risk_budget_usd=50.0,
        broker_executable=True,
        risk_acceptable=False,
        setup_state="ENTRY_ZONE",
        block_reasons=("SPREAD_TOO_WIDE",),
    )
    text = "\n".join(lines)
    for label in (
        "BID:",
        "ASK:",
        "RAW_SPREAD_POINTS:",
        "NORMALIZED_SPREAD_POINTS:",
        "CURRENT_SPREAD_POINTS:",
        "MAX_SPREAD_POINTS:",
        "ENTRY_ZONE_LOW:",
        "ENTRY_ZONE_HIGH:",
        "EXECUTABLE_PRICE:",
        "PROPOSED_VOLUME:",
        "ESTIMATED_RISK_USD:",
        "RISK_BUDGET_USD:",
        "BROKER_EXECUTABLE:",
        "RISK_ACCEPTABLE:",
        "SETUP_STATE:",
        "BLOCK_REASONS:",
    ):
        assert label in text
    assert "SPREAD_TOO_WIDE" in text
    assert "MAX_SPREAD_POINTS: 50" in text


def test_diagnostics_do_not_alter_eligibility() -> None:
    setup = _setup()
    candidate = _candidate(setup, eligible=False)
    before = deepcopy(candidate)
    before_elig = (
        candidate.eligibility.eligible,
        candidate.eligibility.blocking,
        candidate.broker_executable,
        candidate.risk_acceptable,
        candidate.proposed_volume,
    )

    lines = build_preview_diagnostics_lines(
        market=_market(),
        setup=setup,
        candidate=candidate,
        setup_state=setup.state.value,
        block_reasons=candidate.eligibility.blocking,
        max_spread_points=50,
        risk_per_trade_pct=0.5,
        equity=10_000.0,
    )
    assert lines  # produced output

    assert candidate == before
    assert (
        candidate.eligibility.eligible,
        candidate.eligibility.blocking,
        candidate.broker_executable,
        candidate.risk_acceptable,
        candidate.proposed_volume,
    ) == before_elig
    assert setup.state is SetupLifecycleState.ENTRY_ZONE


def test_diagnostics_long_executable_price_is_ask() -> None:
    setup = _setup()
    candidate = _candidate(setup)
    lines = build_preview_diagnostics_lines(
        market=_market(),
        setup=setup,
        candidate=candidate,
        setup_state=setup.state.value,
        block_reasons=("SPREAD_TOO_WIDE",),
        max_spread_points=50,
        risk_per_trade_pct=0.5,
        equity=10_000.0,
    )
    joined = "\n".join(lines)
    assert "EXECUTABLE_PRICE: 2341.4" in joined
    assert "BID: 2340.9" in joined
    assert "ASK: 2341.4" in joined
    assert "RISK_BUDGET_USD: 50" in joined


def test_diagnostics_formatting_is_deterministic() -> None:
    a = format_preview_diagnostics(
        bid=1.0,
        ask=2.0,
        current_spread_points=10.0,
        max_spread_points=50,
        entry_zone_low=1.0,
        entry_zone_high=2.0,
        executable_price_value=2.0,
        proposed_volume=0.01,
        estimated_risk_usd=1.0,
        risk_budget_usd=5.0,
        broker_executable=False,
        risk_acceptable=False,
        setup_state="WAITING_FOR_ENTRY",
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    b = format_preview_diagnostics(
        bid=1.0,
        ask=2.0,
        current_spread_points=10.0,
        max_spread_points=50,
        entry_zone_low=1.0,
        entry_zone_high=2.0,
        executable_price_value=2.0,
        proposed_volume=0.01,
        estimated_risk_usd=1.0,
        risk_budget_usd=5.0,
        broker_executable=False,
        risk_acceptable=False,
        setup_state="WAITING_FOR_ENTRY",
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    assert a == b
