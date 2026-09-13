"""Phase 17.3.3 — Pre-DEMO Execution Correctness Gate (FakeMT5 ONLY)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from exness_bot.broker.mt5.execution_transport import (
    FakeMT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.enablement import DemoGateName
from exness_bot.controlled_demo.identity import (
    DemoIdentitySnapshot,
    DemoMarketSnapshot,
    ReadOnlyMt5DemoProbe,
    StaticDemoBrokerProbe,
)
from exness_bot.controlled_demo.smoke import CONFIRM_PHRASE
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.models import AccountInfo, Tick
from exness_bot.execution.auto_demo.factory import resolve_auto_demo_state_path
from exness_bot.execution.auto_demo.runtime_snapshot import read_auto_demo_runtime_facts
from exness_bot.execution.integration.demo_cli import run_candidate_demo_execution_smoke
from exness_bot.execution.integration.demo_revalidate import (
    CURRENT_PRICE_OUTSIDE_ENTRY_ZONE,
    QUOTE_NON_FINITE,
    current_price_in_frozen_entry_zone,
    executable_price,
    revalidate_candidate_market,
)
from exness_bot.execution.integration.factory import require_durable_setup_store
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
from tests.fixtures.risk_data import make_account, make_xauusd_symbol

SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"
_NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
ZONE_LO = 2338.0
ZONE_HI = 2342.0


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
    direction: str = "LONG",
    state: SetupLifecycleState = SetupLifecycleState.ENTRY_ZONE,
) -> CanonicalTradeSetup:
    c = _NOW - timedelta(minutes=5)
    if direction == "LONG":
        tps = (
            TakeProfitLevel(1, 2355.0, 30.0, 1.5, "TP1"),
            TakeProfitLevel(2, 2370.0, 40.0, 3.0, "TP2"),
        )
        sl = 2330.0
        entry = 2340.0
    else:
        tps = (
            TakeProfitLevel(1, 2325.0, 30.0, 1.5, "TP1"),
            TakeProfitLevel(2, 2310.0, 40.0, 3.0, "TP2"),
        )
        sl = 2350.0
        entry = 2340.0
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
        entry_zone_low=ZONE_LO,
        entry_zone_high=ZONE_HI,
        stop_loss=sl,
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
        entry_zone_low=ZONE_LO,
        entry_zone_high=ZONE_HI,
        entry_price=entry,
        stop_loss=sl,
        take_profits=tps,
        confidence_score=80.0,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        analysis_fingerprint=fp,
        state=state,
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )


def _candidate(setup: CanonicalTradeSetup, *, volume: float | None = 0.01) -> Any:
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


def _identity() -> DemoIdentitySnapshot:
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
        trade_mode="demo",
    )
    return DemoIdentitySnapshot(
        account=account,
        trade_allowed=True,
        currency="USD",
        server=account.server,
        login=account.login,
        trade_mode="demo",
        terminal_trade_allowed=True,
    )


def _market(
    *,
    bid: float = 2340.9,
    ask: float = 2341.1,
    age: float = 1.0,
    fresh: bool = True,
    include_tick: bool = True,
) -> DemoMarketSnapshot:
    sym = _complete_symbol(bid=bid, ask=ask)
    tick = (
        Tick(
            symbol=BROKER,
            bid=bid,
            ask=ask,
            last=ask,
            volume=1.0,
            timestamp=_NOW - timedelta(seconds=age),
        )
        if include_tick
        else None
    )
    spread = 0.0 if not math.isfinite(bid) or not math.isfinite(ask) else abs(ask - bid)
    return DemoMarketSnapshot(
        symbol=sym,
        tick=tick,
        freshness=QuoteFreshness.LIVE if fresh else QuoteFreshness.STALE,
        age_seconds=age,
        spread_points=spread / sym.point if sym.point > 0 else 0.0,
    )


def _tick(*, bid: float, ask: float, age: float = 1.0) -> Tick:
    return Tick(
        symbol=BROKER,
        bid=bid,
        ask=ask,
        last=ask,
        volume=1.0,
        timestamp=_NOW - timedelta(seconds=age),
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
    setup: CanonicalTradeSetup | None = None,
    candidate: Any | None = None,
    market: DemoMarketSnapshot | None = None,
    transport: FakeMT5ExecutionTransport | None = None,
    settings: Settings | None = None,
    state_name: str = "state.json",
) -> Any:
    cfg = settings or _settings(tmp_path)
    store = require_durable_setup_store(cfg)
    setup = setup or _setup()
    candidate = candidate or _candidate(setup)
    transport = transport or _filled_transport(
        volume=float(candidate.proposed_volume or 0.01)
    )
    probe = StaticDemoBrokerProbe(
        identity=_identity(),
        market=market or _market(),
    )
    return run_candidate_demo_execution_smoke(
        symbol=SYMBOL,
        execute=True,
        confirm=CONFIRM_PHRASE,
        settings=cfg,
        probe=probe,
        transport=transport,
        candidate=candidate,
        setup=setup,
        timeframe_status={"M15": "LIVE", "H1": "LIVE", "H4": "LIVE", "D1": "LIVE"},
        real_broker_submission=False,
        state_path=tmp_path / state_name,
        setup_store=store,
        clock=lambda: _NOW,
    )


def test_executable_price_long_ask_short_bid() -> None:
    tick = _tick(bid=2339.0, ask=2341.0)
    assert executable_price(side="LONG", tick=tick) == 2341.0
    assert executable_price(side="SHORT", tick=tick) == 2339.0


def test_1_long_latched_ask_outside_blocked(tmp_path: Path) -> None:
    setup = _setup(direction="LONG", state=SetupLifecycleState.ENTRY_ZONE)
    transport = _filled_transport()
    result = _run(
        tmp_path,
        setup=setup,
        market=_market(bid=2341.9, ask=2342.1),
        transport=transport,
    )
    assert len(transport.calls) == 0
    assert result.transport_send_count == 0
    assert result.candidate_precheck is not None
    assert CURRENT_PRICE_OUTSIDE_ENTRY_ZONE in result.candidate_precheck.reasons


def test_2_short_latched_bid_outside_blocked(tmp_path: Path) -> None:
    setup = _setup(direction="SHORT", state=SetupLifecycleState.ENTRY_ZONE)
    transport = _filled_transport()
    result = _run(
        tmp_path,
        setup=setup,
        market=_market(bid=2337.9, ask=2338.1),
        transport=transport,
    )
    assert len(transport.calls) == 0
    assert result.candidate_precheck is not None
    assert CURRENT_PRICE_OUTSIDE_ENTRY_ZONE in result.candidate_precheck.reasons


def test_3_long_ask_inside_may_proceed_fake_only(tmp_path: Path) -> None:
    setup = _setup(direction="LONG")
    transport = _filled_transport()
    result = _run(
        tmp_path,
        setup=setup,
        market=_market(bid=2340.9, ask=2341.1),
        transport=transport,
    )
    assert result.blocked is False
    assert len(transport.calls) == 1


def test_4_short_bid_inside_may_proceed_fake_only(tmp_path: Path) -> None:
    setup = _setup(direction="SHORT")
    transport = _filled_transport()
    result = _run(
        tmp_path,
        setup=setup,
        market=_market(bid=2340.0, ask=2340.2),
        transport=transport,
    )
    assert result.blocked is False
    assert len(transport.calls) == 1


def test_5_mid_inside_ask_outside_blocked_long(tmp_path: Path) -> None:
    setup = _setup(direction="LONG")
    bid, ask = 2341.9, 2342.1
    assert ZONE_LO <= (bid + ask) / 2 <= ZONE_HI
    assert ask > ZONE_HI
    transport = _filled_transport()
    result = _run(
        tmp_path, setup=setup, market=_market(bid=bid, ask=ask), transport=transport
    )
    assert len(transport.calls) == 0
    assert result.candidate_precheck is not None
    assert CURRENT_PRICE_OUTSIDE_ENTRY_ZONE in result.candidate_precheck.reasons


def test_6_mid_inside_bid_outside_blocked_short(tmp_path: Path) -> None:
    setup = _setup(direction="SHORT")
    bid, ask = 2337.9, 2338.1
    assert ZONE_LO <= (bid + ask) / 2 <= ZONE_HI
    assert bid < ZONE_LO
    transport = _filled_transport()
    result = _run(
        tmp_path, setup=setup, market=_market(bid=bid, ask=ask), transport=transport
    )
    assert len(transport.calls) == 0
    assert result.candidate_precheck is not None
    assert CURRENT_PRICE_OUTSIDE_ENTRY_ZONE in result.candidate_precheck.reasons


def test_7_stale_quote_blocked(tmp_path: Path) -> None:
    setup = _setup()
    transport = _filled_transport()
    result = _run(
        tmp_path,
        setup=setup,
        market=_market(bid=2340.9, ask=2341.1, age=60.0, fresh=False),
        transport=transport,
    )
    assert len(transport.calls) == 0
    assert result.candidate_precheck is not None
    assert "STALE_QUOTE" in result.candidate_precheck.reasons


def test_8_non_finite_quote_blocked_zero_submissions(tmp_path: Path) -> None:
    setup = _setup()
    for bid, ask in ((float("nan"), 2341.0), (2340.9, float("inf"))):
        transport = _filled_transport()
        result = _run(
            tmp_path,
            setup=setup,
            market=_market(bid=bid, ask=ask),
            transport=transport,
            state_name=f"nonfinite-{bid}.json",
        )
        assert result.blocked is True
        assert result.transport_send_count == 0
        assert len(transport.calls) == 0
        assert result.candidate_precheck is not None
        assert QUOTE_NON_FINITE in result.candidate_precheck.reasons


def test_9_missing_tick_blocked_zero_submissions(tmp_path: Path) -> None:
    setup = _setup()
    assert setup.state == SetupLifecycleState.ENTRY_ZONE
    transport = _filled_transport()
    result = _run(
        tmp_path,
        setup=setup,
        market=_market(include_tick=False),
        transport=transport,
    )
    assert result.blocked is True
    assert result.transport_send_count == 0
    assert len(transport.calls) == 0
    assert result.candidate_precheck is not None
    assert "QUOTE_UNAVAILABLE" in result.candidate_precheck.reasons


class _AccountOnlyProbe:
    """Production permission snapshot + static market. No order_send."""

    def __init__(self, client: Any, market: DemoMarketSnapshot) -> None:
        self._reader = ReadOnlyMt5DemoProbe(client)
        self._market = market

    def fetch_account(self) -> DemoIdentitySnapshot:
        return self._reader.fetch_account()

    def fetch_market(self, broker_symbol: str) -> DemoMarketSnapshot:
        del broker_symbol
        return self._market

    def list_positions(self, broker_symbol: str) -> tuple[dict[str, Any], ...]:
        del broker_symbol
        return ()


def _raw_account(*, trade_allowed: bool | None) -> SimpleNamespace:
    payload: dict[str, object] = {
        "login": 12345678,
        "balance": 10_000.0,
        "equity": 10_000.0,
        "margin": 0.0,
        "margin_free": 10_000.0,
        "currency": "USD",
        "leverage": 500,
        "server": "Exness-MT5Trial",
        "trade_mode": 0,
    }
    if trade_allowed is not None:
        payload["trade_allowed"] = trade_allowed
    return SimpleNamespace(**payload)


def _permission_client(
    *,
    trade_allowed: bool | None,
    terminal: SimpleNamespace | None,
    terminal_error: BaseException | None,
) -> Any:
    class _Client:
        def account_info(self) -> SimpleNamespace:
            return _raw_account(trade_allowed=trade_allowed)

        def terminal_info(self) -> SimpleNamespace | None:
            if terminal_error is not None:
                raise terminal_error
            return terminal

    return _Client()


def test_16_unverified_trade_permission_blocked_zero_submissions(tmp_path: Path) -> None:
    """Missing account field or unreadable terminal_info must not authorize send."""
    setup = _setup()
    cases: tuple[tuple[str, bool | None, SimpleNamespace | None, BaseException | None], ...] = (
        ("missing-field", None, None, RuntimeError("terminal_info unreadable")),
        ("unreadable-terminal", True, None, RuntimeError("terminal_info unreadable")),
        ("terminal-none", True, None, None),
    )
    for name, account_allowed, terminal, terminal_error in cases:
        transport = _filled_transport()
        cfg = _settings(tmp_path)
        store = require_durable_setup_store(cfg)
        candidate = _candidate(setup)
        result = run_candidate_demo_execution_smoke(
            symbol=SYMBOL,
            execute=True,
            confirm=CONFIRM_PHRASE,
            settings=cfg,
            probe=_AccountOnlyProbe(
                _permission_client(
                    trade_allowed=account_allowed,
                    terminal=terminal,
                    terminal_error=terminal_error,
                ),
                _market(),
            ),
            transport=transport,
            candidate=candidate,
            setup=setup,
            timeframe_status={"M15": "LIVE", "H1": "LIVE", "H4": "LIVE", "D1": "LIVE"},
            real_broker_submission=False,
            state_path=tmp_path / f"{name}.json",
            setup_store=store,
            clock=lambda: _NOW,
        )
        assert result.blocked is True, name
        assert result.transport_send_count == 0, name
        assert len(transport.calls) == 0, name
        assert result.enablement is not None, name
        assert result.enablement.allowed is False, name
        assert any(
            DemoGateName.TERMINAL_TRADE_PERMISSION.value in reason
            for reason in result.enablement.blocking_reasons
        ), name


def test_10_frozen_geometry_unchanged_after_revalidation(tmp_path: Path) -> None:
    setup = _setup()
    before = (
        setup.entry_zone_low,
        setup.entry_zone_high,
        setup.entry_price,
        setup.stop_loss,
    )
    transport = _filled_transport()
    _run(
        tmp_path,
        setup=setup,
        market=_market(bid=2341.9, ask=2342.1),
        transport=transport,
    )
    assert (
        setup.entry_zone_low,
        setup.entry_zone_high,
        setup.entry_price,
        setup.stop_loss,
    ) == before
    assert not math.isclose(setup.entry_zone_high, 2345.0)


def test_11_duplicate_consume_idempotent(tmp_path: Path) -> None:
    setup = _setup()
    transport = _filled_transport()
    r1 = _run(tmp_path, setup=setup, transport=transport, state_name="dup.json")
    r2 = _run(tmp_path, setup=setup, transport=transport, state_name="dup.json")
    assert r1.transport_send_count == 1
    assert len(transport.calls) == 1
    assert r2.transport_send_count == 0


def test_12_intent_state_path_survives_resolve() -> None:
    path = resolve_auto_demo_state_path()
    assert path.name == ".auto_demo_execution_state.json"
    assert path.is_absolute()


def test_13_snapshot_facts_not_hardcoded_true() -> None:
    class _Provider:
        def get_account_info(self) -> None:
            return None

        def get_tick(self, symbol: str | None = None) -> Tick | None:
            del symbol
            return None

    facts = read_auto_demo_runtime_facts(_Provider(), _settings(Path(".")), now=_NOW)
    assert facts.trade_allowed is None
    assert facts.quote_fresh is None


def test_14_execution_mode_live_fail_closed(tmp_path: Path) -> None:
    from exness_bot.controlled_demo.enablement import DemoPreflightContext
    from exness_bot.execution.auto_demo.enablement import evaluate_auto_demo_enablement

    cfg = _settings(tmp_path, EXECUTION_MODE="live", AUTO_DEMO_EXECUTION_ENABLED=True)
    result = evaluate_auto_demo_enablement(
        DemoPreflightContext(
            settings=cfg,
            symbol_info=_complete_symbol(),
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
    assert result.allowed is False
    assert any("EXECUTION_MODE" in r for r in result.blocking_reasons)


def test_15_latched_but_current_outside_reason() -> None:
    setup = _setup(state=SetupLifecycleState.ENTRY_ZONE)
    cand = _candidate(setup)
    tick = _tick(bid=2400.0, ask=2400.2)
    reasons = revalidate_candidate_market(
        candidate=cand,
        setup=setup,
        tick=tick,
        quote=_complete_symbol(bid=2400.0, ask=2400.2),
        max_spread_points=50,
        now=_NOW,
    )
    assert CURRENT_PRICE_OUTSIDE_ENTRY_ZONE in reasons
    assert setup.state == SetupLifecycleState.ENTRY_ZONE
