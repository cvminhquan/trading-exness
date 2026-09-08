"""CLI: candidate-execution-smoke — Fake transport only (Phase 17.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from exness_bot.config.settings import Settings
from exness_bot.data.models import DataSourceMode, ProviderConnectionStatus, ProviderSnapshot
from exness_bot.domain.models import AccountInfo, SymbolInfo, Tick
from exness_bot.execution.integration.factory import build_fake_candidate_execution_service
from exness_bot.execution.integration.service import CandidateExecutionContext
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
    ExecutionCandidate,
    SetupLifecycleState,
)
from exness_bot.market_analysis.setup import TakeProfitLevel
from exness_bot.paper_execution.contract import AckStatus


def run_candidate_execution_smoke(*, symbol: str = "XAUUSD") -> int:
    """
    Force an ENTRY_ZONE eligible candidate through Fake orchestrator.

    NEVER constructs LiveMT5ExecutionTransport / gated MT5 port.
    Does not require broker credentials.
    """
    settings = Settings(_env_file=None)
    now = datetime.now(tz=UTC)
    candle = now - timedelta(minutes=5)
    # ignore_cleanup_errors: Windows may keep sqlite handles briefly after close.
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "setup.db"
        settings = settings.model_copy(
            update={"database_url": f"sqlite:///{db.as_posix()}"}
        )
        service, port, _store = build_fake_candidate_execution_service(
            settings,
            state_dir=Path(tmp) / "paper",
            ack=AckStatus.FILLED,
            fill_price=2341.0,
            clock=lambda: now,
        )
        setup_store = service._setup_store
        setup = _synthetic_setup(symbol=symbol, candle=candle, now=now)
        setup_store.upsert(setup)
        candidate = _synthetic_candidate(setup, now=now)
        quote = _quote(symbol)
        tick = Tick(
            symbol=symbol,
            bid=2340.9,
            ask=2341.1,
            last=2341.0,
            volume=1.0,
            timestamp=now,
        )
        snapshot = ProviderSnapshot(
            connection_status=ProviderConnectionStatus.CONNECTED,
            data_source=DataSourceMode.MOCK,
            account=AccountInfo(
                login=1,
                balance=10_000.0,
                equity=10_000.0,
                margin=0.0,
                free_margin=10_000.0,
                currency="USD",
                leverage=100,
                trade_mode="demo",
                name="smoke",
                server="smoke",
            ),
            positions=(),
            updated_at=now,
        )
        ctx = CandidateExecutionContext(
            tick=tick,
            quote=quote,
            snapshot=snapshot,
            timeframe_status={
                "M15": "LIVE",
                "H1": "LIVE",
                "H4": "LIVE",
                "D1": "LIVE",
            },
            now=now,
        )
        first = service.consume(candidate, ctx)
        second = service.consume(candidate, ctx)

        orch = first.orchestration
        lines = [
            "",
            "==================================================",
            "CANDIDATE EXECUTION SMOKE (Phase 17.1)",
            "==================================================",
            f"STRATEGY: {MTF_STRATEGY_ID}",
            f"SETUP STATE: {setup.state.value}",
            f"CANDIDATE ELIGIBLE: {'YES' if candidate.eligibility.eligible else 'NO'}",
            "",
            "EXECUTION TRANSPORT:",
            "FAKE",
            "",
            "PRECHECK:",
            f"{first.precheck.verdict.value}",
            "",
            "INTENT:",
        ]
        if orch is not None and orch.lifecycle is not None:
            lines.append(f"{orch.lifecycle.value}")
            lines.append(f"OUTCOME: {orch.outcome}")
        else:
            lines.append("N/A")
            lines.extend(first.precheck.reasons)
        lines.extend(
            [
                "",
                "SUBMIT CALL COUNT:",
                f"{len(port.calls)} (first={first.port_submit_count}, "
                f"second={second.port_submit_count})",
                "",
                "BROKER MUTATION:",
                "NO",
                "==================================================",
                "",
            ]
        )
        print("\n".join(lines))
        if not first.precheck.allowed:
            return 2
        if len(port.calls) != 1:
            return 3
        return 0


def _synthetic_setup(*, symbol: str, candle: datetime, now: datetime) -> CanonicalTradeSetup:
    direction = "LONG"
    setup_id = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol=symbol,
        primary_timeframe="M15",
        source_candle_timestamp=candle,
        direction=direction,
    )
    tps = (
        TakeProfitLevel(1, 2355.0, 30.0, 1.5, "TP1"),
        TakeProfitLevel(2, 2370.0, 40.0, 3.0, "TP2"),
        TakeProfitLevel(3, 2390.0, 30.0, 5.0, "TP3"),
    )
    fp = compute_analysis_fingerprint(
        strategy_id=MTF_STRATEGY_ID,
        symbol=symbol,
        primary_timeframe="M15",
        source_candle_timestamp=candle,
        direction=direction,
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        stop_loss=2330.0,
        take_profit_prices=[tp.price for tp in tps],
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )
    return CanonicalTradeSetup(
        setup_id=setup_id,
        strategy_id=MTF_STRATEGY_ID,
        symbol=symbol,
        broker_symbol="XAUUSDm",
        primary_timeframe="M15",
        direction=direction,
        source_candle_timestamp=candle,
        created_at=now,
        expires_at=compute_expires_at(
            source_candle_timestamp=candle, primary_timeframe="M15", max_candles=8
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
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )


def _synthetic_candidate(
    setup: CanonicalTradeSetup, *, now: datetime
) -> ExecutionCandidate:
    elig = EligibilityResult(
        eligible=True,
        reasons=("ALL_CHECKS_PASSED",),
        blocking=(),
        warnings=(),
    )
    # Build via helper with sizing-like fields
    from exness_bot.market_analysis.models import PositionSizingSnapshot

    sizing = PositionSizingSnapshot(
        equity=10_000.0,
        risk_percent=0.5,
        risk_budget_usd=50.0,
        raw_volume=0.01,
        normalized_volume=0.01,
        broker_min_volume=0.01,
        broker_max_volume=100.0,
        broker_volume_step=0.01,
        estimated_risk_usd=10.0,
        estimated_risk_pct=0.1,
        broker_executable=True,
        risk_acceptable=True,
    )
    built = build_execution_candidate(
        setup=setup,
        sizing=sizing,
        eligibility=elig,
        now=now,
    )
    assert built is not None
    return built


def _quote(symbol: str) -> SymbolInfo:
    return SymbolInfo(
        symbol=symbol,
        bid=2340.9,
        ask=2341.1,
        point=0.01,
        digits=2,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        trade_contract_size=100.0,
        spread=20,
        trade_mode=4,
        visible=True,
        stops_level=0,
        freeze_level=0,
        trade_tick_size=0.01,
        trade_tick_value=1.0,
    )
