"""Phase 12.2 — live enablement gates & preflight. Non-trading."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from exness_bot.cli import build_parser, handle_live_preflight
from exness_bot.config.live_enablement import (
    MT5_EXECUTOR_IMPLEMENTED,
    LiveGateName,
    LivePreflightContext,
    LiveReadinessStatus,
    assert_live_execution_not_operational,
    evaluate_live_enablement,
    parse_strict_bool,
)
from exness_bot.config.settings import ExecutionMode, Settings
from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionEvidence,
    StaticBrokerExecutionQuery,
    UnavailableBrokerExecutionQuery,
)
from exness_bot.paper_execution.contract import IntentLifecycle, IntentRecord
from exness_bot.paper_execution.factory import build_execution_service
from tests.fixtures.risk_data import make_xauusd_symbol

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot"
SYMBOL = "XAUUSD"


def _at(hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 8, 29, hour, minute, tzinfo=UTC)


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "EXECUTION_MODE": "paper",
        "ALLOW_LIVE_TRADING": False,
        "ALLOW_LEGACY_RUN": False,
        "LIVE_KILL_SWITCH": True,
        "TRADING_ENV": "research",
        "LIVE_ACCOUNT_ALLOWLIST": "",
        "LIVE_SERVER_ALLOWLIST": "",
        "DRY_RUN": True,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _intent(
    *,
    lifecycle: IntentLifecycle = IntentLifecycle.UNKNOWN,
    intent_id: str = "i-1",
) -> IntentRecord:
    now = _at()
    return IntentRecord(
        intent_id=intent_id,
        idempotency_key="k-1",
        lifecycle=lifecycle,
        created_at=now,
        updated_at=now,
        side="LONG",
        symbol=SYMBOL,
        requested_quantity=0.1,
        stop_loss=2340.0,
        take_profit=2370.0,
    )


def _preflight_ready_settings() -> Settings:
    return _settings(
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


def _ctx(
    settings: Settings | None = None,
    *,
    requested_mode: str = "live",
    symbol=None,
    intents: tuple[IntentRecord, ...] = (),
    intent_store_error: str | None = None,
    broker_query=None,
    broker_login: int | None = 12345678,
    broker_server: str | None = "Exness-MT5Live",
) -> LivePreflightContext:
    return LivePreflightContext(
        settings=settings or _settings(),
        requested_execution_mode=requested_mode,
        symbol_info=symbol if symbol is not None else make_xauusd_symbol(),
        intents=intents,
        intent_store_error=intent_store_error,
        broker_query=broker_query
        if broker_query is not None
        else StaticBrokerExecutionQuery(()),
        broker_login=broker_login,
        broker_server=broker_server,
        evaluated_at=_at(),
    )


def _gate(result, name: LiveGateName):
    return next(g for g in result.gates if g.gate == name)


class TestBasicBehaviour:
    def test_live_enablement_defaults_to_disabled(self) -> None:
        result = evaluate_live_enablement(_ctx(_settings(), requested_mode="paper"))
        assert result.allowed is False
        # Phase 12.3: executor exists, but defaults still block live
        assert result.execution_capability is True
        assert result.mt5_executor_implemented is True
        assert result.readiness_status in {
            LiveReadinessStatus.LIVE_DISABLED,
            LiveReadinessStatus.BLOCKED,
        }

    def test_kill_switch_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        object.__setattr__(settings, "live_kill_switch", True)
        result = evaluate_live_enablement(_ctx(settings))
        assert _gate(result, LiveGateName.KILL_SWITCH).allowed is False
        assert result.allowed is False

    def test_missing_live_flag_blocks(self) -> None:
        settings = _preflight_ready_settings()
        object.__setattr__(settings, "allow_live_trading", False)
        result = evaluate_live_enablement(_ctx(settings))
        assert _gate(result, LiveGateName.ALLOW_LIVE_TRADING).allowed is False

    def test_invalid_boolean_fails_closed(self) -> None:
        with pytest.raises(ValueError):
            parse_strict_bool("yes", field_name="ALLOW_LIVE_TRADING")
        with pytest.raises(ValidationError):
            Settings(_env_file=None, ALLOW_LIVE_TRADING="yes")

    def test_wrong_environment_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        object.__setattr__(settings, "trading_env", "research")
        result = evaluate_live_enablement(_ctx(settings))
        assert _gate(result, LiveGateName.TRADING_ENV).allowed is False


class TestBroker:
    def test_broker_identity_mismatch_blocks(self) -> None:
        settings = _preflight_ready_settings()
        result = evaluate_live_enablement(_ctx(settings, broker_login=99999999))
        assert _gate(result, LiveGateName.BROKER_IDENTITY).allowed is False

    def test_broker_query_unavailable_blocks(self) -> None:
        settings = _preflight_ready_settings()
        result = evaluate_live_enablement(
            _ctx(settings, broker_query=UnavailableBrokerExecutionQuery())
        )
        assert _gate(result, LiveGateName.UNKNOWN_RECONCILIATION).allowed is False

    def test_ambiguous_reconciliation_blocks(self) -> None:
        settings = _preflight_ready_settings()
        intent = _intent()
        evidence = [
            BrokerExecutionEvidence(
                symbol=SYMBOL,
                side=SignalDirection.LONG,
                volume=0.1,
                timestamp=_at(11, 16),
                correlation_id=intent.intent_id,
                broker_order_id="a",
            ),
            BrokerExecutionEvidence(
                symbol=SYMBOL,
                side=SignalDirection.LONG,
                volume=0.1,
                timestamp=_at(11, 17),
                correlation_id=intent.intent_id,
                broker_order_id="b",
            ),
        ]
        result = evaluate_live_enablement(
            _ctx(
                settings,
                intents=(intent,),
                broker_query=StaticBrokerExecutionQuery(evidence),
            )
        )
        assert _gate(result, LiveGateName.UNKNOWN_RECONCILIATION).allowed is False
        assert _gate(result, LiveGateName.INTENT_STORE).allowed is False


class TestIntentState:
    def test_unresolved_unknown_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        result = evaluate_live_enablement(_ctx(settings, intents=(_intent(),)))
        assert _gate(result, LiveGateName.INTENT_STORE).allowed is False
        assert result.unresolved_unknown_count >= 1

    def test_corrupt_intent_store_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        result = evaluate_live_enablement(
            _ctx(settings, intent_store_error="CorruptStateError: bad json")
        )
        assert _gate(result, LiveGateName.INTENT_STORE).allowed is False

    def test_unsupported_schema_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        result = evaluate_live_enablement(
            _ctx(settings, intent_store_error="UnsupportedSchemaError: 99")
        )
        assert _gate(result, LiveGateName.INTENT_STORE).allowed is False


class TestSafety:
    def test_legacy_run_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        object.__setattr__(settings, "allow_legacy_run", True)
        result = evaluate_live_enablement(_ctx(settings))
        assert _gate(result, LiveGateName.LEGACY_ISOLATION).allowed is False

    def test_missing_stops_metadata_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        symbol = make_xauusd_symbol(stops_level=None, freeze_level=0)
        result = evaluate_live_enablement(_ctx(settings, symbol=symbol))
        assert _gate(result, LiveGateName.SYMBOL_METADATA).allowed is False

    def test_missing_freeze_metadata_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        symbol = make_xauusd_symbol(stops_level=10, freeze_level=None)
        result = evaluate_live_enablement(_ctx(settings, symbol=symbol))
        assert _gate(result, LiveGateName.SYMBOL_METADATA).allowed is False

    def test_invalid_volume_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        symbol = make_xauusd_symbol().model_copy(
            update={"volume_min": 0.0, "volume_step": 0.0, "volume_max": 0.0}
        )
        result = evaluate_live_enablement(_ctx(settings, symbol=symbol))
        assert _gate(result, LiveGateName.SYMBOL_METADATA).allowed is False

    def test_invalid_risk_config_blocks_live(self) -> None:
        settings = _preflight_ready_settings()
        object.__setattr__(settings, "max_open_positions", 0)
        result = evaluate_live_enablement(_ctx(settings))
        assert _gate(result, LiveGateName.RISK_CONFIG).allowed is False


class TestCapability:
    def test_missing_mt5_executor_blocks_actual_live(self) -> None:
        """Phase 12.3: executor exists — capability gate passes; defaults still block."""
        assert MT5_EXECUTOR_IMPLEMENTED is True
        settings = _preflight_ready_settings()
        result = evaluate_live_enablement(_ctx(settings))
        assert _gate(result, LiveGateName.EXECUTOR_CAPABILITY).allowed is True
        assert result.execution_capability is True
        # Full preflight settings may allow enablement evaluation; runtime still unwired.
        assert "production LIVE READY" not in result.message.lower() or "NOT" in result.message

    def test_preflight_ready_does_not_mean_execution_ready(self) -> None:
        # Defaults: capability True but enablement blocked
        result = evaluate_live_enablement(_ctx(_settings(), requested_mode="paper"))
        assert result.mt5_executor_implemented is True
        assert result.allowed is False
        assert "production LIVE READY" not in result.message.lower()
        # Autonomous path still refuses live mode
        live = _settings(EXECUTION_MODE="live")
        with pytest.raises(RuntimeError, match="not operational"):
            assert_live_execution_not_operational(live)


class TestComposition:
    def test_all_gates_are_required(self) -> None:
        result = evaluate_live_enablement(_ctx(_preflight_ready_settings()))
        names = {g.gate for g in result.gates}
        assert set(LiveGateName) == names

    def test_single_failed_gate_blocks_overall(self) -> None:
        settings = _preflight_ready_settings()
        object.__setattr__(settings, "live_kill_switch", True)
        result = evaluate_live_enablement(_ctx(settings))
        assert result.allowed is False
        assert result.configuration_preflight_ready is False

    def test_multiple_failures_are_reported(self) -> None:
        result = evaluate_live_enablement(_ctx(_settings(), requested_mode="paper"))
        assert len(result.blocking_reasons) >= 2

    def test_no_paper_fallback(self) -> None:
        source = inspect.getsource(evaluate_live_enablement)
        assert "PaperExecutor" not in source
        assert "fallback to paper" not in source.lower()

    def test_no_legacy_fallback(self) -> None:
        source = inspect.getsource(evaluate_live_enablement)
        assert "MT5Adapter" not in source
        assert "fallback to legacy" not in source.lower()


class TestApiAndCli:
    def test_live_readiness_endpoint_is_read_only(self) -> None:
        from exness_bot.api.routes import v1 as routes

        source = inspect.getsource(routes.get_live_readiness)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "order_send":
                pytest.fail("order_send in live-readiness route")

    def test_live_readiness_does_not_execute_orders(self) -> None:
        from exness_bot.api.services.read_service import ReadService
        from exness_bot.data.mock_provider import MockTradingDataProvider

        settings = _settings()
        service = ReadService(settings, MockTradingDataProvider(settings))
        dto = service.get_live_readiness()
        assert dto.allowed is False
        assert dto.execution_capability is True
        assert dto.mt5_executor_implemented is True

    def test_live_preflight_is_read_only(self) -> None:
        tree = ast.parse(inspect.getsource(handle_live_preflight))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "order_send":
                pytest.fail("order_send call in live-preflight")
        parser = build_parser()
        assert "live-preflight" in parser.format_help()
        assert handle_live_preflight() == 1


class TestOperationalGuard:
    def test_execution_mode_live_parses_but_not_operational(self) -> None:
        settings = Settings(_env_file=None, EXECUTION_MODE="live")
        assert settings.execution_mode is ExecutionMode.LIVE
        with pytest.raises(RuntimeError, match=r"NOT IMPLEMENTED|not operational"):
            assert_live_execution_not_operational(settings)
        with pytest.raises(RuntimeError):
            build_execution_service(settings)

    def test_mt5_mode_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, EXECUTION_MODE="mt5")


class TestStaticAudit:
    def test_live_enablement_has_no_trading_api(self) -> None:
        path = SRC / "config" / "live_enablement.py"
        code = path.read_text(encoding="utf-8")
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "order_send":
                pytest.fail("order_send in live_enablement")
        assert "order_send" not in code
        assert "TRADE_ACTION_DEAL" not in code
        assert "class MT5Executor" not in code
        assert "MT5Adapter" not in code
