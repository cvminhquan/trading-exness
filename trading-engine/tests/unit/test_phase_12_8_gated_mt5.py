"""Phase 12.8 — Gated MT5 ExecutionPort. Fake transport only — no real order_send."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path

from exness_bot.backtest.config import BacktestConfig
from exness_bot.broker.mt5.execution_transport import (
    FakeMT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.enablement import DemoGateName
from exness_bot.domain.enums import SignalDirection
from exness_bot.execution.guard import default_orchestration_guards
from exness_bot.execution.mt5.factory import build_gated_mt5_execution_port
from exness_bot.execution.mt5.gated_port import GatedMT5ExecutionPort
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot
from exness_bot.execution.orchestrator import ExecutionOrchestrator
from exness_bot.execution.plan import ExecutionPlan
from exness_bot.execution.result import OrchestrationOutcome
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionIntent,
    IntentLifecycle,
)
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from exness_bot.paper_execution.models import PaperSnapshot
from exness_bot.paper_execution.state import FilePaperStateStore
from tests.fixtures.risk_data import make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"


def _at() -> datetime:
    return datetime(2026, 9, 4, 14, 0, tzinfo=UTC)


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
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _snapshot(**kwargs: object) -> GatedExecutionSnapshot:
    base: dict[str, object] = {
        "account_trade_mode": "demo",
        "trade_allowed": True,
        "terminal_trade_allowed": True,
        "broker_login": 12345678,
        "broker_server": "Exness-MT5Trial",
        "quote_fresh": True,
        "quote_age_seconds": 1.0,
        "approval": OneShotApproval(active=True),
        "prior_submission_count": 0,
    }
    base.update(kwargs)
    return GatedExecutionSnapshot(**base)  # type: ignore[arg-type]


def _port(
    transport: FakeMT5ExecutionTransport,
    *,
    settings: Settings | None = None,
    snapshot: GatedExecutionSnapshot | None = None,
) -> GatedMT5ExecutionPort:
    snap = snapshot or _snapshot()
    return build_gated_mt5_execution_port(
        settings or _settings(),
        transport=transport,
        snapshot_provider=lambda: snap,
        wrap_oneshot=True,
    )


def _intent(**kwargs: object) -> ExecutionIntent:
    base: dict[str, object] = {
        "intent_id": "i1",
        "idempotency_key": "k1",
        "symbol": SYMBOL,
        "timeframe": "M15",
        "strategy": "ema_rsi_atr_v1",
        "side": SignalDirection.LONG,
        "requested_quantity": 0.01,
        "stop_loss": 2340.0,
        "take_profit": 2370.0,
        "created_at": _at(),
        "source": "phase_12_8",
    }
    base.update(kwargs)
    return ExecutionIntent(**base)  # type: ignore[arg-type]


def _plan(signal_id: str = "sig-1") -> ExecutionPlan:
    return ExecutionPlan(
        plan_id=f"plan-{signal_id}",
        signal_id=signal_id,
        strategy_id="ema_rsi_atr_v1",
        symbol=SYMBOL,
        timeframe="M15",
        side=SignalDirection.LONG,
        requested_volume=0.01,
        stop_loss=2340.0,
        take_profit=2370.0,
        signal_timestamp=_at(),
        decision_timestamp=_at(),
        metadata={"idempotency_key": f"idem-{signal_id}"},
    )


def _store() -> SnapshotIntentStore:
    paper = PaperExecutor(
        PaperSnapshot.initial(10_000.0),
        config=BacktestConfig.from_settings(_settings()),
    )
    return SnapshotIntentStore(paper, persist=lambda: None)


class TestGateBlocks:
    def test_kill_switch_on_blocks(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        port = _port(transport, settings=_settings(LIVE_KILL_SWITCH=True))
        ack = port.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []
        assert port.executor_submit_count == 0

    def test_approval_off_blocks(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        port = _port(
            transport,
            settings=_settings(LIVE_DEMO_APPROVAL=False),
            snapshot=_snapshot(approval=OneShotApproval(active=False)),
        )
        ack = port.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []

    def test_non_demo_env_blocks(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        port = _port(transport, settings=_settings(TRADING_ENV="live"))
        ack = port.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []

    def test_empty_allowlist_blocks(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        port = _port(transport, settings=_settings(DEMO_ACCOUNT_ALLOWLIST=""))
        ack = port.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []

    def test_symbol_not_allowlisted_blocks(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        port = _port(transport)
        ack = port.submit(_intent(symbol="EURUSD"), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []

    def test_stale_quote_blocks(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        port = _port(
            transport,
            snapshot=_snapshot(quote_fresh=False, quote_age_seconds=99.0),
        )
        ack = port.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []
        assert port.last_enablement is not None
        gate = next(
            g
            for g in port.last_enablement.gates
            if g.gate is DemoGateName.QUOTE_FRESHNESS
        )
        assert gate.allowed is False

    def test_terminal_trade_false_blocks(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        port = _port(
            transport,
            snapshot=_snapshot(trade_allowed=False, terminal_trade_allowed=False),
        )
        ack = port.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []

    def test_valid_gates_allow_execution(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.3, volume=0.01, order_id="9"
            )
        )
        port = _port(transport)
        ack = port.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.FILLED
        assert len(transport.calls) == 1
        assert port.executor_submit_count == 1


class TestSideEffectProtection:
    def test_gate_failure_executor_not_called(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=1.0, volume=0.01
            )
        )
        port = _port(transport, settings=_settings(LIVE_KILL_SWITCH=True))
        port.submit(_intent(), quote=make_xauusd_symbol())
        assert port.executor.submit_count == 0
        assert transport.calls == []

    def test_in_flight_persist_fail_no_mt5(self) -> None:
        class _BoomStore(SnapshotIntentStore):
            def mark_in_flight(self, intent_id: str, *, now: datetime):  # type: ignore[no-untyped-def]
                raise RuntimeError("persist_in_flight_failed")

        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = _BoomStore(paper, persist=lambda: None)
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=1.0, volume=0.01
            )
        )
        port = _port(transport)
        orch = ExecutionOrchestrator(
            store=store,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: f"intent-{p.signal_id}",
        )
        result = orch.execute(_plan(), quote=make_xauusd_symbol())
        assert result.outcome == OrchestrationOutcome.ERROR
        assert transport.calls == []
        assert port.executor_submit_count == 0

    def test_presubmit_gate_blocks_transport(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=1.0, volume=0.01
            )
        )
        port = _port(transport, snapshot=_snapshot(account_trade_mode="live"))
        store = _store()
        orch = ExecutionOrchestrator(
            store=store,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: "intent-x",
        )
        result = orch.execute(_plan("x"), quote=make_xauusd_symbol())
        # Orchestrator may reach port; port rejects before transport
        assert transport.calls == []
        assert result.lifecycle in {
            IntentLifecycle.REJECTED,
            IntentLifecycle.UNKNOWN,
            None,
        } or result.outcome in {
            OrchestrationOutcome.REJECTED,
            OrchestrationOutcome.UNKNOWN,
            OrchestrationOutcome.BLOCKED,
            OrchestrationOutcome.ERROR,
        }


class TestIdempotencyUnknownRestart:
    def test_same_plan_one_port_call(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        port = _port(transport)
        store = _store()
        orch = ExecutionOrchestrator(
            store=store,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: f"intent-{p.signal_id}",
        )
        first = orch.execute(_plan("dup"), quote=make_xauusd_symbol())
        second = orch.execute(_plan("dup"), quote=make_xauusd_symbol())
        assert first.port_calls == 1
        assert second.port_calls == 0
        assert len(transport.calls) == 1

    def test_ambiguous_unknown_no_resubmit(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN, comment="amb")
        )
        port = _port(transport)
        store = _store()
        orch = ExecutionOrchestrator(
            store=store,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: "intent-u",
        )
        first = orch.execute(_plan("u"), quote=make_xauusd_symbol())
        assert first.lifecycle is IntentLifecycle.UNKNOWN
        assert len(transport.calls) == 1
        second = orch.execute(_plan("u"), quote=make_xauusd_symbol())
        assert second.port_calls == 0
        assert len(transport.calls) == 1
        # New different plan also blocked by unresolved UNKNOWN
        third = orch.execute(_plan("other"), quote=make_xauusd_symbol())
        assert third.outcome == OrchestrationOutcome.BLOCKED
        assert len(transport.calls) == 1

    def test_inflight_restart_unknown_no_resend(self, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = SnapshotIntentStore(
            paper, persist=lambda: FilePaperStateStore(state).save(paper.snapshot)
        )
        intent = _intent(intent_id="stuck", idempotency_key="idem-stuck")
        store.create_intent(intent, now=_at())
        store.mark_in_flight(intent.intent_id, now=_at())

        paper2 = PaperExecutor(
            FilePaperStateStore(state).load(),
            config=BacktestConfig.from_settings(_settings()),
        )
        store2 = SnapshotIntentStore(paper2, persist=lambda: None)
        recovered = store2.recover_in_flight_to_unknown(now=_at())
        assert recovered[0].lifecycle is IntentLifecycle.UNKNOWN
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=1.0, volume=0.01
            )
        )
        port = _port(transport)
        orch = ExecutionOrchestrator(
            store=store2,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store2),
        )
        # Same key → no submit
        plan = _plan("stuck")
        plan = ExecutionPlan(
            plan_id=plan.plan_id,
            signal_id=plan.signal_id,
            strategy_id=plan.strategy_id,
            symbol=plan.symbol,
            timeframe=plan.timeframe,
            side=plan.side,
            requested_volume=plan.requested_volume,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            signal_timestamp=plan.signal_timestamp,
            decision_timestamp=plan.decision_timestamp,
            metadata={"idempotency_key": "idem-stuck"},
        )
        result = orch.execute(plan, quote=make_xauusd_symbol())
        assert transport.calls == []
        assert result.port_calls == 0


class TestFailureInjection:
    def test_transport_reject(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.REJECTED, comment="rej")
        )
        port = _port(transport)
        ack = port.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert len(transport.calls) == 1

    def test_transport_exception_via_unknown_outcome(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN, comment="exc")
        )
        port = _port(transport)
        store = _store()
        orch = ExecutionOrchestrator(
            store=store,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: "ix",
        )
        result = orch.execute(_plan("ix"), quote=make_xauusd_symbol())
        assert result.lifecycle is IntentLifecycle.UNKNOWN
        assert len(transport.calls) == 1

    def test_finalize_fail_after_side_effect_no_resend(self) -> None:
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
        port = _port(transport)
        orch = ExecutionOrchestrator(
            store=store,
            port=port,
            clock=_at,
            guard=default_orchestration_guards(store),
            intent_id_factory=lambda p: "fin",
        )
        first = orch.execute(_plan("fin"), quote=make_xauusd_symbol())
        assert first.outcome == OrchestrationOutcome.UNKNOWN
        assert len(transport.calls) == 1
        second = orch.execute(_plan("fin"), quote=make_xauusd_symbol())
        assert len(transport.calls) == 1
        assert second.port_calls == 0


class TestBoundariesAndDefaults:
    def test_core_execution_modules_no_metatrader5(self) -> None:
        for name in (
            "plan.py",
            "orchestrator.py",
            "guard.py",
            "eligibility.py",
            "idempotency.py",
            "planning.py",
            "result.py",
            "spy.py",
        ):
            path = SRC / "execution" / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "MetaTrader5" not in alias.name
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "MetaTrader5" not in node.module
                    assert not node.module.startswith("exness_bot.broker.mt5")
            text = path.read_text(encoding="utf-8")
            assert ".order_send(" not in text

    def test_order_send_only_in_live_transport(self) -> None:
        transport_path = SRC / "broker" / "mt5" / "execution_transport.py"
        assert "order_send" in transport_path.read_text(encoding="utf-8")
        gated = (SRC / "execution" / "mt5" / "gated_port.py").read_text(encoding="utf-8")
        assert ".order_send(" not in gated

    def test_paper_factory_does_not_wire_gated_mt5(self) -> None:
        from exness_bot.paper_execution import factory

        source = inspect.getsource(factory.build_execution_service)
        # Docstring may mention gated port; body must not instantiate it
        body = source.split('"""', 2)[-1] if '"""' in source else source
        assert "GatedMT5ExecutionPort(" not in body
        assert "build_gated_mt5_execution_port(" not in body
        assert "LiveMT5ExecutionTransport" not in source
        assert "MT5Executor(" not in body

    def test_safe_defaults(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.live_kill_switch is True
        assert settings.live_demo_approval is False
        assert settings.execution_mode.value == "paper"
        assert settings.allow_legacy_run is False

    def test_legacy_run_blocks_factory(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=1.0, volume=0.01
            )
        )
        try:
            build_gated_mt5_execution_port(
                _settings(ALLOW_LEGACY_RUN=True),
                transport=transport,
                snapshot_provider=lambda: _snapshot(),
            )
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "ALLOW_LEGACY_RUN" in str(exc)
