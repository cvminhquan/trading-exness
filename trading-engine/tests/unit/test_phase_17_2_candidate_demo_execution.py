"""Phase 17.2 — ExecutionCandidate → GatedMT5 DEMO (Fake transport only).

Never runs LiveMT5 / --execute against real broker.
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
from exness_bot.controlled_demo.identity import (
    DemoIdentitySnapshot,
    DemoMarketSnapshot,
    StaticDemoBrokerProbe,
)
from exness_bot.controlled_demo.intent_factory import CONTROLLED_DEMO_TEST_VOLUME
from exness_bot.controlled_demo.smoke import CONFIRM_PHRASE
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.models import AccountInfo, Tick
from exness_bot.execution.integration.demo_cli import (
    AGENT_PROHIBITION,
    run_candidate_demo_execution_smoke,
)
from exness_bot.execution.integration.demo_factory import (
    build_controlled_demo_candidate_execution_service,
)
from exness_bot.execution.integration.demo_revalidate import EXECUTED_TP_POLICY
from exness_bot.execution.integration.factory import require_durable_setup_store
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
from exness_bot.paper_execution.contract import IntentLifecycle
from tests.fixtures.risk_data import make_account, make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
INTEGRATION = SRC / "execution" / "integration"
SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"
_NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


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
        "LIVE_DATA_STALE_SECONDS": 10,
        "ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS": 10,
        "RISK_PER_TRADE_PCT": 0.5,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _complete_symbol(*, bid: float = 2340.9, ask: float = 2341.1) -> Any:
    return make_xauusd_symbol(bid=bid, ask=ask, stops_level=10, freeze_level=0).model_copy(
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


def _identity(*, trade_mode: str = "demo") -> DemoIdentitySnapshot:
    account = make_account()
    account = AccountInfo(
        login=12345678,
        balance=account.balance,
        equity=account.equity,
        margin=account.margin,
        free_margin=account.free_margin,
        currency="USD",
        leverage=500,
        server="Exness-MT5Trial",
        trade_mode=trade_mode,
    )
    return DemoIdentitySnapshot(
        account=account,
        trade_allowed=True,
        currency="USD",
        server=account.server,
        login=account.login,
        trade_mode=trade_mode,
        terminal_trade_allowed=True,
    )


def _market(
    *,
    bid: float = 2340.9,
    ask: float = 2341.1,
    age: float = 1.0,
    fresh: bool = True,
    symbol: Any | None = None,
) -> DemoMarketSnapshot:
    sym = symbol or _complete_symbol(bid=bid, ask=ask)
    tick = Tick(
        symbol=BROKER,
        bid=bid,
        ask=ask,
        last=ask,
        volume=1.0,
        timestamp=_NOW - timedelta(seconds=age),
    )
    return DemoMarketSnapshot(
        symbol=sym,
        tick=tick,
        freshness=QuoteFreshness.LIVE if fresh else QuoteFreshness.STALE,
        age_seconds=age,
        spread_points=abs(ask - bid) / sym.point,
    )


def _filled_transport(volume: float = 0.01) -> FakeMT5ExecutionTransport:
    return FakeMT5ExecutionTransport(
        default=MT5TransportResult(
            outcome=TransportOutcome.FILLED,
            price=2341.1,
            volume=volume,
            retcode=10009,
            order_id="1",
            deal_id="2",
        )
    )


def _run(
    tmp_path: Path,
    *,
    execute: bool = True,
    confirm: str = CONFIRM_PHRASE,
    settings: Settings | None = None,
    transport: FakeMT5ExecutionTransport | None = None,
    setup: CanonicalTradeSetup | None = None,
    candidate: Any | None = None,
    market: DemoMarketSnapshot | None = None,
    identity: DemoIdentitySnapshot | None = None,
    tf: dict[str, str] | None = None,
    state_name: str = "state.json",
) -> Any:
    cfg = settings or _settings(tmp_path)
    store = require_durable_setup_store(cfg)
    setup = setup or _setup()
    candidate = candidate or _candidate(setup)
    transport = transport or _filled_transport(volume=float(candidate.proposed_volume or 0.01))
    probe = StaticDemoBrokerProbe(
        identity=identity or _identity(),
        market=market or _market(),
    )
    return run_candidate_demo_execution_smoke(
        symbol=SYMBOL,
        execute=execute,
        confirm=confirm,
        settings=cfg,
        probe=probe,
        transport=transport,
        candidate=candidate,
        setup=setup,
        timeframe_status=tf
        or {"M15": "LIVE", "H1": "LIVE", "H4": "LIVE", "D1": "LIVE"},
        real_broker_submission=False,
        state_path=tmp_path / state_name,
        setup_store=store,
        clock=lambda: _NOW,
    )


def test_agent_prohibition_documented() -> None:
    assert "--execute" in AGENT_PROHIBITION
    assert "DEMO-EXECUTE" in AGENT_PROHIBITION
    assert EXECUTED_TP_POLICY == "TP1_ONLY"


def test_preview_never_sends(tmp_path: Path) -> None:
    transport = _filled_transport()
    result = _run(tmp_path, execute=False, confirm="", transport=transport)
    assert result.mode == "PREVIEW"
    assert result.transport_send_count == 0
    assert len(transport.calls) == 0
    assert result.real_broker_submission is False


def test_execute_without_confirm_zero_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    result = _run(tmp_path, execute=True, confirm="WRONG", transport=transport)
    assert result.blocked is True
    assert len(transport.calls) == 0


def test_execute_omitted_zero_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    result = _run(tmp_path, execute=False, confirm=CONFIRM_PHRASE, transport=transport)
    assert len(transport.calls) == 0
    assert result.mode == "PREVIEW"


def test_allowed_fake_filled_exactly_one_send(tmp_path: Path) -> None:
    transport = _filled_transport(volume=0.01)
    result = _run(tmp_path, transport=transport)
    assert result.blocked is False
    assert result.executor_submit_count == 1
    assert result.transport_send_count == 1
    assert len(transport.calls) == 1
    assert result.lifecycle is IntentLifecycle.FILLED
    # proposed_volume from candidate — not forced Phase-12 test volume constant alone
    vol = transport.calls[0].get("volume")
    assert vol == 0.01
    assert result.proposed_volume == 0.01
    assert result.tp_policy == "TP1_ONLY"


def test_candidate_volume_not_forced_to_phase12_constant(tmp_path: Path) -> None:
    """If candidate proposes 0.02, must not rewrite to CONTROLLED_DEMO_TEST_VOLUME."""
    setup = _setup()
    cand = _candidate(setup, volume=0.02)
    assert cand.proposed_volume == 0.02
    assert CONTROLLED_DEMO_TEST_VOLUME == 0.01
    assert cand.proposed_volume != CONTROLLED_DEMO_TEST_VOLUME
    transport = _filled_transport(volume=0.02)
    result = _run(tmp_path, setup=setup, candidate=cand, transport=transport)
    assert result.blocked is False
    assert transport.calls[0]["volume"] == 0.02


def test_duplicate_consume_no_second_send(tmp_path: Path) -> None:
    transport = _filled_transport()
    setup = _setup()
    cand = _candidate(setup)
    r1 = _run(tmp_path, setup=setup, candidate=cand, transport=transport, state_name="s.json")
    assert len(transport.calls) == 1
    r2 = _run(tmp_path, setup=setup, candidate=cand, transport=transport, state_name="s.json")
    assert r1.transport_send_count == 1
    assert len(transport.calls) == 1
    assert r2.transport_send_count == 0


def test_unknown_no_resubmit(tmp_path: Path) -> None:
    transport = FakeMT5ExecutionTransport(
        default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN, comment="ambig")
    )
    setup = _setup()
    cand = _candidate(setup)
    r1 = _run(tmp_path, setup=setup, candidate=cand, transport=transport, state_name="u.json")
    assert r1.lifecycle is IntentLifecycle.UNKNOWN
    assert len(transport.calls) == 1
    r2 = _run(tmp_path, setup=setup, candidate=cand, transport=transport, state_name="u.json")
    assert len(transport.calls) == 1
    assert r2.transport_send_count == 0


@pytest.mark.parametrize(
    "kwargs,needle",
    [
        ({"settings_kw": {"LIVE_KILL_SWITCH": True}}, None),
        ({"settings_kw": {"LIVE_DEMO_APPROVAL": False}}, None),
        ({"settings_kw": {"TRADING_ENV": "research"}}, None),
        ({"identity": "live"}, None),
        ({"price_out": True}, "PRICE_NOT_IN_ENTRY_ZONE"),
        ({"spread": True}, "SPREAD_TOO_WIDE"),
        ({"stale_tf": "M15"}, "STALE_M15"),
        ({"risk": False}, "RISK_NOT_ACCEPTABLE"),
        ({"eligible": False}, "CANDIDATE_NOT_ELIGIBLE"),
        ({"state": SetupLifecycleState.WAITING_FOR_ENTRY}, "PRICE_NOT_IN_ENTRY_ZONE"),
        ({"state": SetupLifecycleState.INVALIDATED}, "SETUP_INVALIDATED"),
        ({"state": SetupLifecycleState.EXPIRED}, "SETUP_EXPIRED"),
        ({"state": SetupLifecycleState.SUPERSEDED}, "SETUP_SUPERSEDED"),
    ],
)
def test_zero_send_matrix(tmp_path: Path, kwargs: dict[str, Any], needle: str | None) -> None:
    settings_kw = kwargs.get("settings_kw", {})
    cfg = _settings(tmp_path, **settings_kw)
    setup = _setup(state=kwargs.get("state", SetupLifecycleState.ENTRY_ZONE))
    if setup.state == SetupLifecycleState.EXPIRED:
        setup = CanonicalTradeSetup(
            **{**setup.__dict__, "expires_at": _NOW - timedelta(minutes=1)}
        )
    cand = _candidate(
        setup,
        eligible=kwargs.get("eligible", True),
        risk_ok=kwargs.get("risk", True) is not False,
    )
    market = _market()
    if kwargs.get("price_out"):
        market = _market(bid=2400.0, ask=2400.2)
    if kwargs.get("spread"):
        market = _market(bid=2340.0, ask=2345.0)  # 500 points
    identity = _identity(trade_mode="live") if kwargs.get("identity") == "live" else _identity()
    tf = {"M15": "LIVE", "H1": "LIVE", "H4": "LIVE", "D1": "LIVE"}
    if kwargs.get("stale_tf"):
        tf[str(kwargs["stale_tf"])] = "STALE"
    transport = _filled_transport()
    result = _run(
        tmp_path,
        settings=cfg,
        setup=setup,
        candidate=cand,
        market=market,
        identity=identity,
        tf=tf,
        transport=transport,
    )
    assert len(transport.calls) == 0
    assert result.transport_send_count == 0
    if needle and result.candidate_precheck is not None:
        assert needle in result.candidate_precheck.reasons


def test_missing_metadata_zero_send(tmp_path: Path) -> None:
    bad = make_xauusd_symbol(bid=2340.9, ask=2341.1)  # no tick size/value
    transport = _filled_transport()
    result = _run(tmp_path, market=_market(symbol=bad), transport=transport)
    assert len(transport.calls) == 0
    assert result.candidate_precheck is not None
    assert "BROKER_METADATA_INCOMPLETE" in result.candidate_precheck.reasons


def test_unresolved_intent_zero_send(tmp_path: Path) -> None:
    cfg = _settings(tmp_path)
    setup = _setup()
    cand = _candidate(setup)
    state = tmp_path / "block.json"
    transport_u = FakeMT5ExecutionTransport(
        default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN)
    )
    r1 = _run(
        tmp_path,
        settings=cfg,
        setup=setup,
        candidate=cand,
        transport=transport_u,
        state_name="block.json",
    )
    assert r1.lifecycle is IntentLifecycle.UNKNOWN
    assert len(transport_u.calls) == 1

    setup2 = _setup(candle=_NOW - timedelta(minutes=30))
    cand2 = _candidate(setup2)
    transport = _filled_transport()
    result = run_candidate_demo_execution_smoke(
        symbol=SYMBOL,
        execute=True,
        confirm=CONFIRM_PHRASE,
        settings=cfg,
        probe=StaticDemoBrokerProbe(identity=_identity(), market=_market()),
        transport=transport,
        candidate=cand2,
        setup=setup2,
        timeframe_status={"M15": "LIVE", "H1": "LIVE", "H4": "LIVE", "D1": "LIVE"},
        state_path=state,
        setup_store=require_durable_setup_store(cfg),
    )
    assert len(transport.calls) == 0
    assert result.blocked is True


def test_factory_never_imports_live_mt5() -> None:
    text = (INTEGRATION / "demo_factory.py").read_text(encoding="utf-8")
    assert "order_send(" not in text
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "LiveMT5" not in node.module
            for alias in node.names:
                assert "LiveMT5" not in alias.name
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "LiveMT5" not in alias.name
    # Must not construct Live transport in factory body
    assert "LiveMT5ExecutionTransport(" not in text


def test_demo_cli_has_no_order_send_call() -> None:
    text = (INTEGRATION / "demo_cli.py").read_text(encoding="utf-8")
    assert "order_send(" not in text
    # May import LiveMT5ExecutionTransport for human CLI path only
    assert "AGENT_PROHIBITION" in text


def test_build_demo_factory_with_fake(tmp_path: Path) -> None:
    cfg = _settings(tmp_path)
    transport = _filled_transport()
    oneshot_holder: list[Any] = []

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

    service, gated, store, oneshot = build_controlled_demo_candidate_execution_service(
        cfg,
        transport=transport,
        snapshot_provider=snapshot_provider,
        state_path=tmp_path / "p.json",
    )
    oneshot_holder.append(oneshot)
    assert gated.executor_submit_count == 0
    assert store.list_blocking() == ()
    assert service._transport_label == "GATED_MT5_DEMO"


def test_allowlist_and_server_block(tmp_path: Path) -> None:
    cfg = _settings(tmp_path, DEMO_ACCOUNT_ALLOWLIST="999")
    transport = _filled_transport()
    result = _run(tmp_path, settings=cfg, transport=transport)
    assert len(transport.calls) == 0

    cfg2 = _settings(tmp_path / "b", DEMO_SERVER_ALLOWLIST="OtherServer")
    transport2 = _filled_transport()
    result2 = _run(tmp_path / "b", settings=cfg2, transport=transport2)
    assert len(transport2.calls) == 0
    del result, result2
