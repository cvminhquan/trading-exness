"""Phase 17.3 — Autonomous DEMO execution loop (FakeMT5ExecutionTransport ONLY).

Never constructs or imports LiveMT5 / real broker order_send.
"""

from __future__ import annotations

import ast
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
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import AccountInfo, Position, Tick
from exness_bot.execution.auto_demo.decision_store import (
    AutoDemoDecisionState,
    SqliteAutoDemoDecisionStore,
    build_decision_id,
)
from exness_bot.execution.auto_demo.factory import build_auto_demo_candidate_execution_service
from exness_bot.execution.auto_demo.loop import (
    AutoDemoCandidateBundle,
    AutonomousDemoExecutionLoop,
    ClosedM15Observation,
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
from exness_bot.market_analysis.setup import TakeProfitLevel
from exness_bot.risk.models import RiskState
from tests.fixtures.risk_data import make_account, make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
AUTO_DEMO = SRC / "execution" / "auto_demo"
SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"
_NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
_CLOSED = datetime(2026, 9, 8, 9, 45, tzinfo=UTC)

_FORBIDDEN_ISOLATION = (
    "ExternalMarketContext",
    "MarketSynthesis",
    "analyst chat",
    "analyst_chat",
    "AnalystChat",
    "FreeSources",
    "gemini",
    "grounding",
    "bls",
    "rss",
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


def _complete_symbol(*, bid: float = 2340.9, ask: float = 2341.1, spread: int = 20) -> Any:
    return make_xauusd_symbol(bid=bid, ask=ask, spread=spread, stops_level=10, freeze_level=0).model_copy(
        update={"trade_tick_size": 0.01, "trade_tick_value": 1.0}
    )


def _setup(
    *,
    state: SetupLifecycleState = SetupLifecycleState.ENTRY_ZONE,
    candle: datetime | None = None,
) -> CanonicalTradeSetup:
    c = candle or (_NOW - timedelta(minutes=5))
    direction = "LONG"
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
        raw_volume=volume or 0.01,
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


def _filled_transport(
    volume: float = 0.01,
    *,
    on_before_send: Any | None = None,
) -> FakeMT5ExecutionTransport:
    return FakeMT5ExecutionTransport(
        default=MT5TransportResult(
            outcome=TransportOutcome.FILLED,
            price=2341.1,
            volume=volume,
            retcode=10009,
            order_id="1",
            deal_id="2",
        ),
        on_before_send=on_before_send,
    )


def _demo_account(*, equity: float = 10_000.0, trade_mode: str = "demo") -> AccountInfo:
    base = make_account(equity=equity, trade_mode=trade_mode)
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


def _make_context(
    *,
    account: AccountInfo | None = None,
    quote: Any | None = None,
    bid: float = 2340.9,
    ask: float = 2341.1,
) -> CandidateExecutionContext:
    acct = account or _demo_account()
    sym = quote or _complete_symbol(bid=bid, ask=ask)
    tick = Tick(
        symbol=SYMBOL,
        bid=bid,
        ask=ask,
        last=ask,
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


def _open_position(*, ticket: int = 1) -> Position:
    return Position(
        ticket=ticket,
        symbol=SYMBOL,
        volume=0.01,
        direction=SignalDirection.LONG,
        open_price=2340.0,
        current_price=2341.0,
        open_time=_NOW - timedelta(hours=1),
    )


def _harness(
    tmp_path: Path,
    *,
    settings: Settings | None = None,
    transport: FakeMT5ExecutionTransport | None = None,
    setup: CanonicalTradeSetup | None = None,
    candidate: Any | None = None,
    account: AccountInfo | None = None,
    trade_mode: str = "demo",
    positions: list[Position] | None = None,
    risk_state: RiskState | None = None,
    blocked_reasons: tuple[str, ...] = (),
    quote: Any | None = None,
    closed_at: datetime | None = None,
    decision_store: SqliteAutoDemoDecisionStore | None = None,
    state_name: str = "paper.json",
) -> dict[str, Any]:
    cfg = settings or _settings(tmp_path)
    acct = account or _demo_account()
    setup = setup or _setup()
    candidate = candidate or _candidate(setup)
    transport = transport or _filled_transport(volume=float(candidate.proposed_volume or 0.01))
    closed = closed_at or _CLOSED
    observation = ClosedM15Observation(symbol=SYMBOL, timeframe="M15", closed_at=closed)

    setup_store = require_durable_setup_store(cfg)
    setup_store.upsert(setup)

    decision_path = tmp_path / "auto_demo_decisions.db"
    store = decision_store or SqliteAutoDemoDecisionStore(decision_path)

    pos_list = list(positions) if positions is not None else []
    risk_holder: dict[str, RiskState | None] = {"state": risk_state}
    bundle_holder: dict[str, Any] = {
        "setup": setup,
        "candidate": candidate,
        "blocked_reasons": blocked_reasons,
        "quote": quote,
        "account": acct,
    }
    obs_holder = {"obs": observation}

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

    service, _gated, _intent = build_auto_demo_candidate_execution_service(
        cfg,
        transport=transport,
        snapshot_provider=snapshot_provider,
        setup_store=setup_store,
        state_path=tmp_path / state_name,
        clock=lambda: _NOW,
        settings_provider=lambda: cfg,
    )

    def observe() -> ClosedM15Observation | None:
        return obs_holder["obs"]

    def build_bundle(_obs: ClosedM15Observation) -> AutoDemoCandidateBundle:
        current_setup = bundle_holder["setup"]
        current_cand = bundle_holder["candidate"]
        setup_store.upsert(current_setup)
        ctx = _make_context(
            account=bundle_holder["account"],
            quote=bundle_holder["quote"],
        )
        return AutoDemoCandidateBundle(
            candidate=current_cand,
            context=ctx,
            blocked_reasons=tuple(bundle_holder["blocked_reasons"]),
            signal="LONG",
        )

    loop = AutonomousDemoExecutionLoop(
        settings=cfg,
        decision_store=store,
        observe_closed_m15=observe,
        build_bundle=build_bundle,
        service=service,
        account_provider=lambda: bundle_holder["account"],
        positions_provider=lambda: list(pos_list),
        risk_state_provider=lambda _a: risk_holder["state"],
        settings_provider=lambda: cfg,
    )

    return {
        "settings": cfg,
        "transport": transport,
        "decision_store": store,
        "setup_store": setup_store,
        "loop": loop,
        "observation": observation,
        "obs_holder": obs_holder,
        "bundle_holder": bundle_holder,
        "pos_list": pos_list,
        "risk_holder": risk_holder,
        "setup": setup,
        "candidate": candidate,
        "account": acct,
        "service": service,
        "decision_path": decision_path,
    }


# ---------------------------------------------------------------------------
# Enablement / gate: zero sends
# ---------------------------------------------------------------------------


def test_auto_demo_disabled_zero_sends(tmp_path: Path) -> None:
    cfg = _settings(tmp_path, AUTO_DEMO_EXECUTION_ENABLED=False)
    transport = _filled_transport()
    h = _harness(tmp_path, settings=cfg, transport=transport)
    record = h["loop"].run_once()
    assert len(transport.calls) == 0
    assert record is not None
    assert record.state == AutoDemoDecisionState.BLOCKED.value
    assert any("AUTO_DEMO_EXECUTION_ENABLED" in r for r in record.blocked_reasons)


def test_kill_switch_on_zero_sends(tmp_path: Path) -> None:
    cfg = _settings(tmp_path, LIVE_KILL_SWITCH=True)
    transport = _filled_transport()
    h = _harness(tmp_path, settings=cfg, transport=transport)
    record = h["loop"].run_once()
    assert len(transport.calls) == 0
    assert record is not None
    assert record.state == AutoDemoDecisionState.BLOCKED.value
    assert any("LIVE_KILL_SWITCH" in r for r in record.blocked_reasons)


def test_approval_false_zero_sends(tmp_path: Path) -> None:
    cfg = _settings(tmp_path, LIVE_DEMO_APPROVAL=False)
    transport = _filled_transport()
    h = _harness(tmp_path, settings=cfg, transport=transport)
    h["loop"].run_once()
    assert len(transport.calls) == 0


def test_allowlist_mismatch_zero_sends(tmp_path: Path) -> None:
    cfg = _settings(tmp_path, DEMO_ACCOUNT_ALLOWLIST="99999999")
    transport = _filled_transport()
    h = _harness(tmp_path, settings=cfg, transport=transport)
    h["loop"].run_once()
    assert len(transport.calls) == 0


def test_non_demo_trading_env_zero_sends(tmp_path: Path) -> None:
    cfg = _settings(tmp_path, TRADING_ENV="research")
    transport = _filled_transport()
    h = _harness(tmp_path, settings=cfg, transport=transport)
    h["loop"].run_once()
    assert len(transport.calls) == 0


def test_unknown_account_trade_mode_zero_sends(tmp_path: Path) -> None:
    transport = _filled_transport()
    h = _harness(tmp_path, transport=transport, trade_mode="")
    h["loop"].run_once()
    assert len(transport.calls) == 0


# ---------------------------------------------------------------------------
# Happy path + idempotency
# ---------------------------------------------------------------------------


def test_eligible_candidate_exactly_one_fake_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    h = _harness(tmp_path, transport=transport)
    record = h["loop"].run_once()
    assert len(transport.calls) == 1
    assert record is not None
    assert record.state == AutoDemoDecisionState.ACCEPTED.value
    assert h["loop"].submissions == 1


def test_same_m15_twice_one_send_total(tmp_path: Path) -> None:
    transport = _filled_transport()
    h = _harness(tmp_path, transport=transport)
    r1 = h["loop"].run_once()
    r2 = h["loop"].run_once()
    assert len(transport.calls) == 1
    assert r1 is not None and r1.state == AutoDemoDecisionState.ACCEPTED.value
    assert r2 is not None and r2.decision_id == r1.decision_id


def test_restart_same_m15_reload_store_no_duplicate(tmp_path: Path) -> None:
    transport = _filled_transport()
    h1 = _harness(tmp_path, transport=transport, state_name="paper1.json")
    r1 = h1["loop"].run_once()
    assert len(transport.calls) == 1
    assert r1 is not None
    assert r1.state == AutoDemoDecisionState.ACCEPTED.value

    store2 = SqliteAutoDemoDecisionStore(h1["decision_path"])
    h2 = _harness(
        tmp_path,
        settings=h1["settings"],
        transport=transport,
        setup=h1["setup"],
        candidate=h1["candidate"],
        decision_store=store2,
        state_name="paper2.json",
    )
    r2 = h2["loop"].run_once()
    assert len(transport.calls) == 1
    assert r2 is not None
    assert r2.state == AutoDemoDecisionState.ACCEPTED.value
    assert r2.decision_id == r1.decision_id


def test_next_closed_m15_new_evaluation_can_send_again(tmp_path: Path) -> None:
    transport = _filled_transport()
    h = _harness(tmp_path, transport=transport)
    r1 = h["loop"].run_once()
    assert len(transport.calls) == 1
    assert r1 is not None

    next_closed = _CLOSED + timedelta(minutes=15)
    next_setup = _setup(candle=_NOW - timedelta(minutes=20))
    next_cand = _candidate(next_setup)
    h["setup_store"].upsert(next_setup)
    h["bundle_holder"]["setup"] = next_setup
    h["bundle_holder"]["candidate"] = next_cand
    h["obs_holder"]["obs"] = ClosedM15Observation(
        symbol=SYMBOL, timeframe="M15", closed_at=next_closed
    )

    r2 = h["loop"].run_once()
    assert len(transport.calls) == 2
    assert r2 is not None
    assert r2.decision_id != r1.decision_id
    assert r2.state == AutoDemoDecisionState.ACCEPTED.value


# ---------------------------------------------------------------------------
# Candidate / risk gates
# ---------------------------------------------------------------------------


def test_blocked_candidate_zero_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    h = _harness(
        tmp_path,
        transport=transport,
        blocked_reasons=("ENTRY_ZONE_NOT_READY",),
    )
    record = h["loop"].run_once()
    assert len(transport.calls) == 0
    assert record is not None
    assert record.state == AutoDemoDecisionState.BLOCKED.value
    assert "ENTRY_ZONE_NOT_READY" in record.blocked_reasons


def test_open_position_limit_zero_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    h = _harness(
        tmp_path,
        transport=transport,
        positions=[_open_position()],
    )
    record = h["loop"].run_once()
    assert len(transport.calls) == 0
    assert record is not None
    assert record.state == AutoDemoDecisionState.BLOCKED.value
    assert any(r.startswith("OPEN_POSITIONS:") for r in record.blocked_reasons)


def test_daily_loss_breach_zero_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    account = _demo_account(equity=9_750.0)
    risk = RiskState(day_start_equity=10_000.0, peak_equity=9_750.0)
    h = _harness(tmp_path, transport=transport, account=account, risk_state=risk)
    record = h["loop"].run_once()
    assert len(transport.calls) == 0
    assert record is not None
    assert record.state == AutoDemoDecisionState.BLOCKED.value
    assert any(r.startswith("DAILY_LOSS:") for r in record.blocked_reasons)


def test_drawdown_breach_zero_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    account = _demo_account(equity=9_400.0)
    risk = RiskState(day_start_equity=9_400.0, peak_equity=10_000.0)
    h = _harness(tmp_path, transport=transport, account=account, risk_state=risk)
    record = h["loop"].run_once()
    assert len(transport.calls) == 0
    assert record is not None
    assert record.state == AutoDemoDecisionState.BLOCKED.value
    assert any(r.startswith("DRAWDOWN:") for r in record.blocked_reasons)


def test_spread_breach_zero_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    wide = _complete_symbol(bid=2340.0, ask=2345.0, spread=500)
    h = _harness(tmp_path, transport=transport, quote=wide)
    record = h["loop"].run_once()
    assert len(transport.calls) == 0
    assert record is not None
    assert record.state == AutoDemoDecisionState.BLOCKED.value
    assert any(r.startswith("SPREAD:") for r in record.blocked_reasons)


# ---------------------------------------------------------------------------
# Persistence / lifecycle
# ---------------------------------------------------------------------------


def test_persistence_failure_before_in_flight_zero_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    h = _harness(tmp_path, transport=transport)
    store: SqliteAutoDemoDecisionStore = h["decision_store"]
    real_upsert = store.upsert

    def failing_upsert(record: Any) -> Any:
        if record.state == AutoDemoDecisionState.IN_FLIGHT.value:
            raise RuntimeError("forced persist failure before IN_FLIGHT")
        return real_upsert(record)

    store.upsert = failing_upsert  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="forced persist failure"):
        h["loop"].run_once()
    assert len(transport.calls) == 0


def test_in_flight_persisted_before_transport_call(tmp_path: Path) -> None:
    decision_id = build_decision_id(
        symbol=SYMBOL,
        timeframe="M15",
        closed_m15_timestamp=_CLOSED,
        strategy_id=MTF_STRATEGY_ID,
    )
    seen: list[str] = []

    def on_before_send(_request: dict[str, Any]) -> None:
        rec = store_holder["store"].get(decision_id)
        assert rec is not None
        assert rec.state == AutoDemoDecisionState.IN_FLIGHT.value
        seen.append(rec.state)

    store_holder: dict[str, SqliteAutoDemoDecisionStore] = {}
    transport = _filled_transport(on_before_send=on_before_send)
    h = _harness(tmp_path, transport=transport)
    store_holder["store"] = h["decision_store"]
    record = h["loop"].run_once()
    assert len(transport.calls) == 1
    assert seen == [AutoDemoDecisionState.IN_FLIGHT.value]
    assert record is not None
    assert record.state == AutoDemoDecisionState.ACCEPTED.value


def test_accepted_persists_accepted(tmp_path: Path) -> None:
    transport = _filled_transport()
    h = _harness(tmp_path, transport=transport)
    record = h["loop"].run_once()
    assert record is not None
    assert record.state == AutoDemoDecisionState.ACCEPTED.value
    reloaded = h["decision_store"].get(record.decision_id)
    assert reloaded is not None
    assert reloaded.state == AutoDemoDecisionState.ACCEPTED.value


def test_rejected_persists_rejected(tmp_path: Path) -> None:
    transport = FakeMT5ExecutionTransport(
        default=MT5TransportResult(
            outcome=TransportOutcome.REJECTED,
            retcode=10013,
            comment="reject",
        )
    )
    h = _harness(tmp_path, transport=transport)
    record = h["loop"].run_once()
    assert len(transport.calls) == 1
    assert record is not None
    assert record.state == AutoDemoDecisionState.REJECTED.value
    reloaded = h["decision_store"].get(record.decision_id)
    assert reloaded is not None
    assert reloaded.state == AutoDemoDecisionState.REJECTED.value


def test_timeout_ambiguous_unknown_no_resubmit(tmp_path: Path) -> None:
    transport = FakeMT5ExecutionTransport(
        default=MT5TransportResult(
            outcome=TransportOutcome.TIMEOUT,
            comment="timeout_ambiguous",
        )
    )
    h = _harness(tmp_path, transport=transport)
    r1 = h["loop"].run_once()
    assert len(transport.calls) == 1
    assert r1 is not None
    assert r1.state == AutoDemoDecisionState.UNKNOWN.value

    r2 = h["loop"].run_once()
    assert len(transport.calls) == 1
    assert r2 is not None
    assert r2.decision_id == r1.decision_id
    assert r2.state == AutoDemoDecisionState.UNKNOWN.value


# ---------------------------------------------------------------------------
# Isolation / static scans
# ---------------------------------------------------------------------------


def test_factory_never_imports_live_mt5() -> None:
    text = (AUTO_DEMO / "factory.py").read_text(encoding="utf-8")
    assert "order_send(" not in text
    assert "LiveMT5ExecutionTransport(" not in text
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "LiveMT5" not in node.module
            for alias in node.names:
                assert "LiveMT5" not in alias.name
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "LiveMT5" not in alias.name


def test_auto_demo_package_isolation_no_external_market_ai() -> None:
    for path in sorted(AUTO_DEMO.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for needle in _FORBIDDEN_ISOLATION:
            assert needle.lower() not in lowered, f"{path.name} contains forbidden '{needle}'"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.lower()
                for needle in (
                    "externalmarketcontext",
                    "marketsynthesis",
                    "freesources",
                    "gemini",
                    "grounding",
                    "analyst",
                ):
                    assert needle not in mod, f"{path.name} imports {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.lower()
                    for needle in ("gemini", "grounding", "freesources"):
                        assert needle not in name, f"{path.name} imports {alias.name}"


def test_auto_demo_has_zero_order_send() -> None:
    """order_send(...) must live only in LiveMT5ExecutionTransport — never in auto_demo."""
    for path in sorted(AUTO_DEMO.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "order_send(" not in text, f"{path.name} must not call order_send"
