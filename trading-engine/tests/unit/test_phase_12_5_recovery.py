"""Phase 12.5 — UNKNOWN recovery + second-smoke blocking. Fake transport only."""

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
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.evidence import match_filled_position
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
    BrokerExecutionEvidence,
    IntentReconcileResult,
    IntentReconcileStatus,
)
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionAck,
    ExecutionIntent,
    IntentLifecycle,
)
from exness_bot.paper_execution.executor import PaperExecutor
from exness_bot.paper_execution.intent_store import (
    SnapshotIntentStore,
    UnknownReason,
)
from exness_bot.paper_execution.models import PaperSnapshot
from exness_bot.paper_execution.state import FilePaperStateStore
from exness_bot.paper_execution.unknown_recovery import apply_reconcile_to_intent
from tests.fixtures.risk_data import make_xauusd_symbol

SYMBOL = "XAUUSD"
BROKER = "XAUUSDm"


def _at() -> datetime:
    return datetime(2026, 9, 4, 8, 0, tzinfo=UTC)


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


def _identity() -> DemoIdentitySnapshot:
    account = AccountInfo(
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
    return DemoIdentitySnapshot(
        account=account,
        trade_allowed=True,
        currency="USD",
        server=account.server,
        login=account.login,
        trade_mode="demo",
        terminal_trade_allowed=True,
    )


def _market() -> DemoMarketSnapshot:
    symbol = make_xauusd_symbol()
    tick = Tick(
        symbol=BROKER,
        bid=symbol.bid,
        ask=symbol.ask,
        last=symbol.ask,
        volume=1.0,
        timestamp=_at(),
    )
    return DemoMarketSnapshot(
        symbol=symbol,
        tick=tick,
        freshness=QuoteFreshness.LIVE,
        age_seconds=1.0,
        spread_points=20.0,
    )


def _probe() -> StaticDemoBrokerProbe:
    return StaticDemoBrokerProbe(identity=_identity(), market=_market())


def _store() -> SnapshotIntentStore:
    paper = PaperExecutor(
        PaperSnapshot.initial(10_000.0),
        config=BacktestConfig.from_settings(_settings()),
    )
    return SnapshotIntentStore(paper, persist=lambda: None)


def _unknown_intent(store: SnapshotIntentStore) -> ExecutionIntent:
    intent = ExecutionIntent(
        intent_id="demo-unknown-1",
        idempotency_key="idem-unknown-1",
        symbol=SYMBOL,
        timeframe="M15",
        strategy="controlled_demo_smoke_v1",
        side=SignalDirection.LONG,
        requested_quantity=0.01,
        stop_loss=2340.0,
        take_profit=2370.0,
        created_at=_at(),
        source="phase_12_5",
    )
    store.create_intent(intent, now=_at())
    store.mark_in_flight(intent.intent_id, now=_at())
    store.mark_unknown(intent.intent_id, UnknownReason.ACK_UNKNOWN, now=_at())
    return intent


class TestUnknownRecoveryNoResubmit:
    def test_confirmed_filled(self) -> None:
        store = _store()
        intent = _unknown_intent(store)
        record = store.get(intent.intent_id)
        assert record is not None
        assert record.lifecycle is IntentLifecycle.UNKNOWN

        class _Query:
            def find_execution(self, item):  # type: ignore[no-untyped-def]
                return IntentReconcileResult(
                    status=IntentReconcileStatus.CONFIRMED_FILLED,
                    intent_id=item.intent_id,
                    idempotency_key=item.idempotency_key,
                    fill_price=2350.3,
                    broker_order_id="11",
                    broker_deal_id="22",
                    message="confirmed filled",
                )

        apply_reconcile_to_intent(
            store, record, _Query().find_execution(record), now=_at()
        )
        updated = store.get(intent.intent_id)
        assert updated is not None
        assert updated.lifecycle is IntentLifecycle.FILLED
        assert "order_send" not in inspect.getsource(apply_reconcile_to_intent)

    def test_confirmed_rejected(self) -> None:
        store = _store()
        intent = _unknown_intent(store)
        record = store.get(intent.intent_id)
        assert record is not None

        class _Query:
            def find_execution(self, item):  # type: ignore[no-untyped-def]
                return IntentReconcileResult(
                    status=IntentReconcileStatus.CONFIRMED_REJECTED,
                    intent_id=item.intent_id,
                    idempotency_key=item.idempotency_key,
                    message="confirmed rejected",
                )

        apply_reconcile_to_intent(
            store, record, _Query().find_execution(record), now=_at()
        )
        updated = store.get(intent.intent_id)
        assert updated is not None
        assert updated.lifecycle is IntentLifecycle.REJECTED

    def test_not_found_stays_unknown(self) -> None:
        store = _store()
        intent = _unknown_intent(store)
        record = store.get(intent.intent_id)
        assert record is not None

        class _Query:
            def find_execution(self, item):  # type: ignore[no-untyped-def]
                return IntentReconcileResult(
                    status=IntentReconcileStatus.NOT_FOUND,
                    intent_id=item.intent_id,
                    idempotency_key=item.idempotency_key,
                    message="not found",
                )

        apply_reconcile_to_intent(
            store, record, _Query().find_execution(record), now=_at()
        )
        updated = store.get(intent.intent_id)
        assert updated is not None
        assert updated.lifecycle is IntentLifecycle.UNKNOWN

    def test_ambiguous_stays_unknown(self) -> None:
        store = _store()
        intent = _unknown_intent(store)
        record = store.get(intent.intent_id)
        assert record is not None

        class _Query:
            def find_execution(self, item):  # type: ignore[no-untyped-def]
                return IntentReconcileResult(
                    status=IntentReconcileStatus.AMBIGUOUS,
                    intent_id=item.intent_id,
                    idempotency_key=item.idempotency_key,
                    matched_evidence=(
                        BrokerExecutionEvidence(
                            symbol=SYMBOL,
                            side=SignalDirection.LONG,
                            volume=0.01,
                            timestamp=_at(),
                        ),
                        BrokerExecutionEvidence(
                            symbol=SYMBOL,
                            side=SignalDirection.LONG,
                            volume=0.01,
                            timestamp=_at() - timedelta(seconds=1),
                        ),
                    ),
                    message="ambiguous",
                )

        apply_reconcile_to_intent(
            store, record, _Query().find_execution(record), now=_at()
        )
        updated = store.get(intent.intent_id)
        assert updated is not None
        assert updated.lifecycle is IntentLifecycle.UNKNOWN

    def test_unavailable_stays_unknown(self) -> None:
        store = _store()
        intent = _unknown_intent(store)
        record = store.get(intent.intent_id)
        assert record is not None

        class _Query:
            def find_execution(self, item):  # type: ignore[no-untyped-def]
                return IntentReconcileResult(
                    status=IntentReconcileStatus.UNAVAILABLE,
                    intent_id=item.intent_id,
                    idempotency_key=item.idempotency_key,
                    message="unavailable",
                )

        apply_reconcile_to_intent(
            store, record, _Query().find_execution(record), now=_at()
        )
        updated = store.get(intent.intent_id)
        assert updated is not None
        assert updated.lifecycle is IntentLifecycle.UNKNOWN


class TestSecondSmokeAndPreflight:
    def test_second_smoke_does_not_call_transport(self, tmp_path: Path) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                price=2350.3,
                volume=0.01,
                order_id="1",
            )
        )
        first = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=transport,
            approval=OneShotApproval(active=True),
            state_path=tmp_path / "a.json",
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert first.submitted is True
        assert len(transport.calls) == 1

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
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert second.submitted is False
        assert spy.calls == []

    def test_restart_preserves_lifecycle(self, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        result = ControlledDemoSmoke(
            settings=_settings(),
            probe=_probe(),
            transport=FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.FILLED,
                    price=2350.4,
                    volume=0.01,
                    order_id="9",
                )
            ),
            approval=OneShotApproval(active=True),
            state_path=state,
            ledger_path=tmp_path / "ledger.json",
            execute=True,
            confirm_phrase=CONFIRM_PHRASE,
        ).run()
        assert result.intent is not None
        intent_id = result.intent.intent_id
        idem = result.intent.idempotency_key

        snap = FilePaperStateStore(state).load()
        row = next(i for i in snap.intents if i.intent_id == intent_id)
        assert row.lifecycle is IntentLifecycle.FILLED
        assert row.idempotency_key == idem

    def test_preflight_blocks_when_kill_switch(self) -> None:
        report = run_demo_preflight(
            settings=_settings(LIVE_KILL_SWITCH=True),
            probe=_probe(),
            approval=OneShotApproval(active=True),
        )
        assert report.overall is CheckStatus.BLOCKED
        assert any(
            c.name == "kill_switch" and c.status is CheckStatus.BLOCKED
            for c in report.checks
        )

    def test_preflight_never_calls_order_send(self) -> None:
        source = inspect.getsource(run_demo_preflight)
        assert ".order_send(" not in source
        assert "transport.send" not in source
        assert "TRADE_ACTION_DEAL" not in source

    def test_position_match_unknown_on_ambiguity(self) -> None:
        intent = ExecutionIntent(
            intent_id="i",
            idempotency_key="k",
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
        ack = ExecutionAck(
            intent_id="i",
            idempotency_key="k",
            status=AckStatus.FILLED,
            timestamp=_at(),
            fill_price=2350.0,
            filled_quantity=0.01,
        )
        positions = (
            {"ticket": 1, "symbol": BROKER, "volume": 0.01, "type": 0},
            {"ticket": 2, "symbol": BROKER, "volume": 0.01, "type": 0},
        )
        assert (
            match_filled_position(
                intent=intent,
                ack=ack,
                positions_after=positions,
                broker_symbol=BROKER,
            )
            == "UNKNOWN"
        )

    def test_safe_defaults_unchanged(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.live_kill_switch is True
        assert settings.live_demo_approval is False
        assert settings.execution_mode.value == "paper"
        assert settings.allow_legacy_run is False
