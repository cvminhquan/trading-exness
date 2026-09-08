"""Phase 17.1 — ExecutionCandidate → ExecutionOrchestrator (Fake only)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from exness_bot.backtest.config import BacktestConfig
from exness_bot.config.settings import Settings
from exness_bot.data.models import DataSourceMode, ProviderConnectionStatus, ProviderSnapshot
from exness_bot.domain.enums import SignalDirection
from exness_bot.execution.guard import default_orchestration_guards
from exness_bot.execution.integration.adapter import (
    build_candidate_idempotency_key,
    map_candidate_to_execution_plan,
)
from exness_bot.execution.integration.factory import (
    DurableSetupStoreUnavailableError,
    build_fake_candidate_execution_service,
    require_durable_setup_store,
)
from exness_bot.execution.integration.service import (
    CandidateExecutionContext,
    CandidateExecutionService,
)
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.result import OrchestrationOutcome
from exness_bot.execution.spy import SpyExecutionPort
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
from exness_bot.market_analysis.contract.store import (
    InMemorySetupLifecycleStore,
    SqliteSetupLifecycleStore,
)
from exness_bot.market_analysis.models import PositionSizingSnapshot
from exness_bot.market_analysis.setup import TakeProfitLevel
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionIntent,
    IntentLifecycle,
    IntentRecord,
)
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import (
    CreateIntentResult,
    SnapshotIntentStore,
)
from exness_bot.paper_execution.models import PaperSnapshot
from tests.fixtures.risk_data import make_account, make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
INTEGRATION = SRC / "execution" / "integration"

_NOW = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)


def _candle() -> datetime:
    return _NOW - timedelta(minutes=5)


def _settings(tmp_path: Path) -> Settings:
    db = tmp_path / "setup.db"
    return Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{db.as_posix()}",
        LIVE_DATA_STALE_SECONDS=10,
        ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS=10,
        MAX_SPREAD_POINTS=50,
        RISK_PER_TRADE_PCT=0.5,
    )


def _setup(
    *,
    state: SetupLifecycleState = SetupLifecycleState.ENTRY_ZONE,
    fingerprint: str | None = None,
    candle: datetime | None = None,
) -> CanonicalTradeSetup:
    c = candle or _candle()
    direction = "LONG"
    tps = (
        TakeProfitLevel(1, 2355.0, 30.0, 1.5, "TP1"),
        TakeProfitLevel(2, 2370.0, 40.0, 3.0, "TP2"),
    )
    setup_id = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=c,
        direction=direction,
    )
    fp = fingerprint or compute_analysis_fingerprint(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=c,
        direction=direction,
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        stop_loss=2330.0,
        take_profit_prices=[tp.price for tp in tps],
    )
    return CanonicalTradeSetup(
        setup_id=setup_id,
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
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
        state=state,
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )


def _candidate(
    setup: CanonicalTradeSetup,
    *,
    eligible: bool = True,
    risk_ok: bool = True,
    broker_ok: bool = True,
    volume: float | None = 0.01,
) -> Any:
    sizing = PositionSizingSnapshot(
        equity=10_000.0,
        risk_percent=0.5,
        risk_budget_usd=50.0,
        raw_volume=0.01,
        normalized_volume=volume,
        broker_min_volume=0.01,
        broker_max_volume=100.0,
        broker_volume_step=0.01,
        estimated_risk_usd=10.0,
        estimated_risk_pct=0.1,
        broker_executable=broker_ok,
        risk_acceptable=risk_ok,
    )
    elig = EligibilityResult(
        eligible=eligible,
        reasons=("ALL_CHECKS_PASSED",) if eligible else ("BLOCKED",),
        blocking=() if eligible else ("CANDIDATE_NOT_ELIGIBLE",),
        warnings=(),
    )
    built = build_execution_candidate(
        setup=setup, sizing=sizing, eligibility=elig, now=_NOW
    )
    assert built is not None
    return built


def _complete_symbol(*, tick_spread: float = 0.2) -> Any:
    return make_xauusd_symbol(
        bid=2340.9,
        ask=2340.9 + tick_spread,
    ).model_copy(update={"trade_tick_size": 0.01, "trade_tick_value": 1.0})


def _ctx(
    *,
    quote_age: float = 0.0,
    tf: dict[str, str] | None = None,
    snapshot: ProviderSnapshot | object | None = ...,
    quote: Any = ...,
    tick_spread: float = 0.2,
) -> CandidateExecutionContext:
    now = _NOW
    symbol = _complete_symbol(tick_spread=tick_spread)
    tick = None
    if quote is not False:
        from exness_bot.domain.models import Tick

        tick = Tick(
            symbol="XAUUSD",
            bid=2340.9,
            ask=2340.9 + tick_spread,
            last=2341.0,
            volume=1.0,
            timestamp=now - timedelta(seconds=quote_age),
        )
    if snapshot is ...:
        snapshot = ProviderSnapshot(
            connection_status=ProviderConnectionStatus.CONNECTED,
            data_source=DataSourceMode.MOCK,
            account=make_account(),
            positions=(),
            updated_at=now,
        )
    if quote is ...:
        quote = symbol
    elif quote is False:
        quote = None
    return CandidateExecutionContext(
        tick=tick,
        quote=quote,
        snapshot=snapshot,  # type: ignore[arg-type]
        timeframe_status=tf
        or {"M15": "LIVE", "H1": "LIVE", "H4": "LIVE", "D1": "LIVE"},
        now=now,
    )


class ControllableStore(SnapshotIntentStore):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fail_create = False
        self.fail_in_flight = False
        self.fail_filled = False
        self.in_flight_before_submit = False

    def create_intent(self, intent: ExecutionIntent, *, now: datetime) -> CreateIntentResult:
        if self.fail_create:
            raise RuntimeError("inject_create_fail")
        return super().create_intent(intent, now=now)

    def mark_in_flight(self, intent_id: str, *, now: datetime):
        if self.fail_in_flight:
            raise RuntimeError("inject_in_flight_fail")
        record = super().mark_in_flight(intent_id, now=now)
        self.in_flight_before_submit = True
        return record

    def mark_filled(self, intent_id: str, evidence: Any, *, now: datetime):
        if self.fail_filled:
            raise RuntimeError("inject_filled_fail")
        return super().mark_filled(intent_id, evidence, now=now)


def _service(
    tmp_path: Path,
    *,
    ack: AckStatus = AckStatus.FILLED,
    controllable: bool = False,
    exceptions: list[BaseException] | None = None,
) -> tuple[CandidateExecutionService, SpyExecutionPort, Any, SqliteSetupLifecycleStore]:
    settings = _settings(tmp_path)
    setup_store = require_durable_setup_store(settings)
    paper = PaperExecutor(
        PaperSnapshot.initial(10_000.0),
        config=BacktestConfig.from_settings(settings),
    )
    if controllable:
        intent_store: Any = ControllableStore(paper, persist=lambda: None)
    else:
        intent_store = SnapshotIntentStore(paper, persist=lambda: None)
    on_submit = None
    if controllable:

        def _on_submit(_intent: ExecutionIntent) -> None:
            assert intent_store.in_flight_before_submit is True

        on_submit = _on_submit

    port = SpyExecutionPort(
        responses=ack,
        fill_price=2341.0,
        exceptions=exceptions,
        on_submit=on_submit,
    )

    orch = ExecutionOrchestrator(
        store=intent_store,
        port=port,
        clock=lambda: _NOW,
        guard=default_orchestration_guards(intent_store),
    )
    svc = CandidateExecutionService(
        settings,
        setup_store=setup_store,
        intent_store=intent_store,
        orchestrator=orch,
        port=port,
        clock=lambda: _NOW,
    )
    return svc, port, intent_store, setup_store


def test_idempotency_key_deterministic() -> None:
    setup = _setup()
    side = SignalDirection.LONG
    a = build_candidate_idempotency_key(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=setup.source_candle_timestamp,
        setup_id=setup.setup_id,
        candidate_id="cand_abc",
        side=side,
    )
    b = build_candidate_idempotency_key(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=setup.source_candle_timestamp,
        setup_id=setup.setup_id,
        candidate_id="cand_abc",
        side=side,
    )
    assert a == b
    assert "uuid" not in a.lower()


def test_adapter_maps_without_recalc() -> None:
    setup = _setup()
    cand = _candidate(setup)
    plan = map_candidate_to_execution_plan(cand, setup, decision_timestamp=_NOW)
    assert plan.strategy_id == MTF_STRATEGY_ID
    assert plan.signal_id == cand.candidate_id
    assert plan.requested_volume == 0.01
    assert plan.stop_loss == setup.stop_loss
    assert plan.take_profit == setup.take_profits[0].price
    assert plan.metadata["setup_id"] == setup.setup_id


def test_eligible_filled_exactly_one_submit(tmp_path: Path) -> None:
    svc, port, store, setup_store = _service(tmp_path, controllable=True)
    setup = _setup()
    setup_store.upsert(setup)
    cand = _candidate(setup)
    result = svc.consume(cand, _ctx())
    assert result.precheck.allowed is True
    assert result.port_submit_count == 1
    assert len(port.calls) == 1
    assert store.in_flight_before_submit is True
    assert result.orchestration is not None
    assert result.orchestration.outcome == OrchestrationOutcome.FILLED

    # Duplicate consume
    again = svc.consume(cand, _ctx())
    assert again.port_submit_count == 0
    assert len(port.calls) == 1


def test_rejected_and_unknown_no_retry(tmp_path: Path) -> None:
    svc, port, _, setup_store = _service(tmp_path, ack=AckStatus.REJECTED)
    setup = _setup()
    setup_store.upsert(setup)
    cand = _candidate(setup)
    r1 = svc.consume(cand, _ctx())
    assert r1.orchestration is not None
    assert r1.orchestration.outcome == OrchestrationOutcome.REJECTED
    assert len(port.calls) == 1
    r2 = svc.consume(cand, _ctx())
    assert r2.port_submit_count == 0
    assert len(port.calls) == 1

    svc_u, port_u, _, setup_u = _service(tmp_path / "u", ack=AckStatus.UNKNOWN)
    setup2 = _setup(candle=_candle() - timedelta(minutes=15))
    setup_u.upsert(setup2)
    cand2 = _candidate(setup2)
    u1 = svc_u.consume(cand2, _ctx())
    assert u1.reconciliation == "READ_ONLY_RECONCILIATION_REQUIRED"
    assert len(port_u.calls) == 1
    u2 = svc_u.consume(cand2, _ctx())
    assert u2.port_submit_count == 0
    assert len(port_u.calls) == 1


def test_persistence_fail_before_in_flight_zero_submit(tmp_path: Path) -> None:
    svc, port, store, setup_store = _service(tmp_path, controllable=True)
    store.fail_in_flight = True
    setup = _setup()
    setup_store.upsert(setup)
    result = svc.consume(_candidate(setup), _ctx())
    assert len(port.calls) == 0
    assert result.orchestration is not None
    assert result.orchestration.outcome == OrchestrationOutcome.ERROR


def test_fail_create_zero_submit(tmp_path: Path) -> None:
    svc, port, store, setup_store = _service(tmp_path, controllable=True)
    store.fail_create = True
    setup = _setup()
    setup_store.upsert(setup)
    result = svc.consume(_candidate(setup), _ctx())
    assert len(port.calls) == 0
    assert result.orchestration is not None
    assert result.orchestration.outcome == OrchestrationOutcome.ERROR


def test_fail_after_side_effect_unknown_no_resend(tmp_path: Path) -> None:
    svc, port, store, setup_store = _service(tmp_path, controllable=True)
    store.fail_filled = True
    setup = _setup()
    setup_store.upsert(setup)
    r1 = svc.consume(_candidate(setup), _ctx())
    assert len(port.calls) == 1
    assert r1.orchestration is not None
    assert r1.orchestration.outcome == OrchestrationOutcome.UNKNOWN
    r2 = svc.consume(_candidate(setup), _ctx())
    assert r2.port_submit_count == 0
    assert len(port.calls) == 1


@pytest.mark.parametrize(
    "state,reason",
    [
        (SetupLifecycleState.WAITING_FOR_ENTRY, "PRICE_NOT_IN_ENTRY_ZONE"),
        (SetupLifecycleState.INVALIDATED, "SETUP_INVALIDATED"),
        (SetupLifecycleState.EXPIRED, "SETUP_EXPIRED"),
        (SetupLifecycleState.SUPERSEDED, "SETUP_SUPERSEDED"),
    ],
)
def test_blocked_setup_states(
    tmp_path: Path, state: SetupLifecycleState, reason: str
) -> None:
    svc, port, _, setup_store = _service(tmp_path)
    setup = _setup(state=state)
    if state == SetupLifecycleState.EXPIRED:
        setup = CanonicalTradeSetup(
            **{**setup.__dict__, "expires_at": _NOW - timedelta(minutes=1)}
        )
    setup_store.upsert(setup)
    result = svc.consume(_candidate(setup), _ctx())
    assert result.precheck.allowed is False
    assert reason in result.precheck.reasons
    assert len(port.calls) == 0


def test_risk_and_broker_flags_block(tmp_path: Path) -> None:
    svc, port, _, setup_store = _service(tmp_path)
    setup = _setup()
    setup_store.upsert(setup)
    r = svc.consume(_candidate(setup, risk_ok=False), _ctx())
    assert "RISK_NOT_ACCEPTABLE" in r.precheck.reasons
    assert len(port.calls) == 0
    assert (
        svc.consume(_candidate(setup, broker_ok=False, volume=None), _ctx()).precheck.allowed
        is False
    )
    assert len(port.calls) == 0


@pytest.mark.parametrize("tf", ["M15", "H1", "H4", "D1"])
def test_stale_timeframes_block(tmp_path: Path, tf: str) -> None:
    svc, port, _, setup_store = _service(tmp_path)
    setup = _setup()
    setup_store.upsert(setup)
    statuses = {"M15": "LIVE", "H1": "LIVE", "H4": "LIVE", "D1": "LIVE"}
    statuses[tf] = "STALE"
    r = svc.consume(_candidate(setup), _ctx(tf=statuses))
    assert f"STALE_{tf}" in r.precheck.reasons
    assert len(port.calls) == 0


def test_stale_quote_and_account(tmp_path: Path) -> None:
    svc, port, _, setup_store = _service(tmp_path)
    setup = _setup()
    setup_store.upsert(setup)
    r = svc.consume(_candidate(setup), _ctx(quote_age=120))
    assert "STALE_QUOTE" in r.precheck.reasons
    assert len(port.calls) == 0

    stale_snap = ProviderSnapshot(
        connection_status=ProviderConnectionStatus.CONNECTED,
        data_source=DataSourceMode.MOCK,
        account=make_account(),
        positions=(),
        updated_at=_NOW - timedelta(seconds=120),
    )
    r2 = svc.consume(_candidate(setup), _ctx(snapshot=stale_snap))
    assert "STALE_ACCOUNT" in r2.precheck.reasons

    unknown = SimpleNamespace(
        connection_status=ProviderConnectionStatus.CONNECTED,
        account=make_account(),
        updated_at=None,
        stale=False,
    )
    r3 = svc.consume(_candidate(setup), _ctx(snapshot=unknown))
    assert "ACCOUNT_FRESHNESS_UNKNOWN" in r3.precheck.reasons


def test_missing_metadata_and_spread(tmp_path: Path) -> None:
    svc, port, _, setup_store = _service(tmp_path)
    setup = _setup()
    setup_store.upsert(setup)
    bad = make_xauusd_symbol(bid=2340.9, ask=2341.1)  # tick_size/value absent
    r = svc.consume(_candidate(setup), _ctx(quote=bad))
    assert "BROKER_METADATA_INCOMPLETE" in r.precheck.reasons
    assert len(port.calls) == 0

    r2 = svc.consume(_candidate(setup), _ctx(tick_spread=5.0))  # 500 points
    assert "SPREAD_TOO_WIDE" in r2.precheck.reasons


def test_higher_tf_conflict_and_sr_block(tmp_path: Path) -> None:
    svc, port, _, setup_store = _service(tmp_path)
    setup = _setup()
    setup_store.upsert(setup)
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
    for code in ("HIGHER_TF_CONFLICT", "RESISTANCE_TOO_CLOSE"):
        blocked = build_execution_candidate(
            setup=setup,
            sizing=sizing,
            eligibility=EligibilityResult(
                eligible=False,
                reasons=(code,),
                blocking=(code,),
                warnings=(),
            ),
            now=_NOW,
        )
        assert blocked is not None
        r = svc.consume(blocked, _ctx())
        assert "CANDIDATE_NOT_ELIGIBLE" in r.precheck.reasons
        assert code in r.precheck.reasons
        assert len(port.calls) == 0


def test_legacy_strategy_blocked(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    setup_store = require_durable_setup_store(settings)
    paper = PaperExecutor(
        PaperSnapshot.initial(10_000.0),
        config=BacktestConfig.from_settings(settings),
    )
    intent = SnapshotIntentStore(paper, persist=lambda: None)
    port = SpyExecutionPort(responses=AckStatus.FILLED)
    orch = ExecutionOrchestrator(
        store=intent, port=port, clock=lambda: _NOW, guard=default_orchestration_guards(intent)
    )
    svc = CandidateExecutionService(
        settings,
        setup_store=setup_store,
        intent_store=intent,
        orchestrator=orch,
        port=port,
        strategy_id="ema_rsi_atr_v1",
        clock=lambda: _NOW,
    )
    setup = _setup()
    setup_store.upsert(setup)
    r = svc.consume(_candidate(setup), _ctx())
    assert "LEGACY_STRATEGY_NOT_EXECUTABLE" in r.precheck.reasons
    assert len(port.calls) == 0


def test_fingerprint_mismatch(tmp_path: Path) -> None:
    svc, port, _, setup_store = _service(tmp_path)
    setup = _setup()
    setup_store.upsert(setup)
    cand = _candidate(setup)
    # Corrupt fingerprint on stored setup
    changed = CanonicalTradeSetup(
        **{**setup.__dict__, "analysis_fingerprint": "fp_changed"}
    )
    setup_store.upsert(changed)
    r = svc.consume(cand, _ctx())
    assert "ANALYSIS_FINGERPRINT_CHANGED" in r.precheck.reasons
    assert len(port.calls) == 0


def test_in_memory_store_blocked(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    paper = PaperExecutor(
        PaperSnapshot.initial(10_000.0),
        config=BacktestConfig.from_settings(settings),
    )
    intent = SnapshotIntentStore(paper, persist=lambda: None)
    port = SpyExecutionPort(responses=AckStatus.FILLED)
    orch = ExecutionOrchestrator(
        store=intent, port=port, clock=lambda: _NOW, guard=default_orchestration_guards(intent)
    )
    mem = InMemorySetupLifecycleStore()
    setup = _setup()
    mem.upsert(setup)
    svc = CandidateExecutionService(
        settings,
        setup_store=mem,
        intent_store=intent,
        orchestrator=orch,
        port=port,
        clock=lambda: _NOW,
    )
    r = svc.consume(_candidate(setup), _ctx())
    assert "DURABLE_SETUP_STORE_UNAVAILABLE" in r.precheck.reasons
    assert len(port.calls) == 0


def test_unresolved_intent_blocks(tmp_path: Path) -> None:
    svc2, port2, _store2, setup2_store = _service(tmp_path / "b", ack=AckStatus.UNKNOWN)
    setup_b = _setup(candle=_candle() - timedelta(minutes=30))
    setup2_store.upsert(setup_b)
    u = svc2.consume(_candidate(setup_b), _ctx())
    assert u.orchestration is not None
    assert u.orchestration.lifecycle == IntentLifecycle.UNKNOWN

    setup_c = _setup(candle=_candle() - timedelta(minutes=45))
    setup2_store.upsert(setup_c)
    blocked = svc2.consume(_candidate(setup_c), _ctx())
    assert "UNRESOLVED_EXECUTION_EXISTS" in blocked.precheck.reasons
    assert blocked.port_submit_count == 0
    assert len(port2.calls) == 1


@pytest.mark.parametrize(
    "lifecycle",
    [IntentLifecycle.INTENT_CREATED, IntentLifecycle.IN_FLIGHT, IntentLifecycle.UNKNOWN],
)
def test_seeded_unresolved_lifecycles_block(
    tmp_path: Path, lifecycle: IntentLifecycle
) -> None:
    svc, port, store, setup_store = _service(tmp_path)
    setup = _setup()
    setup_store.upsert(setup)
    record = IntentRecord(
        intent_id=f"seed-{lifecycle.value}",
        idempotency_key=f"seed-key-{lifecycle.value}",
        lifecycle=lifecycle,
        created_at=_NOW,
        updated_at=_NOW,
        side="LONG",
        symbol="XAUUSD",
        requested_quantity=0.01,
        stop_loss=2330.0,
        take_profit=2355.0,
        strategy=MTF_STRATEGY_ID,
        timeframe="M15",
    )
    store._executor.upsert_intent(record)
    r = svc.consume(_candidate(setup), _ctx())
    assert "UNRESOLVED_EXECUTION_EXISTS" in r.precheck.reasons
    assert len(port.calls) == 0


def test_wait_no_setup_blocks(tmp_path: Path) -> None:
    svc, port, _, setup_store = _service(tmp_path)
    setup = _setup(state=SetupLifecycleState.NO_SETUP)
    setup_store.upsert(setup)
    r = svc.consume(_candidate(setup), _ctx())
    assert r.precheck.allowed is False
    assert len(port.calls) == 0


def test_require_durable_rejects_non_sqlite() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="postgresql://x/y")
    with pytest.raises(DurableSetupStoreUnavailableError):
        require_durable_setup_store(settings)


def test_factory_has_no_mt5_imports() -> None:
    """Phase 17.1 Fake path must stay MT5-free. Phase 17.2 demo_* modules are separate."""
    phase_171 = {
        "__init__.py",
        "adapter.py",
        "factory.py",
        "models.py",
        "precheck.py",
        "service.py",
        "smoke_cli.py",
    }
    for path in INTEGRATION.rglob("*.py"):
        if path.name not in phase_171:
            continue
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "broker.mt5" not in node.module
                assert "execution.mt5" not in node.module
        assert "order_send(" not in text
        assert "LiveMT5ExecutionTransport(" not in text
        assert "build_gated_mt5_execution_port(" not in text


def test_duplicate_after_service_recreation(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    setup_store = require_durable_setup_store(settings)
    setup = _setup()
    setup_store.upsert(setup)
    cand = _candidate(setup)

    paper = PaperExecutor(
        PaperSnapshot.initial(10_000.0),
        config=BacktestConfig.from_settings(settings),
    )
    # Persist intents in-memory within same paper object across recreation of service
    intent_store = SnapshotIntentStore(paper, persist=lambda: None)
    port = SpyExecutionPort(responses=AckStatus.FILLED, fill_price=2341.0)

    def _mk() -> CandidateExecutionService:
        orch = ExecutionOrchestrator(
            store=intent_store,
            port=port,
            clock=lambda: _NOW,
            guard=default_orchestration_guards(intent_store),
        )
        return CandidateExecutionService(
            settings,
            setup_store=setup_store,
            intent_store=intent_store,
            orchestrator=orch,
            port=port,
            clock=lambda: _NOW,
        )

    assert _mk().consume(cand, _ctx()).port_submit_count == 1
    assert _mk().consume(cand, _ctx()).port_submit_count == 0
    assert len(port.calls) == 1


def test_build_fake_factory_smoke(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service, port, _ = build_fake_candidate_execution_service(
        settings, state_dir=tmp_path / "paper", ack=AckStatus.FILLED
    )
    assert isinstance(service._setup_store, SqliteSetupLifecycleStore)
    assert len(port.calls) == 0
