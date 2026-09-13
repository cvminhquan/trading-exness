"""Phase 12.10 — DEMO execution evidence & reconciliation (Fake only).

No real order_send. Proves lifecycle mapping, one-shot, and failure paths.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.broker.mt5.execution_transport import (
    FakeMT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.broker.mt5.executor import parse_symbol_map, resolve_broker_symbol
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.enablement import (
    DemoGateName,
    DemoPreflightContext,
    evaluate_demo_controlled_enablement,
)
from exness_bot.controlled_demo.identity import (
    DemoIdentitySnapshot,
    DemoMarketSnapshot,
    StaticDemoBrokerProbe,
)
from exness_bot.controlled_demo.intent_factory import (
    CONTROLLED_DEMO_TEST_VOLUME,
    build_controlled_demo_plan,
)
from exness_bot.controlled_demo.smoke import CONFIRM_PHRASE, ControlledDemoSmoke
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import AccountInfo, Tick
from exness_bot.execution.guard import default_orchestration_guards
from exness_bot.execution.mt5.factory import build_gated_mt5_execution_port
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.plan import ExecutionPlan
from exness_bot.execution.result import OrchestrationOutcome
from exness_bot.paper_execution.contract import AckStatus, IntentLifecycle
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from exness_bot.paper_execution.models import PaperSnapshot
from tests.fixtures.risk_data import make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"


def _at() -> datetime:
    return datetime(2026, 9, 7, 16, 0, tzinfo=UTC)


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "EXECUTION_MODE": "paper",
        "TRADING_ENV": "demo",
        "TRADING_MODE": "demo",
        "LIVE_KILL_SWITCH": False,
        "LIVE_DEMO_APPROVAL": True,
        "ALLOW_LEGACY_RUN": False,
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


def _account() -> AccountInfo:
    return AccountInfo(
        login=12345678,
        balance=10_000.0,
        equity=10_000.0,
        margin=0.0,
        free_margin=10_000.0,
        currency="USD",
        leverage=500,
        server="Exness-MT5Trial",
        trade_mode="demo",
    )


def _identity() -> DemoIdentitySnapshot:
    account = _account()
    return DemoIdentitySnapshot(
        account=account,
        trade_allowed=True,
        currency="USD",
        server=account.server,
        login=account.login,
        trade_mode="demo",
        terminal_trade_allowed=True,
    )


def _market(*, spread: int = 20, fresh: bool = True) -> DemoMarketSnapshot:
    symbol = make_xauusd_symbol(spread=spread)
    tick = Tick(
        symbol=BROKER,
        bid=symbol.bid,
        ask=symbol.ask,
        last=symbol.ask,
        volume=1.0,
        timestamp=_at() - timedelta(seconds=1.0),
    )
    return DemoMarketSnapshot(
        symbol=symbol,
        tick=tick,
        freshness=QuoteFreshness.LIVE if fresh else QuoteFreshness.STALE,
        age_seconds=1.0 if fresh else 60.0,
        spread_points=float(spread),
    )


def _probe(**kwargs: object) -> StaticDemoBrokerProbe:
    return StaticDemoBrokerProbe(
        identity=kwargs.get("identity", _identity()),  # type: ignore[arg-type]
        market=kwargs.get("market", _market()),  # type: ignore[arg-type]
        positions=kwargs.get("positions", ()),  # type: ignore[arg-type]
    )


def _gate(result, name: DemoGateName):
    return next(g for g in result.gates if g.gate == name)


class TestDeterministicDemoIntent:
    def test_buy_001_xauusd_maps_to_xauusdm(self) -> None:
        settings = _settings()
        plan = build_controlled_demo_plan(
            symbol=make_xauusd_symbol(),
            canonical_symbol=SYMBOL,
            timeframe="M15",
            now=_at(),
            max_position_lots=settings.max_position_lots,
            side=SignalDirection.LONG,
        )
        assert plan.side is SignalDirection.LONG
        assert plan.requested_volume == CONTROLLED_DEMO_TEST_VOLUME
        assert plan.requested_volume == 0.01
        assert plan.symbol == SYMBOL
        mapping = parse_symbol_map(
            settings.live_symbol_map,
            fallback_canonical=settings.symbol,
            fallback_broker=settings.mt5_symbol,
        )
        assert resolve_broker_symbol(SYMBOL, mapping) == BROKER
        assert plan.requested_volume <= settings.max_position_lots

    def test_001_broker_valid_and_spread_ok(self) -> None:
        symbol = make_xauusd_symbol(spread=20)
        settings = _settings(MAX_SPREAD_POINTS=260)
        ctx = DemoPreflightContext(
            settings=settings,
            symbol_info=symbol,
            account_trade_mode="demo",
            trade_allowed=True,
            terminal_trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert result.allowed is True
        assert _gate(result, DemoGateName.SPREAD_LIMIT).allowed is True
        assert _gate(result, DemoGateName.ACCOUNT_TRADE_MODE).allowed is True
        assert _gate(result, DemoGateName.BROKER_IDENTITY).allowed is True
        assert symbol.volume_min <= 0.01 <= symbol.volume_max

    def test_spread_above_limit_blocks(self) -> None:
        symbol = make_xauusd_symbol(spread=500)
        ctx = DemoPreflightContext(
            settings=_settings(MAX_SPREAD_POINTS=260),
            symbol_info=symbol,
            account_trade_mode="demo",
            trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert result.allowed is False
        assert _gate(result, DemoGateName.SPREAD_LIMIT).allowed is False


class TestPreSubmitPersistence:
    def test_inflight_fields_sufficient_for_reconcile(self, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        captured: dict[str, object] = {}

        class _Tracking(FakeMT5ExecutionTransport):
            def send(self, request):  # type: ignore[no-untyped-def]
                from exness_bot.paper_execution.state import FilePaperStateStore

                snap = FilePaperStateStore(state).load()
                record = snap.intents[0]
                captured.update(
                    {
                        "intent_id": record.intent_id,
                        "idempotency_key": record.idempotency_key,
                        "symbol": record.symbol,
                        "side": record.side,
                        "volume": record.requested_quantity,
                        "created_at": record.created_at,
                        "lifecycle": record.lifecycle,
                    }
                )
                assert record.lifecycle is IntentLifecycle.IN_FLIGHT
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
        assert result.submitted is True
        assert captured["volume"] == 0.01
        assert captured["symbol"] == SYMBOL
        assert captured["side"] in {SignalDirection.LONG, SignalDirection.LONG.value, "LONG"}
        assert captured["intent_id"]
        assert captured["idempotency_key"]
        assert captured["created_at"] is not None
        assert captured["lifecycle"] is IntentLifecycle.IN_FLIGHT


class TestBrokerResultMappingAndFailures:
    def test_a_broker_rejected(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.REJECTED,
                    comment="reject",
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.lifecycle is IntentLifecycle.REJECTED
        assert result.ack is not None
        assert result.ack.status is AckStatus.REJECTED

    def test_b_ambiguous_becomes_unknown(self, tmp_path: Path) -> None:
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

    def test_c_persistence_failure_after_side_effect_unknown(self) -> None:
        class _FailFilled(SnapshotIntentStore):
            def mark_filled(self, intent_id, evidence, *, now):  # type: ignore[no-untyped-def]
                raise RuntimeError("finalize_failed")

            def mark_unknown(self, intent_id, reason, *, now, detail=None):  # type: ignore[no-untyped-def]
                return super().mark_unknown(intent_id, reason, now=now, detail=detail)

        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = _FailFilled(paper, persist=lambda: None)
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        snap = GatedExecutionSnapshot(
            account_trade_mode="demo",
            trade_allowed=True,
            terminal_trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        port = build_gated_mt5_execution_port(
            _settings(),
            transport=transport,
            snapshot_provider=lambda: snap,
        )
        orch = ExecutionOrchestrator(
            store=store,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: "fin-12-10",
        )
        plan = ExecutionPlan(
            plan_id="plan-fin",
            signal_id="sig-fin",
            strategy_id="controlled_demo_smoke_v1",
            symbol=SYMBOL,
            timeframe="M15",
            side=SignalDirection.LONG,
            requested_volume=0.01,
            stop_loss=2340.0,
            take_profit=2370.0,
            signal_timestamp=_at(),
            decision_timestamp=_at(),
            metadata={"idempotency_key": "idem-fin-12-10"},
        )
        first = orch.execute(plan, quote=make_xauusd_symbol())
        assert first.outcome == OrchestrationOutcome.UNKNOWN
        assert len(transport.calls) == 1
        second = orch.execute(plan, quote=make_xauusd_symbol())
        assert second.port_calls == 0
        assert len(transport.calls) == 1

    def test_d_restart_unresolved_intent_blocks(self, tmp_path: Path) -> None:
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
        second = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=state,
            ledger_path=tmp_path / "ledger-b.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert second.submitted is False
        assert second.blocked is True

    def test_e_duplicate_plan_blocks(self) -> None:
        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = SnapshotIntentStore(paper, persist=lambda: None)
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        snap = GatedExecutionSnapshot(
            account_trade_mode="demo",
            trade_allowed=True,
            terminal_trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        port = build_gated_mt5_execution_port(
            _settings(),
            transport=transport,
            snapshot_provider=lambda: snap,
        )
        orch = ExecutionOrchestrator(
            store=store,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: f"i-{p.signal_id}",
        )
        plan = ExecutionPlan(
            plan_id="plan-dup",
            signal_id="sig-dup",
            strategy_id="controlled_demo_smoke_v1",
            symbol=SYMBOL,
            timeframe="M15",
            side=SignalDirection.LONG,
            requested_volume=0.01,
            stop_loss=2340.0,
            take_profit=2370.0,
            signal_timestamp=_at(),
            decision_timestamp=_at(),
            metadata={"idempotency_key": "idem-dup-12-10"},
        )
        first = orch.execute(plan, quote=make_xauusd_symbol())
        second = orch.execute(plan, quote=make_xauusd_symbol())
        assert first.port_calls == 1
        assert second.port_calls == 0
        assert len(transport.calls) == 1

    def test_f_second_smoke_submission_blocks(self, tmp_path: Path) -> None:
        first = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "a.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert first.submitted is True
        assert first.transport_send_count == 1
        second = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "b.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert second.blocked is True
        assert second.submitted is False


class TestOneShotAndIsolation:
    def test_transport_send_count_le_one(self, tmp_path: Path) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
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
        assert result.transport_send_count <= 1
        assert len(transport.calls) == 1

    def test_no_strategy_loop_in_smoke(self) -> None:
        source = inspect.getsource(ControlledDemoSmoke.run)
        assert "while True" not in source
        assert "SignalEngine" not in source

    def test_reconcile_query_is_read_only(self) -> None:
        path = SRC / "broker" / "mt5" / "execution_query.py"
        text = path.read_text(encoding="utf-8")
        assert "order_send" not in text
        assert "ReadOnlyMt5BrokerExecutionQuery" in text

    def test_safe_defaults(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.live_kill_switch is True
        assert s.live_demo_approval is False
        assert str(s.execution_mode) == "paper"
        assert s.allow_legacy_run is False
