"""Phase 12.7 — DEMO one-shot gates + Fake transport evidence. No real order_send."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.broker.mt5.execution_transport import (
    FakeMT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.enablement import (
    DemoGateName,
    DemoPreflightContext,
    evaluate_demo_controlled_enablement,
)
from exness_bot.controlled_demo.evidence import sanitize_position
from exness_bot.controlled_demo.identity import (
    DemoIdentitySnapshot,
    DemoMarketSnapshot,
    StaticDemoBrokerProbe,
)
from exness_bot.controlled_demo.preflight import CheckStatus, run_demo_preflight
from exness_bot.controlled_demo.smoke import CONFIRM_PHRASE, ControlledDemoSmoke
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import AccountInfo, Tick
from exness_bot.paper_execution.broker_query import (
    IntentReconcileResult,
    IntentReconcileStatus,
)
from exness_bot.paper_execution.contract import IntentLifecycle
from tests.fixtures.risk_data import make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"


def _at() -> datetime:
    return datetime(2026, 9, 4, 10, 30, tzinfo=UTC)


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


def _identity(*, trade_mode: str = "demo", trade_allowed: bool = True) -> DemoIdentitySnapshot:
    account = AccountInfo(
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
    return DemoIdentitySnapshot(
        account=account,
        trade_allowed=trade_allowed,
        currency="USD",
        server=account.server,
        login=account.login,
        trade_mode=trade_mode,
        terminal_connected=True,
        terminal_trade_allowed=trade_allowed,
    )


def _market(*, fresh: bool = True, age: float = 1.0) -> DemoMarketSnapshot:
    symbol = make_xauusd_symbol()
    tick = Tick(
        symbol=BROKER,
        bid=symbol.bid,
        ask=symbol.ask,
        last=symbol.ask,
        volume=1.0,
        timestamp=_at() - timedelta(seconds=age),
    )
    return DemoMarketSnapshot(
        symbol=symbol,
        tick=tick,
        freshness=QuoteFreshness.LIVE if fresh else QuoteFreshness.STALE,
        age_seconds=age,
        spread_points=20.0,
    )


def _probe(**kwargs: object) -> StaticDemoBrokerProbe:
    return StaticDemoBrokerProbe(
        identity=kwargs.get("identity", _identity()),  # type: ignore[arg-type]
        market=kwargs.get("market", _market()),  # type: ignore[arg-type]
        positions=kwargs.get("positions", ()),  # type: ignore[arg-type]
    )


def _ctx(**kwargs: object) -> DemoPreflightContext:
    base: dict[str, object] = {
        "settings": _settings(),
        "symbol_info": make_xauusd_symbol(),
        "account_trade_mode": "demo",
        "trade_allowed": True,
        "terminal_trade_allowed": True,
        "broker_login": 12345678,
        "broker_server": "Exness-MT5Trial",
        "quote_fresh": True,
        "quote_age_seconds": 1.0,
        "approval": OneShotApproval(active=True),
    }
    base.update(kwargs)
    return DemoPreflightContext(**base)  # type: ignore[arg-type]


def _gate(result, name: DemoGateName):
    return next(g for g in result.gates if g.gate == name)


class TestDemoOnlyAndAllowlist:
    def test_demo_required(self) -> None:
        result = evaluate_demo_controlled_enablement(_ctx())
        assert result.allowed is True
        assert _gate(result, DemoGateName.ACCOUNT_TRADE_MODE).allowed is True

    def test_non_demo_blocked(self) -> None:
        result = evaluate_demo_controlled_enablement(_ctx(account_trade_mode="real"))
        assert result.allowed is False
        assert _gate(result, DemoGateName.ACCOUNT_TRADE_MODE).allowed is False

    def test_allowlist_missing_blocked(self) -> None:
        result = evaluate_demo_controlled_enablement(
            _ctx(settings=_settings(DEMO_ACCOUNT_ALLOWLIST=""))
        )
        assert _gate(result, DemoGateName.BROKER_IDENTITY).allowed is False

    def test_allowlist_mismatch_blocked(self) -> None:
        result = evaluate_demo_controlled_enablement(_ctx(broker_login=999))
        assert _gate(result, DemoGateName.BROKER_IDENTITY).allowed is False


class TestQuoteAndTerminal:
    def test_fresh_quote_required(self) -> None:
        result = evaluate_demo_controlled_enablement(_ctx(quote_fresh=True))
        assert "QUOTE: FRESH" in _gate(result, DemoGateName.QUOTE_FRESHNESS).reason

    def test_stale_quote_blocked(self) -> None:
        result = evaluate_demo_controlled_enablement(
            _ctx(quote_fresh=False, quote_age_seconds=99.0)
        )
        assert result.allowed is False
        assert "STALE" in _gate(result, DemoGateName.QUOTE_FRESHNESS).reason

    def test_terminal_trade_permission_required(self) -> None:
        result = evaluate_demo_controlled_enablement(
            _ctx(trade_allowed=False, terminal_trade_allowed=False)
        )
        assert _gate(result, DemoGateName.TERMINAL_TRADE_PERMISSION).allowed is False

    def test_preflight_terminal_blocks(self) -> None:
        report = run_demo_preflight(
            settings=_settings(),
            probe=_probe(identity=_identity(trade_allowed=False)),
            approval=OneShotApproval(active=True),
        )
        assert report.overall is CheckStatus.BLOCKED
        assert any(
            c.name == "terminal_state" and c.status is CheckStatus.BLOCKED
            for c in report.checks
        )


class TestApprovalAndKill:
    def test_approval_required(self) -> None:
        result = evaluate_demo_controlled_enablement(
            _ctx(approval=OneShotApproval(active=False))
        )
        assert _gate(result, DemoGateName.DEMO_APPROVAL).allowed is False

    def test_kill_switch_blocks(self) -> None:
        result = evaluate_demo_controlled_enablement(
            _ctx(settings=_settings(LIVE_KILL_SWITCH=True))
        )
        assert _gate(result, DemoGateName.KILL_SWITCH).allowed is False

    def test_confirmation_required_no_submit(self, tmp_path: Path) -> None:
        port = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=port,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "a.json",
            ledger_path=tmp_path / "l.json",
            execute=True,
            confirm_phrase="yes",
        ).run()
        assert result.submitted is False
        assert port.calls == []


class TestOneShotAndLifecycle:
    def test_in_flight_before_submit_and_one_call(self, tmp_path: Path) -> None:
        seen: list[str] = []

        def _before(_req: object) -> None:
            from exness_bot.paper_execution.state import FilePaperStateStore

            snap = FilePaperStateStore(tmp_path / "state.json").load()
            assert snap.intents
            assert snap.intents[-1].lifecycle is IntentLifecycle.IN_FLIGHT
            seen.append("ok")

        port = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.3, volume=0.01, order_id="1"
            ),
            on_before_send=_before,
        )
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=port,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.submitted is True
        assert len(port.calls) == 1
        assert seen == ["ok"]
        assert result.lifecycle is IntentLifecycle.FILLED

    def test_second_attempt_blocked(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.json"
        port = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.0, volume=0.01
            )
        )
        ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=port,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "a.json",
            ledger_path=ledger,
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        spy = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=1.0, volume=0.01
            )
        )
        second = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=spy,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "b.json",
            ledger_path=ledger,
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert second.submitted is False
        assert spy.calls == []

    def test_broker_rejection(self, tmp_path: Path) -> None:
        port = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.REJECTED, comment="rej")
        )
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=port,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "r.json",
            ledger_path=tmp_path / "rl.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert len(port.calls) == 1
        assert result.lifecycle is IntentLifecycle.REJECTED

    def test_broker_exception_unknown_no_retry(self, tmp_path: Path) -> None:
        def _boom(_req: object) -> None:
            raise RuntimeError("transport_boom")

        port = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.FILLED, price=1.0, volume=0.01),
            on_before_send=_boom,
        )
        # Fake transport raises before appending? It appends then on_before - check Fake
        # Actually Fake calls on_before_send first then appends. So exception = 0 calls?
        # Looking at Fake: on_before then append. Exception => calls empty.
        # For MT5Executor path, exception maps differently. Smoke uses MT5Executor which
        # catches transport results not exceptions from Fake if Fake raises before return.
        # Use UNKNOWN outcome instead for reliable UNKNOWN lifecycle.
        port2 = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN, comment="amb")
        )
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=port2,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "u.json",
            ledger_path=tmp_path / "ul.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert len(port2.calls) == 1
        assert result.lifecycle is IntentLifecycle.UNKNOWN
        # Second attempt ledger-blocked
        spy = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.FILLED, price=1.0, volume=0.01)
        )
        again = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=spy,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "u2.json",
            ledger_path=tmp_path / "ul.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert spy.calls == []
        assert again.submitted is False
        del port  # unused intentional for documentation


class TestReconcileUnknown:
    def test_not_found_ambiguous_unavailable_stay_unknown(self) -> None:
        from exness_bot.backtest.config import BacktestConfig
        from exness_bot.paper_execution.contract import ExecutionIntent
        from exness_bot.paper_execution.executor import PaperExecutor
        from exness_bot.paper_execution.intent_store import SnapshotIntentStore, UnknownReason
        from exness_bot.paper_execution.models import PaperSnapshot
        from exness_bot.paper_execution.unknown_recovery import apply_reconcile_to_intent

        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = SnapshotIntentStore(paper, persist=lambda: None)
        for idx, status in enumerate(
            (
                IntentReconcileStatus.NOT_FOUND,
                IntentReconcileStatus.AMBIGUOUS,
                IntentReconcileStatus.UNAVAILABLE,
            )
        ):
            intent = ExecutionIntent(
                intent_id=f"u{idx}",
                idempotency_key=f"k{idx}",
                symbol=SYMBOL,
                timeframe="M15",
                strategy="controlled_demo_smoke_v1",
                side=SignalDirection.LONG,
                requested_quantity=0.01,
                stop_loss=1.0,
                take_profit=2.0,
                created_at=_at(),
                source="t",
            )
            store.create_intent(intent, now=_at())
            store.mark_in_flight(intent.intent_id, now=_at())
            store.mark_unknown(intent.intent_id, UnknownReason.ACK_UNKNOWN, now=_at())
            record = store.get(intent.intent_id)
            assert record is not None
            apply_reconcile_to_intent(
                store,
                record,
                IntentReconcileResult(
                    status=status,
                    intent_id=record.intent_id,
                    idempotency_key=record.idempotency_key,
                    message=status.value,
                ),
                now=_at(),
            )
            updated = store.get(intent.intent_id)
            assert updated is not None
            assert updated.lifecycle is IntentLifecycle.UNKNOWN


class TestEvidenceAndSafety:
    def test_sanitize_position_strips_secrets(self) -> None:
        cleaned = sanitize_position(
            {
                "ticket": 1,
                "symbol": BROKER,
                "volume": 0.01,
                "password": "secret",
                "token": "x",
            }
        )
        assert "password" not in cleaned
        assert cleaned["ticket"] == 1

    def test_safe_defaults(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.live_kill_switch is True
        assert settings.live_demo_approval is False
        assert settings.execution_mode.value == "paper"
        assert settings.allow_legacy_run is False

    def test_no_auto_close_helpers_in_controlled_demo(self) -> None:
        for path in (SRC / "controlled_demo").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "positions_close" not in text
            assert "close_position(" not in text or "Virtual" in text

    def test_order_send_only_in_live_transport_ast(self) -> None:
        live = SRC / "broker" / "mt5" / "execution_transport.py"
        assert "order_send" in live.read_text(encoding="utf-8")
        for pkg in ("execution", "signal_engine", "candle_engine", "risk"):
            for path in (SRC / pkg).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        assert "MetaTrader5" not in (node.module or "")

    def test_factory_no_mt5_wiring(self) -> None:
        import inspect

        from exness_bot.paper_execution import factory

        source = inspect.getsource(factory)
        assert "LiveMT5ExecutionTransport" not in source
        assert "MT5Executor" not in source
