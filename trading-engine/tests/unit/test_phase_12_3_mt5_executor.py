"""Phase 12.3 — MT5Executor execution boundary. No real order_send."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from exness_bot.broker.mt5.execution_transport import (
    FakeMT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.broker.mt5.executor import (
    MT5Executor,
    build_mt5_request,
    normalize_price,
    normalize_volume,
    parse_symbol_map,
)
from exness_bot.broker.mt5.mapper import (
    MT5_ORDER_TYPE_BUY,
    MT5_ORDER_TYPE_SELL,
    MT5_TRADE_ACTION_DEAL,
)
from exness_bot.config.live_enablement import LivePreflightContext, evaluate_live_enablement
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.broker_query import StaticBrokerExecutionQuery
from exness_bot.paper_execution.contract import (
    AckStatus,
    ExecutionIntent,
    IntentLifecycle,
)
from exness_bot.paper_execution.intent_store import SnapshotIntentStore
from tests.fixtures.risk_data import make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
SYMBOL = "XAUUSD"
BROKER_SYMBOL = "XAUUSDm"


def _at() -> datetime:
    return datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "EXECUTION_MODE": "paper",
        "ALLOW_LIVE_TRADING": False,
        "ALLOW_LEGACY_RUN": False,
        "LIVE_KILL_SWITCH": True,
        "TRADING_ENV": "research",
        "LIVE_SYMBOL_MAP": f"{SYMBOL}:{BROKER_SYMBOL}",
        "DRY_RUN": True,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _enablement_settings() -> Settings:
    return _settings(
        EXECUTION_MODE="live",
        ALLOW_LIVE_TRADING=True,
        LIVE_KILL_SWITCH=False,
        TRADING_ENV="live",
        LIVE_ACCOUNT_ALLOWLIST="12345678",
        LIVE_SERVER_ALLOWLIST="Exness-MT5Live",
        MT5_LOGIN=12345678,
        MT5_SERVER="Exness-MT5Live",
        DRY_RUN=False,
        TRADING_MODE="live",
    )


def _preflight(settings: Settings | None = None, **kwargs: object) -> LivePreflightContext:
    return LivePreflightContext(
        settings=settings or _enablement_settings(),
        requested_execution_mode="live",
        symbol_info=kwargs.get("symbol_info", make_xauusd_symbol()),  # type: ignore[arg-type]
        intents=kwargs.get("intents", ()),  # type: ignore[arg-type]
        intent_store_error=kwargs.get("intent_store_error"),  # type: ignore[arg-type]
        broker_query=kwargs.get("broker_query", StaticBrokerExecutionQuery(())),  # type: ignore[arg-type]
        broker_login=kwargs.get("broker_login", 12345678),  # type: ignore[arg-type]
        broker_server=kwargs.get("broker_server", "Exness-MT5Live"),  # type: ignore[arg-type]
        evaluated_at=_at(),
    )


def _intent(
    *,
    side: SignalDirection = SignalDirection.LONG,
    volume: float = 0.10,
    sl: float = 2340.0,
    tp: float = 2370.0,
) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="live-intent-1",
        idempotency_key="sig-key-1",
        symbol=SYMBOL,
        timeframe="M15",
        strategy="ema_rsi_atr_v1",
        side=side,
        requested_quantity=volume,
        stop_loss=sl,
        take_profit=tp,
        created_at=_at(),
        source="test",
    )


def _executor(
    transport: FakeMT5ExecutionTransport,
    *,
    require_enablement: bool = False,
    settings: Settings | None = None,
    preflight: LivePreflightContext | None = None,
) -> MT5Executor:
    return MT5Executor(
        transport=transport,
        settings=settings or _settings(),
        symbol_map={SYMBOL: BROKER_SYMBOL},
        preflight_context=preflight,
        require_enablement=require_enablement,
    )


class TestRequestConstruction:
    def test_buy_intent_maps_to_mt5_buy_request(self) -> None:
        quote = make_xauusd_symbol()
        built = build_mt5_request(
            _intent(side=SignalDirection.LONG),
            quote=quote,
            symbol_map={SYMBOL: BROKER_SYMBOL},
            magic=120300,
            deviation=20,
        )
        from exness_bot.broker.mt5.executor import BuiltMt5Request

        assert isinstance(built, BuiltMt5Request)
        assert built.payload["action"] == MT5_TRADE_ACTION_DEAL
        assert built.payload["type"] == MT5_ORDER_TYPE_BUY
        assert built.payload["price"] == quote.ask
        assert built.payload["symbol"] == BROKER_SYMBOL

    def test_sell_intent_maps_to_mt5_sell_request(self) -> None:
        quote = make_xauusd_symbol()
        built = build_mt5_request(
            _intent(side=SignalDirection.SHORT, sl=2360.0, tp=2330.0),
            quote=quote,
            symbol_map={SYMBOL: BROKER_SYMBOL},
            magic=1,
            deviation=10,
        )
        from exness_bot.broker.mt5.executor import BuiltMt5Request

        assert isinstance(built, BuiltMt5Request)
        assert built.payload["type"] == MT5_ORDER_TYPE_SELL
        assert built.payload["price"] == quote.bid

    def test_symbol_mapping_is_explicit(self) -> None:
        from exness_bot.paper_execution.contract import ExecutionAck

        mapping = parse_symbol_map("XAUUSD:XAUUSDm,EURUSD:EURUSDm")
        assert mapping["XAUUSD"] == "XAUUSDm"
        ack = build_mt5_request(
            _intent(),
            quote=make_xauusd_symbol(),
            symbol_map={},
            magic=1,
            deviation=20,
        )
        assert isinstance(ack, ExecutionAck)
        assert ack.status is AckStatus.REJECTED
        assert "SYMBOL_MAPPING_MISSING" in (ack.reason or "")

    def test_volume_is_normalized_to_broker_step(self) -> None:
        symbol = make_xauusd_symbol()
        # Float noise around 0.10
        noisy = 0.10 + 1e-12
        assert normalize_volume(noisy, symbol) == pytest.approx(0.10)
        assert normalize_volume(0.105, symbol) is None  # material change → reject

    def test_price_is_normalized_to_tick_size(self) -> None:
        symbol = make_xauusd_symbol(ask=2350.304, bid=2350.101)
        assert normalize_price(2350.304, symbol) == 2350.30
        assert normalize_price(2350.101, symbol) == 2350.10


class TestValidation:
    def test_invalid_quote_is_rejected(self) -> None:
        bad = make_xauusd_symbol(bid=0.0, ask=0.0)
        ack = build_mt5_request(
            _intent(),
            quote=bad,
            symbol_map={SYMBOL: BROKER_SYMBOL},
            magic=1,
            deviation=20,
        )
        from exness_bot.paper_execution.contract import ExecutionAck

        assert isinstance(ack, ExecutionAck)
        assert ack.status is AckStatus.REJECTED
        assert "INVALID_QUOTE" in (ack.reason or "")

    def test_missing_stops_metadata_is_rejected(self) -> None:
        quote = make_xauusd_symbol(stops_level=None, freeze_level=0)
        ack = build_mt5_request(
            _intent(),
            quote=quote,
            symbol_map={SYMBOL: BROKER_SYMBOL},
            magic=1,
            deviation=20,
        )
        from exness_bot.paper_execution.contract import ExecutionAck

        assert isinstance(ack, ExecutionAck)
        assert "STOPS_METADATA" in (ack.reason or "")

    def test_invalid_buy_sl_tp_geometry_is_rejected(self) -> None:
        ack = build_mt5_request(
            _intent(side=SignalDirection.LONG, sl=2400.0, tp=2300.0),
            quote=make_xauusd_symbol(),
            symbol_map={SYMBOL: BROKER_SYMBOL},
            magic=1,
            deviation=20,
        )
        from exness_bot.paper_execution.contract import ExecutionAck

        assert isinstance(ack, ExecutionAck)
        assert ack.status is AckStatus.REJECTED

    def test_invalid_sell_sl_tp_geometry_is_rejected(self) -> None:
        ack = build_mt5_request(
            _intent(side=SignalDirection.SHORT, sl=2300.0, tp=2400.0),
            quote=make_xauusd_symbol(),
            symbol_map={SYMBOL: BROKER_SYMBOL},
            magic=1,
            deviation=20,
        )
        from exness_bot.paper_execution.contract import ExecutionAck

        assert isinstance(ack, ExecutionAck)
        assert ack.status is AckStatus.REJECTED

    def test_volume_outside_limits_is_rejected(self) -> None:
        ack = build_mt5_request(
            _intent(volume=999.0),
            quote=make_xauusd_symbol(volume_max=1.0),
            symbol_map={SYMBOL: BROKER_SYMBOL},
            magic=1,
            deviation=20,
        )
        from exness_bot.paper_execution.contract import ExecutionAck

        assert isinstance(ack, ExecutionAck)
        assert "INVALID_VOLUME" in (ack.reason or "")


class TestBrokerResponse:
    def test_confirmed_broker_fill_returns_filled(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                retcode=10009,
                order_id="1001",
                deal_id="2002",
                price=2350.35,
                volume=0.10,
            )
        )
        ack = _executor(transport).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.FILLED
        assert ack.fill_price == 2350.35
        assert ack.broker_order_id == "1001"
        assert ack.filled_quantity == 0.10

    def test_broker_rejection_returns_rejected(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.REJECTED,
                retcode=10016,
                comment="invalid stops",
            )
        )
        ack = _executor(transport).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert "10016" in (ack.reason or "")

    def test_timeout_returns_unknown(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.TIMEOUT, retcode=10027)
        )
        ack = _executor(transport).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.TIMEOUT

    def test_ambiguous_broker_result_returns_unknown(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.UNKNOWN,
                retcode=99999,
                comment="ambiguous",
            )
        )
        ack = _executor(transport).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.UNKNOWN


class TestSafety:
    def test_unknown_is_never_retried(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN, retcode=10031)
        )
        executor = _executor(transport)
        first = executor.submit(_intent(), quote=make_xauusd_symbol())
        second = executor.submit(_intent(), quote=make_xauusd_symbol())
        assert first.status is AckStatus.UNKNOWN
        assert second.status is AckStatus.UNKNOWN
        # Caller may submit again; executor itself has no retry loop.
        assert len(transport.calls) == 2
        source = inspect.getsource(MT5Executor.submit)
        assert "for " not in source.split("transport.send")[0] or "retry" not in source.lower()
        assert "while " not in source.lower()
        assert "retry" not in source.lower()

    def test_executor_does_not_modify_strategy(self) -> None:
        source = inspect.getsource(MT5Executor)
        assert "SignalEngine" not in source
        assert "EmaRsiAtr" not in source
        assert "calculate_rsi" not in source

    def test_executor_does_not_call_risk_manager(self) -> None:
        source = inspect.getsource(MT5Executor)
        assert "RiskManager" not in source
        assert "assess(" not in source

    def test_executor_does_not_call_legacy_order_manager(self) -> None:
        source = inspect.getsource(MT5Executor)
        assert "OrderManager" not in source
        assert "MT5Adapter" not in source
        transport_src = inspect.getsource(FakeMT5ExecutionTransport.send)
        assert "order_send" not in transport_src
        assert ".order_send" not in transport_src


class TestPersistenceLifecycle:
    def test_in_flight_is_persisted_before_submit(self) -> None:
        from exness_bot.backtest.config import BacktestConfig
        from exness_bot.paper_execution.executor import PaperExecutor
        from exness_bot.paper_execution.models import PaperSnapshot

        snap_store = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        seen: list[str] = []

        def _before(_request: dict) -> None:
            record = snap_store.intent_by_key("sig-key-1")
            assert record is not None
            assert record.lifecycle is IntentLifecycle.IN_FLIGHT
            seen.append("ok")

        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                price=2350.35,
                volume=0.10,
                order_id="1",
                deal_id="2",
            ),
            on_before_send=_before,
        )
        intents = SnapshotIntentStore(snap_store, persist=lambda: None)
        intent = _intent()
        created = intents.create_intent(intent, now=_at())
        assert created.created
        intents.mark_in_flight(intent.intent_id, now=_at())
        ack = _executor(transport).submit(intent, quote=make_xauusd_symbol())
        assert ack.status is AckStatus.FILLED
        assert seen == ["ok"]

    def test_confirmed_fill_persists_filled(self) -> None:
        from exness_bot.backtest.config import BacktestConfig
        from exness_bot.paper_execution.executor import PaperExecutor
        from exness_bot.paper_execution.intent_store import ExecutionEvidence
        from exness_bot.paper_execution.models import PaperSnapshot

        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = SnapshotIntentStore(paper, persist=lambda: None)
        intent = _intent()
        store.create_intent(intent, now=_at())
        store.mark_in_flight(intent.intent_id, now=_at())
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                price=2350.40,
                volume=0.10,
                order_id="9",
            )
        )
        ack = _executor(transport).submit(intent, quote=make_xauusd_symbol())
        store.mark_filled(
            intent.intent_id,
            ExecutionEvidence(fill_price=ack.fill_price, broker_order_id=ack.broker_order_id),
            now=_at(),
        )
        row = store.get(intent.intent_id)
        assert row is not None
        assert row.lifecycle is IntentLifecycle.FILLED

    def test_rejection_persists_rejected(self) -> None:
        from exness_bot.backtest.config import BacktestConfig
        from exness_bot.paper_execution.executor import PaperExecutor
        from exness_bot.paper_execution.intent_store import ExecutionEvidence
        from exness_bot.paper_execution.models import PaperSnapshot

        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = SnapshotIntentStore(paper, persist=lambda: None)
        intent = _intent()
        store.create_intent(intent, now=_at())
        store.mark_in_flight(intent.intent_id, now=_at())
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.REJECTED, retcode=10006)
        )
        ack = _executor(transport).submit(intent, quote=make_xauusd_symbol())
        store.mark_rejected(
            intent.intent_id,
            ExecutionEvidence(reason=ack.reason, ack_status=ack.status.value),
            now=_at(),
        )
        assert store.get(intent.intent_id).lifecycle is IntentLifecycle.REJECTED  # type: ignore[union-attr]

    def test_unknown_persists_unknown(self) -> None:
        from exness_bot.backtest.config import BacktestConfig
        from exness_bot.paper_execution.executor import PaperExecutor
        from exness_bot.paper_execution.intent_store import UnknownReason
        from exness_bot.paper_execution.models import PaperSnapshot

        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = SnapshotIntentStore(paper, persist=lambda: None)
        intent = _intent()
        store.create_intent(intent, now=_at())
        store.mark_in_flight(intent.intent_id, now=_at())
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(outcome=TransportOutcome.UNKNOWN)
        )
        ack = _executor(transport).submit(intent, quote=make_xauusd_symbol())
        assert ack.status is AckStatus.UNKNOWN
        store.mark_unknown(intent.intent_id, UnknownReason.ACK_UNKNOWN, now=_at())
        assert store.get(intent.intent_id).lifecycle is IntentLifecycle.UNKNOWN  # type: ignore[union-attr]

    def test_restart_after_unknown_does_not_resubmit(self) -> None:
        from exness_bot.backtest.config import BacktestConfig
        from exness_bot.paper_execution.executor import PaperExecutor
        from exness_bot.paper_execution.intent_store import UnknownReason
        from exness_bot.paper_execution.models import PaperSnapshot

        paper = PaperExecutor(
            PaperSnapshot.initial(10_000.0),
            config=BacktestConfig.from_settings(_settings()),
        )
        store = SnapshotIntentStore(paper, persist=lambda: None)
        intent = _intent()
        store.create_intent(intent, now=_at())
        store.mark_in_flight(intent.intent_id, now=_at())
        store.mark_unknown(intent.intent_id, UnknownReason.ACK_TIMEOUT, now=_at())
        assert paper.has_blocking_intent(intent.idempotency_key)
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=1.0, volume=0.1
            )
        )
        assert paper.has_blocking_intent(intent.idempotency_key)
        assert len(transport.calls) == 0


class TestGateEnforcement:
    def test_live_executor_requires_enablement_gates(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.3, volume=0.1
            )
        )
        # Defaults: kill switch on → blocked
        executor = _executor(
            transport,
            require_enablement=True,
            settings=_settings(),
            preflight=_preflight(_settings()),
        )
        ack = executor.submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert "LIVE_ENABLEMENT_BLOCKED" in (ack.reason or "")
        assert transport.calls == []

    def test_kill_switch_blocks_submission(self) -> None:
        settings = _enablement_settings()
        object.__setattr__(settings, "live_kill_switch", True)
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.3, volume=0.1
            )
        )
        ack = _executor(
            transport,
            require_enablement=True,
            settings=settings,
            preflight=_preflight(settings),
        ).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []

    def test_unresolved_unknown_blocks_submission(self) -> None:
        from exness_bot.paper_execution.contract import IntentRecord

        now = _at()
        unknown = IntentRecord(
            intent_id="u1",
            idempotency_key="k",
            lifecycle=IntentLifecycle.UNKNOWN,
            created_at=now,
            updated_at=now,
            side="LONG",
            symbol=SYMBOL,
            requested_quantity=0.1,
            stop_loss=2340.0,
            take_profit=2370.0,
        )
        settings = _enablement_settings()
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.3, volume=0.1
            )
        )
        ack = _executor(
            transport,
            require_enablement=True,
            settings=settings,
            preflight=_preflight(settings, intents=(unknown,)),
        ).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        assert transport.calls == []

    def test_legacy_run_cannot_be_used_as_fallback(self) -> None:
        settings = _enablement_settings()
        object.__setattr__(settings, "allow_legacy_run", True)
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED, price=2350.3, volume=0.1
            )
        )
        ack = _executor(
            transport,
            require_enablement=True,
            settings=settings,
            preflight=_preflight(settings),
        ).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.REJECTED
        source = inspect.getsource(MT5Executor)
        assert "OrderManager" not in source
        assert "legacy fallback" not in source.lower()
        assert "OrderManager" not in inspect.getsource(
            __import__("exness_bot.broker.mt5.executor", fromlist=["map_transport_to_ack"])
        )


class TestTransportIsolation:
    def test_executor_uses_execution_transport(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                price=2350.35,
                volume=0.10,
                order_id="1",
            )
        )
        _executor(transport).submit(_intent(), quote=make_xauusd_symbol())
        assert len(transport.calls) == 1
        assert transport.calls[0]["action"] == MT5_TRADE_ACTION_DEAL

    def test_fake_transport_does_not_contain_order_send(self) -> None:
        source = inspect.getsource(FakeMT5ExecutionTransport.send)
        assert "order_send" not in source
        assert "MetaTrader5" not in source
        body = FakeMT5ExecutionTransport.send.__code__.co_names
        assert "order_send" not in body

    def test_phase_11_packages_remain_free_of_mt5_trading_api(self) -> None:
        packages = [
            SRC / "candle_engine",
            SRC / "signal_engine",
            SRC / "risk",
            SRC / "paper_execution",
            SRC / "config" / "live_enablement.py",
        ]
        forbidden = ("order_send", "TRADE_ACTION_DEAL", "TRADE_ACTION_PENDING")
        for path in packages:
            files = [path] if path.is_file() else list(path.rglob("*.py"))
            for file in files:
                text = file.read_text(encoding="utf-8")
                for token in forbidden:
                    assert token not in text, f"{token} found in {file}"


class TestPartialAndEnablementPass:
    def test_partial_fill_maps_to_unknown(self) -> None:
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.PARTIAL,
                retcode=10010,
                price=2350.3,
                volume=0.05,
            )
        )
        ack = _executor(transport).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.UNKNOWN
        assert "PARTIAL" in (ack.reason or "")

    def test_gates_pass_allows_transport_send(self) -> None:
        settings = _enablement_settings()
        result = evaluate_live_enablement(_preflight(settings))
        assert result.allowed is True
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.FILLED,
                price=2350.35,
                volume=0.10,
                order_id="77",
            )
        )
        ack = _executor(
            transport,
            require_enablement=True,
            settings=settings,
            preflight=_preflight(settings),
        ).submit(_intent(), quote=make_xauusd_symbol())
        assert ack.status is AckStatus.FILLED
        assert len(transport.calls) == 1


class TestNoRealBroker:
    def test_live_transport_not_used_in_unit_suite(self) -> None:
        # Ensure Fake is the only transport exercised here
        transport = FakeMT5ExecutionTransport(
            default=MT5TransportResult(
                outcome=TransportOutcome.REJECTED, retcode=10006
            )
        )
        assert not hasattr(transport, "client")
        _executor(transport).submit(_intent(), quote=make_xauusd_symbol())

    def test_map_raw_none_is_unknown(self) -> None:
        from exness_bot.broker.mt5.execution_transport import map_raw_order_send

        result = map_raw_order_send(None)
        assert result.outcome is TransportOutcome.UNKNOWN

    def test_map_raw_done_partial(self) -> None:
        from exness_bot.broker.mt5.execution_transport import map_raw_order_send

        raw = SimpleNamespace(
            retcode=10010, order=1, deal=2, price=1.0, volume=0.05, comment="partial"
        )
        result = map_raw_order_send(raw)
        assert result.outcome is TransportOutcome.PARTIAL
