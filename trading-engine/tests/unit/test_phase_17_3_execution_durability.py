"""Phase 17.3 — Execution durability hardening (FakeMT5 ONLY — no real order_send)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from exness_bot.broker.mt5.execution_transport import (
    FakeMT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.config.settings import Settings
from exness_bot.data.models import DataSourceMode, ProviderConnectionStatus, ProviderSnapshot
from exness_bot.domain.models import Tick
from exness_bot.execution.auto_demo.decision_store import (
    AutoDemoDecisionState,
    SqliteAutoDemoDecisionStore,
)
from exness_bot.execution.auto_demo.factory import (
    build_auto_demo_candidate_execution_service,
    resolve_auto_demo_state_path,
)
from exness_bot.execution.auto_demo.loop import (
    AutoDemoCandidateBundle,
    AutonomousDemoExecutionLoop,
    ClosedM15Observation,
)
from exness_bot.execution.auto_demo.runtime_snapshot import (
    build_gated_execution_snapshot,
    read_auto_demo_runtime_facts,
)
from exness_bot.execution.integration.factory import require_durable_setup_store
from exness_bot.execution.integration.service import CandidateExecutionContext
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot
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
from exness_bot.paper_execution.contract import IntentLifecycle
from exness_bot.paper_execution.errors import CorruptStateError
from tests.fixtures.risk_data import make_account, make_xauusd_symbol

SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"
_NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
_CLOSED = datetime(2026, 9, 8, 9, 45, tzinfo=UTC)

AUTO_DEMO_CLI = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "exness_bot"
    / "execution"
    / "auto_demo"
    / "cli.py"
)


def _settings(tmp_path: Path, **kwargs: object) -> Settings:
    db = tmp_path / "setup.db"
    base: dict[str, object] = {
        "_env_file": None,
        "DATABASE_URL": f"sqlite:///{db.as_posix()}",
        "EXECUTION_MODE": "paper",
        "TRADING_ENV": "demo",
        "TRADING_MODE": "demo",
        "LIVE_KILL_SWITCH": False,
        "LIVE_DEMO_APPROVAL": True,
        "AUTO_DEMO_EXECUTION_ENABLED": True,
        "ALLOW_LEGACY_RUN": False,
        "ALLOW_LIVE_TRADING": False,
        "DRY_RUN": False,
        "DEMO_ACCOUNT_ALLOWLIST": "12345678",
        "DEMO_SERVER_ALLOWLIST": "Exness-MT5Trial",
        "MT5_DEMO_LOGIN": 12345678,
        "MT5_DEMO_SERVER": "Exness-MT5Trial",
        "LIVE_SYMBOL_MAP": f"{SYMBOL}:{BROKER}",
        "MT5_SYMBOL": BROKER,
        "SYMBOL": SYMBOL,
        "MAX_POSITION_LOTS": 1.0,
        "MAX_SPREAD_POINTS": 50,
        "MAX_OPEN_POSITIONS": 1,
        "MAX_DAILY_LOSS_PCT": 2.0,
        "MAX_DRAWDOWN_PCT": 5.0,
        "LIVE_DATA_STALE_SECONDS": 10,
        "ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS": 10,
        "RISK_PER_TRADE_PCT": 0.5,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _setup() -> CanonicalTradeSetup:
    c = _NOW - timedelta(minutes=5)
    direction = "LONG"
    from exness_bot.market_analysis.setup import TakeProfitLevel

    tps = (
        TakeProfitLevel(1, 2355.0, 30.0, 1.5, "TP1"),
        TakeProfitLevel(2, 2370.0, 40.0, 3.0, "TP2"),
    )
    setup_id = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol=SYMBOL,
        primary_timeframe="M15",
        source_candle_timestamp=c,
        direction=direction,
    )
    fp = compute_analysis_fingerprint(
        strategy_id=MTF_STRATEGY_ID,
        symbol=SYMBOL,
        primary_timeframe="M15",
        source_candle_timestamp=c,
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
        symbol=SYMBOL,
        broker_symbol=BROKER,
        primary_timeframe="M15",
        direction=direction,
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
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )


def _candidate(setup: CanonicalTradeSetup) -> Any:
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
    elig = EligibilityResult(
        eligible=True,
        reasons=("ALL_CHECKS_PASSED",),
        blocking=(),
        warnings=(),
    )
    built = build_execution_candidate(
        setup=setup, sizing=sizing, eligibility=elig, now=_NOW
    )
    assert built is not None
    return built


def _demo_account(*, trade_mode: str = "demo") -> Any:
    base = make_account(equity=10_000.0, trade_mode=trade_mode)
    from exness_bot.domain.models import AccountInfo

    return AccountInfo(
        login=12345678,
        balance=base.balance,
        equity=base.equity,
        margin=base.margin,
        free_margin=base.free_margin,
        currency="USD",
        leverage=500,
        server="Exness-MT5Trial",
        trade_mode=trade_mode,
    )


def _context(account: Any | None = None) -> CandidateExecutionContext:
    acct = account or _demo_account()
    sym = make_xauusd_symbol(
        bid=2340.9, ask=2341.1, spread=20, stops_level=10, freeze_level=0
    ).model_copy(update={"trade_tick_size": 0.01, "trade_tick_value": 1.0})
    tick = Tick(
        symbol=SYMBOL,
        bid=2340.9,
        ask=2341.1,
        last=2341.1,
        volume=1.0,
        timestamp=_NOW - timedelta(seconds=1),
    )
    snapshot = ProviderSnapshot(
        connection_status=ProviderConnectionStatus.CONNECTED,
        data_source=DataSourceMode.MT5,
        account=acct,
        positions=(),
        updated_at=_NOW,
        broker_server="Exness-MT5Trial",
    )
    return CandidateExecutionContext(
        tick=tick,
        quote=sym,
        snapshot=snapshot,
        timeframe_status={"M15": "LIVE", "H1": "LIVE", "H4": "LIVE", "D1": "LIVE"},
        now=_NOW,
    )


def _filled_transport() -> FakeMT5ExecutionTransport:
    return FakeMT5ExecutionTransport(
        default=MT5TransportResult(
            outcome=TransportOutcome.FILLED,
            price=2341.1,
            volume=0.01,
            retcode=10009,
            order_id="1",
            deal_id="2",
        )
    )


def _harness(
    tmp_path: Path,
    *,
    transport: FakeMT5ExecutionTransport | None = None,
    state_path: Path | None = None,
    decision_store: SqliteAutoDemoDecisionStore | None = None,
    settings: Settings | None = None,
    trade_mode: str = "demo",
) -> dict[str, Any]:
    cfg = settings or _settings(tmp_path)
    setup = _setup()
    candidate = _candidate(setup)
    transport = transport or _filled_transport()
    path = state_path or (tmp_path / "auto_demo_intent.json")
    setup_store = require_durable_setup_store(cfg)
    setup_store.upsert(setup)
    store = decision_store or SqliteAutoDemoDecisionStore(tmp_path / "decisions.db")
    observation = ClosedM15Observation(symbol=SYMBOL, timeframe="M15", closed_at=_CLOSED)

    def snapshot_provider() -> GatedExecutionSnapshot:
        return GatedExecutionSnapshot(
            account_trade_mode=trade_mode,
            trade_allowed=True,
            terminal_trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
        )

    service, _gated, intent_store = build_auto_demo_candidate_execution_service(
        cfg,
        transport=transport,
        snapshot_provider=snapshot_provider,
        setup_store=setup_store,
        state_path=path,
        clock=lambda: _NOW,
        settings_provider=lambda: cfg,
    )

    def build_bundle(_obs: ClosedM15Observation) -> AutoDemoCandidateBundle:
        return AutoDemoCandidateBundle(
            candidate=candidate,
            context=_context(),
            blocked_reasons=(),
            signal="LONG",
        )

    loop = AutonomousDemoExecutionLoop(
        settings=cfg,
        decision_store=store,
        observe_closed_m15=lambda: observation,
        build_bundle=build_bundle,
        service=service,
        account_provider=lambda: _demo_account(),
        positions_provider=lambda: [],
        settings_provider=lambda: cfg,
    )
    return {
        "loop": loop,
        "transport": transport,
        "intent_store": intent_store,
        "decision_store": store,
        "state_path": path,
        "settings": cfg,
        "setup": setup,
        "candidate": candidate,
        "service": service,
    }


# ---------------------------------------------------------------------------
# A–E: durable intent restart lifecycle
# ---------------------------------------------------------------------------


def test_a_intent_survives_restart_filled(tmp_path: Path) -> None:
    state = tmp_path / "intent.json"
    transport = _filled_transport()
    h1 = _harness(tmp_path, transport=transport, state_path=state)
    r1 = h1["loop"].run_once()
    assert r1 is not None
    assert r1.state == AutoDemoDecisionState.ACCEPTED.value
    assert len(transport.calls) == 1
    filled = [
        i
        for i in h1["intent_store"]._executor.snapshot.intents
        if i.lifecycle == IntentLifecycle.FILLED
    ]
    assert len(filled) == 1
    intent_id = filled[0].intent_id

    h2 = _harness(
        tmp_path,
        transport=transport,
        state_path=state,
        decision_store=h1["decision_store"],
        settings=h1["settings"],
    )
    reloaded = h2["intent_store"].get(intent_id)
    assert reloaded is not None
    assert reloaded.lifecycle == IntentLifecycle.FILLED
    assert len(transport.calls) == 1


def test_b_in_flight_survives_restart_no_resubmit(tmp_path: Path) -> None:
    """Crash after durable IN_FLIGHT (before finalize) must not wipe or resubmit."""
    from exness_bot.domain.enums import SignalDirection
    from exness_bot.execution.auto_demo.decision_store import (
        AutoDemoDecisionRecord,
        build_decision_id,
    )
    from exness_bot.paper_execution.contract import ExecutionIntent

    state = tmp_path / "intent.json"
    transport = _filled_transport()
    h1 = _harness(tmp_path, transport=transport, state_path=state)

    intent = ExecutionIntent(
        intent_id="crash-inflight-1",
        idempotency_key="crash-inflight-key",
        symbol=SYMBOL,
        timeframe="M15",
        strategy=MTF_STRATEGY_ID,
        side=SignalDirection.LONG,
        requested_quantity=0.01,
        stop_loss=2330.0,
        take_profit=2355.0,
        created_at=_NOW,
        source="test",
    )
    created = h1["intent_store"].create_intent(intent, now=_NOW)
    assert created.created
    h1["intent_store"].mark_in_flight(intent.intent_id, now=_NOW)
    assert len(h1["intent_store"].list_in_flight()) == 1
    assert state.is_file()

    decision_id = build_decision_id(
        symbol=SYMBOL,
        timeframe="M15",
        closed_m15_timestamp=_CLOSED,
        strategy_id=MTF_STRATEGY_ID,
    )
    h1["decision_store"].upsert(
        AutoDemoDecisionRecord(
            decision_id=decision_id,
            symbol=SYMBOL,
            timeframe="M15",
            closed_m15_timestamp=_CLOSED.isoformat(),
            strategy_id=MTF_STRATEGY_ID,
            state=AutoDemoDecisionState.IN_FLIGHT.value,
            created_at=_NOW.isoformat(),
            updated_at=_NOW.isoformat(),
        )
    )

    transport2 = _filled_transport()
    h2 = _harness(
        tmp_path,
        transport=transport2,
        state_path=state,
        decision_store=h1["decision_store"],
        settings=h1["settings"],
    )
    assert len(h2["intent_store"].list_in_flight()) == 1
    reloaded = h2["intent_store"].get("crash-inflight-1")
    assert reloaded is not None
    assert reloaded.lifecycle == IntentLifecycle.IN_FLIGHT

    r2 = h2["loop"].run_once()
    assert len(transport2.calls) == 0
    assert r2 is not None
    # Decision store skip — never auto-resubmit IN_FLIGHT
    assert r2.state == AutoDemoDecisionState.IN_FLIGHT.value
    assert len(h2["intent_store"].list_in_flight()) == 1


def test_c_d_unknown_survives_restart_zero_broker_requests(tmp_path: Path) -> None:
    state = tmp_path / "intent.json"
    transport = FakeMT5ExecutionTransport(
        default=MT5TransportResult(
            outcome=TransportOutcome.TIMEOUT,
            comment="timeout_ambiguous",
        )
    )
    h1 = _harness(tmp_path, transport=transport, state_path=state)
    r1 = h1["loop"].run_once()
    assert r1 is not None
    assert r1.state == AutoDemoDecisionState.UNKNOWN.value
    assert len(transport.calls) == 1
    assert len(h1["intent_store"].list_unknown()) == 1

    transport2 = _filled_transport()
    h2 = _harness(
        tmp_path,
        transport=transport2,
        state_path=state,
        decision_store=h1["decision_store"],
        settings=h1["settings"],
    )
    assert len(h2["intent_store"].list_unknown()) == 1
    r2 = h2["loop"].run_once()
    assert len(transport2.calls) == 0
    assert r2 is not None
    assert r2.state == AutoDemoDecisionState.UNKNOWN.value


def test_e_duplicate_decision_zero_additional_broker_requests(tmp_path: Path) -> None:
    state = tmp_path / "intent.json"
    transport = _filled_transport()
    h = _harness(tmp_path, transport=transport, state_path=state)
    h["loop"].run_once()
    h["loop"].run_once()
    assert len(transport.calls) == 1


# ---------------------------------------------------------------------------
# F: corrupt persistence fail-closed
# ---------------------------------------------------------------------------


def test_f_corrupt_persistence_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "intent.json"
    state.write_text("{not-json", encoding="utf-8")
    cfg = _settings(tmp_path)
    transport = _filled_transport()

    def snapshot_provider() -> GatedExecutionSnapshot:
        return GatedExecutionSnapshot(
            account_trade_mode="demo",
            trade_allowed=True,
            terminal_trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
        )

    with pytest.raises(CorruptStateError):
        build_auto_demo_candidate_execution_service(
            cfg,
            transport=transport,
            snapshot_provider=snapshot_provider,
            setup_store=require_durable_setup_store(cfg),
            state_path=state,
            clock=lambda: _NOW,
            settings_provider=lambda: cfg,
        )
    assert len(transport.calls) == 0


def test_f_empty_persistence_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "intent.json"
    state.write_text("   \n", encoding="utf-8")
    cfg = _settings(tmp_path)

    def snapshot_provider() -> GatedExecutionSnapshot:
        return GatedExecutionSnapshot(
            account_trade_mode="demo",
            trade_allowed=True,
            quote_fresh=True,
            quote_age_seconds=0.0,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
        )

    with pytest.raises(CorruptStateError):
        build_auto_demo_candidate_execution_service(
            cfg,
            transport=_filled_transport(),
            snapshot_provider=snapshot_provider,
            setup_store=require_durable_setup_store(cfg),
            state_path=state,
            settings_provider=lambda: cfg,
        )


# ---------------------------------------------------------------------------
# G–H: kill switch + DEMO identity (regression)
# ---------------------------------------------------------------------------


def test_g_kill_switch_hot_read_blocks_before_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _settings(tmp_path, LIVE_KILL_SWITCH=False)
    transport = _filled_transport()
    # Simulate operator flipping kill switch via process env during loop.
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    from exness_bot.execution.auto_demo.hot_read import hot_read_safety_settings

    h = _harness(tmp_path, transport=transport, settings=cfg)
    # Replace settings_provider to hot-read
    h["loop"].settings_provider = lambda: hot_read_safety_settings(cfg)
    record = h["loop"].run_once()
    assert len(transport.calls) == 0
    assert record is not None
    assert record.state == AutoDemoDecisionState.BLOCKED.value


def test_h_demo_identity_and_allowlist_required(tmp_path: Path) -> None:
    transport = _filled_transport()
    h_bad_list = _harness(
        tmp_path,
        transport=transport,
        settings=_settings(tmp_path, DEMO_ACCOUNT_ALLOWLIST="999"),
    )
    h_bad_list["loop"].run_once()
    assert len(transport.calls) == 0

    transport2 = _filled_transport()
    h_live = _harness(tmp_path / "b", transport=transport2, trade_mode="live")
    h_live["loop"].run_once()
    assert len(transport2.calls) == 0


# ---------------------------------------------------------------------------
# Runtime snapshot fail-closed (no hardcoded True / invented DEMO)
# ---------------------------------------------------------------------------


def test_runtime_snapshot_never_invents_demo_when_account_missing() -> None:
    class _Provider:
        def get_snapshot(self) -> ProviderSnapshot:
            return ProviderSnapshot(
                connection_status=ProviderConnectionStatus.DISCONNECTED,
                data_source=DataSourceMode.MT5,
                account=None,
                positions=(),
                updated_at=_NOW,
            )

        def get_tick(self, symbol: str | None = None) -> Tick | None:
            del symbol
            return None

    cfg = _settings(Path("."))
    facts = read_auto_demo_runtime_facts(_Provider(), cfg, now=_NOW)
    assert facts.account_trade_mode == ""
    assert facts.trade_allowed is None
    assert facts.quote_fresh is None
    snap = build_gated_execution_snapshot(facts)
    assert snap.account_trade_mode == ""
    assert snap.trade_allowed is None
    assert snap.quote_fresh is None


def test_cli_has_no_hardcoded_trade_allowed_true() -> None:
    text = AUTO_DEMO_CLI.read_text(encoding="utf-8")
    assert "trade_allowed=True" not in text
    assert "quote_fresh=True" not in text
    assert 'or "demo"' not in text
    assert "make_auto_demo_snapshot_provider" in text
    assert "resolve_auto_demo_state_path" in text


def test_resolve_auto_demo_state_path_default_is_durable() -> None:
    path = resolve_auto_demo_state_path()
    assert path.name == ".auto_demo_execution_state.json"
    assert path.is_absolute()


def test_execution_mode_not_an_enablement_gate(tmp_path: Path) -> None:
    """EXECUTION_MODE=live must not alone block/allow auto_demo (intentional)."""
    from exness_bot.controlled_demo.enablement import DemoPreflightContext
    from exness_bot.execution.auto_demo.enablement import evaluate_auto_demo_enablement

    cfg = _settings(tmp_path, EXECUTION_MODE="live")
    result = evaluate_auto_demo_enablement(
        DemoPreflightContext(
            settings=cfg,
            symbol_info=make_xauusd_symbol(
                bid=2340.9, ask=2341.1, spread=20, stops_level=10, freeze_level=0
            ).model_copy(update={"trade_tick_size": 0.01, "trade_tick_value": 1.0}),
            intents=(),
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            account_trade_mode="demo",
            trade_allowed=True,
            terminal_trade_allowed=True,
            quote_fresh=True,
            quote_age_seconds=1.0,
        )
    )
    assert result.allowed is True
    assert not any("EXECUTION_MODE" in r for r in result.blocking_reasons)
