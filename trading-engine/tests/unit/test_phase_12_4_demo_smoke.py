"""Phase 12.4 — controlled DEMO one-shot smoke. Fake transport only."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from exness_bot.broker.mt5.execution_transport import (
    FakeMT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.broker.mt5.executor import MT5Executor
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
from exness_bot.controlled_demo.oneshot_transport import OneShotExecutionTransport
from exness_bot.controlled_demo.smoke import CONFIRM_PHRASE, ControlledDemoSmoke
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import AccountInfo, Tick
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionEvidence,
    IntentReconcileResult,
    IntentReconcileStatus,
)
from exness_bot.paper_execution.contract import AckStatus, IntentLifecycle
from tests.fixtures.risk_data import make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"


def _at() -> datetime:
    return datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


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
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _account(*, trade_mode: str = "demo") -> AccountInfo:
    return AccountInfo(
        login=12345678,
        balance=10_000.0,
        equity=10_000.0,
        margin=0.0,
        free_margin=10_000.0,
        currency="USD",
        leverage=500,
        server="Exness-MT5Trial",
        trade_mode=trade_mode,
    )


def _identity(*, trade_mode: str = "demo") -> DemoIdentitySnapshot:
    account = _account(trade_mode=trade_mode)
    return DemoIdentitySnapshot(
        account=account,
        trade_allowed=True,
        currency="USD",
        server=account.server,
        login=account.login,
        trade_mode=trade_mode,
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


def _gate(result, name: DemoGateName):
    return next(g for g in result.gates if g.gate == name)


class TestDemoEnvironment:
    def test_demo_environment_required(self) -> None:
        ctx = DemoPreflightContext(
            settings=_settings(TRADING_ENV="demo"),
            symbol_info=make_xauusd_symbol(),
            account_trade_mode="demo",
            trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert _gate(result, DemoGateName.TRADING_ENV).allowed is True

    def test_real_live_environment_rejected(self) -> None:
        for env in ("live", "production", "real"):
            ctx = DemoPreflightContext(
                settings=_settings(TRADING_ENV=env),
                symbol_info=make_xauusd_symbol(),
                account_trade_mode="demo",
                broker_login=12345678,
                quote_fresh=True,
                quote_age_seconds=1.0,
                approval=OneShotApproval(active=True),
            )
            result = evaluate_demo_controlled_enablement(ctx)
            assert result.allowed is False
            assert _gate(result, DemoGateName.TRADING_ENV).allowed is False

    def test_missing_environment_rejected(self) -> None:
        settings = _settings()
        object.__setattr__(settings, "trading_env", "")
        ctx = DemoPreflightContext(
            settings=settings,
            symbol_info=make_xauusd_symbol(),
            account_trade_mode="demo",
            trade_allowed=True,
            broker_login=12345678,
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert result.allowed is False


class TestIdentityAndGates:
    def test_broker_identity_mismatch_rejected(self) -> None:
        ctx = DemoPreflightContext(
            settings=_settings(),
            symbol_info=make_xauusd_symbol(),
            account_trade_mode="demo",
            broker_login=99999999,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert _gate(result, DemoGateName.BROKER_IDENTITY).allowed is False

    def test_kill_switch_blocks(self) -> None:
        ctx = DemoPreflightContext(
            settings=_settings(LIVE_KILL_SWITCH=True),
            symbol_info=make_xauusd_symbol(),
            account_trade_mode="demo",
            trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert _gate(result, DemoGateName.KILL_SWITCH).allowed is False
        assert result.allowed is False

    def test_approval_required(self) -> None:
        ctx = DemoPreflightContext(
            settings=_settings(LIVE_DEMO_APPROVAL=False),
            symbol_info=make_xauusd_symbol(),
            account_trade_mode="demo",
            trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=False),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert _gate(result, DemoGateName.DEMO_APPROVAL).allowed is False

    def test_approval_is_one_shot(self) -> None:
        approval = OneShotApproval(active=True)
        assert approval.try_consume(intent_id="a") is True
        assert approval.try_consume(intent_id="b") is False
        assert approval.consumed is True

    def test_executor_cannot_bypass_gate(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.3, volume=0.01
            )
        )
        executor = MT5Executor(
            transport=transport,
            settings=_settings(LIVE_KILL_SWITCH=True, TRADING_ENV="research"),
            require_enablement=True,
        )
        from exness_bot.controlled_demo.intent_factory import CONTROLLED_STRATEGY_ID
        from exness_bot.paper_execution.contract import ExecutionIntent

        intent = ExecutionIntent(
            intent_id="x",
            idempotency_key="k",
            symbol=SYMBOL,
            timeframe="M15",
            strategy=CONTROLLED_STRATEGY_ID,
            side=SignalDirection.LONG,
            requested_quantity=0.01,
            stop_loss=2340.0,
            take_profit=2370.0,
            created_at=_at(),
            source="test",
        )
        ack = executor.submit(intent, quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []


class TestQuoteAndVolume:
    def test_invalid_quote_blocks(self, tmp_path: Path) -> None:
        market = _market()
        bad = market.symbol.model_copy(update={"bid": 0.0, "ask": 0.0})
        market = DemoMarketSnapshot(
            symbol=bad,
            tick=market.tick,
            freshness=QuoteFreshness.LIVE,
            age_seconds=1.0,
            spread_points=0.0,
        )
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(market=market),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(outcome=TransportOutcome.REJECTED)
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert result.submitted is False

    def test_stale_quote_blocks(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(market=_market(age_seconds=60.0, fresh=False)),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(outcome=TransportOutcome.REJECTED)
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.blocked is True
        assert result.enablement is not None
        assert _gate(result.enablement, DemoGateName.QUOTE_FRESHNESS).allowed is False

    def test_missing_stops_metadata_blocks(self) -> None:
        ctx = DemoPreflightContext(
            settings=_settings(),
            symbol_info=make_xauusd_symbol(stops_level=None, freeze_level=0),
            account_trade_mode="demo",
            trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert _gate(result, DemoGateName.SYMBOL_METADATA).allowed is False

    def test_invalid_volume_blocks(self) -> None:
        symbol = make_xauusd_symbol().model_copy(
            update={"volume_min": 0.0, "volume_step": 0.0, "volume_max": 0.0}
        )
        ctx = DemoPreflightContext(
            settings=_settings(),
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
        assert _gate(result, DemoGateName.SYMBOL_METADATA).allowed is False


class TestLifecycleAndTransport:
    def test_in_flight_persisted_before_transport(self, tmp_path: Path) -> None:
        seen: list[str] = []

        def _before(_req: dict) -> None:
            from exness_bot.paper_execution.state import FilePaperStateStore

            snap = FilePaperStateStore(tmp_path / "state.json").load()
            assert any(i.lifecycle is IntentLifecycle.IN_FLIGHT for i in snap.intents)
            seen.append("ok")

        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                price=2350.35,
                volume=0.01,
                order_id="1",
                deal_id="2",
            ),
            on_before_send=_before,
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
        assert result.submitted is True
        assert seen == ["ok"]
        assert result.transport_send_count == 1

    def test_transport_called_exactly_once(self, tmp_path: Path) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                price=2350.35,
                volume=0.01,
                order_id="1",
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
        assert len(transport.calls) == 1
        assert result.transport_send_count == 1

    def test_filled_maps_correctly(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED,
                    price=2350.40,
                    volume=0.01,
                    order_id="9",
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.ack is not None
        assert result.ack.status is AckStatus.FILLED
        assert result.lifecycle is IntentLifecycle.FILLED

    def test_rejected_maps_correctly(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(outcome=TransportOutcome.REJECTED, retcode=10016)
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

    def test_timeout_becomes_unknown(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(outcome=TransportOutcome.TIMEOUT)
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.lifecycle is IntentLifecycle.UNKNOWN

    def test_partial_fill_becomes_unknown(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.PARTIAL,
                    price=2350.3,
                    volume=0.005,
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.ack is not None
        assert result.ack.status is AckStatus.UNKNOWN
        assert result.lifecycle is IntentLifecycle.UNKNOWN

    def test_unknown_never_retries(self, tmp_path: Path) -> None:
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
        assert result.transport_send_count == 1
        # Second send blocked by one-shot wrapper
        again = oneshot.send({"action": 1})
        assert again.outcome is TransportOutcome.UNKNOWN
        assert "ONE_SHOT_VIOLATION" in (again.comment or "")
        assert len(transport.calls) == 1


class TestReconciliationAndSafety:
    def test_unknown_reconciliation_can_confirm_filled(self, tmp_path: Path) -> None:
        class _Query:
            def find_execution(self, intent):
                return IntentReconcileResult(
                    status=IntentReconcileStatus.CONFIRMED_FILLED,
                    intent_id=intent.intent_id,
                    idempotency_key=intent.idempotency_key,
                    matched_evidence=(
                        BrokerExecutionEvidence(
                            broker_order_id="1",
                            broker_deal_id="2",
                            symbol=SYMBOL,
                            side=SignalDirection.LONG,
                            volume=0.01,
                            fill_price=2350.3,
                            timestamp=_at(),
                        ),
                    ),
                    message="confirmed",
                    broker_order_id="1",
                    broker_deal_id="2",
                    fill_price=2350.3,
                )

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
            broker_query=_Query(),  # type: ignore[arg-type]
        ).run()
        assert result.lifecycle is IntentLifecycle.FILLED
        assert result.reconcile_status == IntentReconcileStatus.CONFIRMED_FILLED.value

    def test_unknown_reconciliation_can_confirm_rejected(self, tmp_path: Path) -> None:
        class _Query:
            def find_execution(self, intent):
                return IntentReconcileResult(
                    status=IntentReconcileStatus.CONFIRMED_REJECTED,
                    intent_id=intent.intent_id,
                    idempotency_key=intent.idempotency_key,
                    message="rejected",
                )

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
            broker_query=_Query(),  # type: ignore[arg-type]
        ).run()
        assert result.lifecycle is IntentLifecycle.REJECTED

    def test_ambiguous_reconciliation_stays_unknown(self, tmp_path: Path) -> None:
        class _Query:
            def find_execution(self, intent):
                return IntentReconcileResult(
                    status=IntentReconcileStatus.AMBIGUOUS,
                    intent_id=intent.intent_id,
                    idempotency_key=intent.idempotency_key,
                    message="ambiguous",
                )

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
            broker_query=_Query(),  # type: ignore[arg-type]
        ).run()
        assert result.lifecycle is IntentLifecycle.UNKNOWN

    def test_no_signal_engine_dependency(self) -> None:
        root = SRC / "controlled_demo"
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "signal_engine" not in text
            assert "SignalEngine" not in text

    def test_no_strategy_loop(self) -> None:
        source = inspect.getsource(ControlledDemoSmoke.run)
        assert "while True" not in source
        assert "Thread(" not in source

    def test_legacy_run_path_never_used(self) -> None:
        source = inspect.getsource(ControlledDemoSmoke)
        assert "OrderManager" not in source
        assert "MT5Adapter" not in source
        assert "handle_run" not in source

    def test_exactly_one_controlled_intent(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED,
                    price=2350.3,
                    volume=0.01,
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.intent is not None
        assert result.intent.strategy == "controlled_demo_smoke_v1"

    def test_second_submission_is_blocked(self, tmp_path: Path) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                price=2350.3,
                volume=0.01,
            )
        )
        first = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=transport,
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
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED,
                    price=2350.3,
                    volume=0.01,
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state2.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert second.submitted is False
        assert second.blocked is True

    def test_paper_execution_unchanged(self) -> None:
        from exness_bot.paper_execution.executor import PaperExecutor

        source = inspect.getsource(PaperExecutor.submit)
        assert "order_send" not in source
        assert "LiveMT5" not in source

    def test_confirm_required(self, tmp_path: Path) -> None:
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED, price=1.0, volume=0.01
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase="yes",
        ).run()
        assert result.submitted is False

    def test_live_account_trade_mode_blocks(self) -> None:
        ctx = DemoPreflightContext(
            settings=_settings(),
            symbol_info=make_xauusd_symbol(),
            account_trade_mode="live",
            trade_allowed=True,
            broker_login=12345678,
            broker_server="Exness-MT5Trial",
            quote_fresh=True,
            quote_age_seconds=1.0,
            approval=OneShotApproval(active=True),
        )
        result = evaluate_demo_controlled_enablement(ctx)
        assert _gate(result, DemoGateName.ACCOUNT_TRADE_MODE).allowed is False


class TestStaticAudit:
    def test_phase11_packages_free_of_mt5_trading(self) -> None:
        for package in ("candle_engine", "signal_engine", "risk", "paper_execution"):
            for path in (SRC / package).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                assert "TRADE_ACTION_DEAL" not in text, path
                assert "MT5Adapter" not in text, path
                assert "OrderManager" not in text, path
                cleaned = text
                for phrase in (
                    "No order_send",
                    "no order_send",
                    "never calls order_send",
                    "excludes order_send",
                ):
                    cleaned = cleaned.replace(phrase, "")
                assert "order_send" not in cleaned, path

    def test_controlled_demo_has_no_strategy_loop(self) -> None:
        for path in (SRC / "controlled_demo").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.While):
                    pytest.fail(f"while loop in {path}")

    def test_cli_has_demo_smoke_command(self) -> None:
        from exness_bot.cli import build_parser

        help_text = build_parser().format_help()
        assert "demo-execution-smoke" in help_text
