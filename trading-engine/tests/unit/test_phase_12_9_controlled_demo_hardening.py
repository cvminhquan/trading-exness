"""Phase 12.9 — Controlled DEMO execution path hardening.

Fake transport only — never real order_send / --execute.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.broker.mt5.execution_transport import (
    FakeMT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.identity import (
    DemoIdentitySnapshot,
    DemoMarketSnapshot,
    StaticDemoBrokerProbe,
)
from exness_bot.controlled_demo.intent_factory import (
    CONTROLLED_DEMO_TEST_VOLUME,
    CONTROLLED_STRATEGY_ID,
    build_controlled_demo_intent,
    build_controlled_demo_plan,
    resolve_controlled_demo_volume,
)
from exness_bot.controlled_demo.oneshot_transport import OneShotExecutionTransport
from exness_bot.controlled_demo.smoke import CONFIRM_PHRASE, ControlledDemoSmoke
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.models import AccountInfo, Tick
from exness_bot.paper_execution.contract import AckStatus, IntentLifecycle
from exness_bot.risk.manager import RiskManager
from exness_bot.risk.models import RiskState
from tests.fixtures.risk_data import make_account, make_buy_signal, make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"


def _at() -> datetime:
    return datetime(2026, 9, 7, 10, 0, tzinfo=UTC)


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
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
        "MAX_SPREAD_POINTS": 260,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _account(*, equity: float = 10_000.0, trade_mode: str = "demo") -> AccountInfo:
    return AccountInfo(
        login=12345678,
        balance=equity,
        equity=equity,
        margin=0.0,
        free_margin=equity,
        currency="USD",
        leverage=500,
        server="Exness-MT5Trial",
        trade_mode=trade_mode,
    )


def _identity(*, equity: float = 10_000.0, trade_mode: str = "demo") -> DemoIdentitySnapshot:
    account = _account(equity=equity, trade_mode=trade_mode)
    return DemoIdentitySnapshot(
        account=account,
        trade_allowed=True,
        currency="USD",
        server=account.server,
        login=account.login,
        trade_mode=trade_mode,
        terminal_trade_allowed=True,
    )


def _market(*, age_seconds: float = 1.0, fresh: bool = True) -> DemoMarketSnapshot:
    symbol = make_xauusd_symbol()
    tick = Tick(
        symbol=BROKER,
        bid=symbol.bid,
        ask=symbol.ask,
        last=symbol.ask,
        volume=1.0,
        timestamp=_at() - timedelta(seconds=age_seconds),
    )
    return DemoMarketSnapshot(
        symbol=symbol,
        tick=tick,
        freshness=QuoteFreshness.LIVE if fresh else QuoteFreshness.STALE,
        age_seconds=age_seconds,
        spread_points=20.0,
    )


def _probe(**kwargs: object) -> StaticDemoBrokerProbe:
    return StaticDemoBrokerProbe(
        identity=kwargs.get("identity", _identity()),  # type: ignore[arg-type]
        market=kwargs.get("market", _market()),  # type: ignore[arg-type]
        positions=kwargs.get("positions", ()),  # type: ignore[arg-type]
    )


def _filled_transport() -> FakeMT5ExecutionTransport:
    return FakeMT5ExecutionTransport(
        default=MT5TransportResult(
            outcome=TransportOutcome.FILLED,
            price=2350.3,
            volume=CONTROLLED_DEMO_TEST_VOLUME,
        )
    )


class TestControlledDemoSizing:
    def test_explicit_001_lot(self) -> None:
        intent = build_controlled_demo_intent(
            symbol=make_xauusd_symbol(),
            canonical_symbol=SYMBOL,
            timeframe="M15",
            now=_at(),
            max_position_lots=1.0,
        )
        assert intent.requested_quantity == CONTROLLED_DEMO_TEST_VOLUME
        assert intent.requested_quantity == 0.01
        assert intent.strategy == CONTROLLED_STRATEGY_ID

    def test_001_satisfies_broker_min_volume(self) -> None:
        symbol = make_xauusd_symbol()
        assert symbol.volume_min == 0.01
        vol = resolve_controlled_demo_volume(symbol=symbol, max_position_lots=1.0)
        assert vol >= symbol.volume_min

    def test_001_satisfies_broker_volume_step(self) -> None:
        symbol = make_xauusd_symbol()
        vol = resolve_controlled_demo_volume(symbol=symbol, max_position_lots=1.0)
        steps = round(vol / symbol.volume_step)
        assert abs(steps * symbol.volume_step - vol) <= 1e-9

    def test_001_does_not_exceed_max_position_lots(self) -> None:
        vol = resolve_controlled_demo_volume(
            symbol=make_xauusd_symbol(),
            max_position_lots=1.0,
        )
        assert vol <= 1.0

    def test_large_equity_still_uses_001_not_strategy_size(self) -> None:
        """Regression: RiskManager would size ~38.99 lots on large equity + tight ATR."""
        plan = build_controlled_demo_plan(
            symbol=make_xauusd_symbol(),
            canonical_symbol=SYMBOL,
            timeframe="M15",
            now=_at(),
            max_position_lots=1.0,
        )
        assert plan.requested_volume == 0.01

    def test_rejects_volume_above_max_position_lots_ceiling(self) -> None:
        try:
            resolve_controlled_demo_volume(
                symbol=make_xauusd_symbol(),
                max_position_lots=0.005,
            )
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "MAX_POSITION_LOTS" in str(exc)

    def test_rejects_misaligned_non_canonical_volume(self) -> None:
        try:
            resolve_controlled_demo_volume(
                symbol=make_xauusd_symbol(),
                max_position_lots=1.0,
                requested=0.02,
            )
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "exactly" in str(exc)

    def test_smoke_result_volume_is_001(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(identity=_identity(equity=58_485.0)),
            transport=_filled_transport(),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.submitted is True
        assert result.intent is not None
        assert result.intent.requested_quantity == 0.01


class TestRiskManagerUnchanged:
    def test_normal_risk_manager_sizing_unchanged(self) -> None:
        mgr = RiskManager(_settings(RISK_PER_TRADE_PCT=0.5, MAX_POSITION_LOTS=100.0))
        decision = mgr.assess(
            make_buy_signal(atr_14=2.0),
            make_account(equity=10_000.0),
            make_xauusd_symbol(),
            [],
            RiskState(day_start_equity=10_000.0, peak_equity=10_000.0),
        )
        assert hasattr(decision, "volume")
        assert decision.volume > 0.01  # type: ignore[union-attr]

    def test_oversized_strategy_position_still_rejected(self) -> None:
        mgr = RiskManager(_settings(MAX_POSITION_LOTS=1.0, RISK_PER_TRADE_PCT=0.5))
        # Tight ATR + large equity → volume >> 1.0 (mirrors prior 38.99 failure mode)
        decision = mgr.assess(
            make_buy_signal(atr_14=0.05),
            make_account(equity=58_485.0),
            make_xauusd_symbol(),
            [],
            RiskState(day_start_equity=58_485.0, peak_equity=58_485.0),
        )
        assert hasattr(decision, "reason")
        assert "exceeds maximum allowed" in decision.reason  # type: ignore[union-attr]

    def test_intent_factory_does_not_import_risk_manager(self) -> None:
        source = Path(
            SRC / "controlled_demo" / "intent_factory.py"
        ).read_text(encoding="utf-8")
        assert "RiskManager" not in source
        assert "calculate_position_size" not in source


class TestUnifiedGatedPath:
    def test_smoke_uses_gated_mt5_execution_port(self, tmp_path: Path) -> None:
        source = inspect.getsource(ControlledDemoSmoke.run)
        assert "build_gated_mt5_execution_port" in source
        assert "ExecutionOrchestrator" in source
        assert "GatedMT5ExecutionPort" in source or "gated" in source
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=_filled_transport(),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.used_gated_port is True
        assert result.submitted is True

    def test_no_duplicate_custom_enablement_bypass(self) -> None:
        source = inspect.getsource(ControlledDemoSmoke.run)
        assert "_demo_enablement" not in source
        assert "LiveEnablementResult" not in source


class TestSafetyGatesViaSmoke:
    def test_kill_switch_blocks(self, tmp_path: Path) -> None:
        transport = _filled_transport()
        result = ControlledDemoSmoke(
            settings=_settings(LIVE_KILL_SWITCH=True),
            probe=_probe(),
            transport=transport,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert result.submitted is False
        assert transport.calls == []

    def test_non_demo_account_blocks(self, tmp_path: Path) -> None:
        transport = _filled_transport()
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(identity=_identity(trade_mode="real")),
            transport=transport,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert result.submitted is False
        assert transport.calls == []

    def test_account_not_allowlisted_blocks(self, tmp_path: Path) -> None:
        transport = _filled_transport()
        result = ControlledDemoSmoke(
            settings=_settings(DEMO_ACCOUNT_ALLOWLIST="99999999"),
            probe=_probe(),
            transport=transport,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert transport.calls == []

    def test_approval_missing_blocks(self, tmp_path: Path) -> None:
        transport = _filled_transport()
        result = ControlledDemoSmoke(
            settings=_settings(LIVE_DEMO_APPROVAL=False),
            probe=_probe(),
            transport=transport,
            approval=OneShotApproval(active=False),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert transport.calls == []

    def test_stale_quote_blocks(self, tmp_path: Path) -> None:
        transport = _filled_transport()
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(market=_market(age_seconds=60.0, fresh=False)),
            transport=transport,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert transport.calls == []

    def test_trade_permission_false_blocks(self, tmp_path: Path) -> None:
        transport = _filled_transport()
        identity = _identity()
        identity = DemoIdentitySnapshot(
            account=identity.account,
            trade_allowed=False,
            currency=identity.currency,
            server=identity.server,
            login=identity.login,
            trade_mode=identity.trade_mode,
            terminal_trade_allowed=False,
        )
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(identity=identity),
            transport=transport,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert transport.calls == []

    def test_invalid_symbol_blocks(self, tmp_path: Path) -> None:
        transport = _filled_transport()
        result = ControlledDemoSmoke(
            settings=_settings(LIVE_SYMBOL_MAP="", MT5_SYMBOL=""),
            probe=_probe(),
            transport=transport,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert transport.calls == []


class TestOneShotAndLifecycle:
    def test_duplicate_execution_blocks(self, tmp_path: Path) -> None:
        first = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=_filled_transport(),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert first.submitted is True
        second = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=_filled_transport(),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state2.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert second.blocked is True
        assert second.submitted is False

    def test_unresolved_unknown_blocks_new_execution(self, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        first = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN)
            ),
            approval=OneShotApproval(active=True),
            state_path=state,
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert first.lifecycle is IntentLifecycle.UNKNOWN
        # Same ledger blocks; also unresolved intent in same state blocks orchestrator
        second = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=_filled_transport(),
            approval=OneShotApproval(active=True),
            state_path=state,
            ledger_path=tmp_path / "ledger2.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert second.submitted is False
        assert second.blocked is True

    def test_inflight_persisted_before_transport_send(self, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        events: list[str] = []

        class _Tracking(FakeMT5ExecutionTransport):
            def send(self, request):  # type: ignore[no-untyped-def]
                from exness_bot.paper_execution.state import FilePaperStateStore

                snap = FilePaperStateStore(state).load()
                assert snap.intents, "intent must exist before transport send"
                assert snap.intents[0].lifecycle is IntentLifecycle.IN_FLIGHT
                events.append("send")
                return super().send(request)

        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=_Tracking(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED,
                    price=2350.3,
                    volume=0.01,
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=state,
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert events == ["send"]
        assert result.submitted is True

    def test_transport_send_count_never_exceeds_one(self, tmp_path: Path) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN)
        )
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=transport,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.transport_send_count == 1
        assert len(transport.calls) == 1
        # Process-local second attempt via new smoke still ledger-blocked
        again = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=_filled_transport(),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state2.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert again.submitted is False
        assert len(transport.calls) == 1

    def test_broker_rejection_becomes_rejected(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.REJECTED,
                    comment="no money",
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.ack is not None
        assert result.ack.status is AckStatus.REJECTED
        assert result.lifecycle is IntentLifecycle.REJECTED

    def test_ambiguous_broker_result_becomes_unknown(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN)
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.lifecycle is IntentLifecycle.UNKNOWN

    def test_unknown_never_automatically_resubmits(self, tmp_path: Path) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN)
        )
        oneshot = OneShotExecutionTransport(transport)
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=oneshot,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.transport_send_count >= 1
        assert len(transport.calls) == 1
        blocked = oneshot.send({"action": 1})
        assert blocked.outcome is TransportOutcome.UNKNOWN
        assert "ONE_SHOT_VIOLATION" in (blocked.comment or "")
        assert len(transport.calls) == 1

    def test_strategy_loop_not_invoked(self) -> None:
        source = inspect.getsource(ControlledDemoSmoke.run)
        assert "while True" not in source
        assert "SignalEngine" not in source
        assert "strategy_loop" not in source
        root = SRC / "controlled_demo"
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "signal_engine" not in text


class TestStaticSafetyAudit:
    def test_order_send_only_in_execution_transport(self) -> None:
        hits: list[str] = []
        for path in (SRC / "broker" / "mt5").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = ""
                    if isinstance(func, ast.Attribute):
                        name = func.attr
                    elif isinstance(func, ast.Name):
                        name = func.id
                    if name == "order_send":
                        hits.append(str(path.relative_to(SRC)))
        phase12 = [h for h in hits if "execution_transport.py" in h]
        assert phase12, "expected LiveMT5ExecutionTransport.order_send"
        legacy = [h for h in hits if h not in phase12]
        # Legacy may exist but must stay isolated
        for path in legacy:
            assert "adapter" in path or "trading_client" in path

    def test_safe_defaults_unchanged(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.live_kill_switch is True
        assert s.live_demo_approval is False
        assert s.execution_mode.value == "paper" or str(s.execution_mode) == "paper"
        assert s.allow_legacy_run is False

    def test_smoke_cli_mentions_gated_path(self) -> None:
        cli = (SRC / "cli.py").read_text(encoding="utf-8")
        assert "demo-execution-smoke" in cli
        assert "GatedMT5ExecutionPort" in cli
