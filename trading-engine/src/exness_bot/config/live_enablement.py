"""Phase 12.2 — Live enablement gates & preflight. Non-trading. Fail-closed."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import structlog

from exness_bot.config.settings import ExecutionMode, Settings
from exness_bot.domain.execution_validation import (
    validate_quote,
    validate_stops_metadata,
    validate_volume,
)
from exness_bot.domain.models import SymbolInfo
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionQuery,
    IntentReconcileStatus,
    UnavailableBrokerExecutionQuery,
)
from exness_bot.paper_execution.contract import IntentLifecycle, IntentRecord
from exness_bot.paper_execution.errors import CorruptStateError, UnsupportedSchemaError
from exness_bot.paper_execution.state import FilePaperStateStore, PaperStateStore

logger = structlog.get_logger(__name__)

# Phase 12.3: MT5Executor exists behind ExecutionPort — still fail-closed by gates.
MT5_EXECUTOR_IMPLEMENTED = True

TRUE_VALUES = frozenset({"true"})
FALSE_VALUES = frozenset({"false"})


class LiveGateName(StrEnum):
    EXECUTION_MODE = "execution_mode"
    ALLOW_LIVE_TRADING = "allow_live_trading"
    TRADING_ENV = "trading_env"
    BROKER_IDENTITY = "broker_identity"
    SYMBOL_METADATA = "symbol_metadata"
    RISK_CONFIG = "risk_config"
    INTENT_STORE = "intent_store"
    UNKNOWN_RECONCILIATION = "unknown_reconciliation"
    LEGACY_ISOLATION = "legacy_isolation"
    KILL_SWITCH = "kill_switch"
    EXECUTOR_CAPABILITY = "executor_capability"


class LiveReadinessStatus(StrEnum):
    """
    Distinguishes configuration preflight from executable live trading.

    LIVE_DISABLED — default; live not allowed
    PREFLIGHT_READY — configuration gates pass, but execution still blocked
    BLOCKED — one or more gates failed
    NOT_IMPLEMENTED — live executor does not exist
    """

    LIVE_DISABLED = "LIVE_DISABLED"
    PREFLIGHT_READY = "PREFLIGHT_READY"
    BLOCKED = "BLOCKED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class GateSeverity(StrEnum):
    BLOCKING = "BLOCKING"
    INFO = "INFO"


@dataclass(frozen=True)
class LiveGateResult:
    gate: LiveGateName
    allowed: bool
    reason: str
    severity: GateSeverity = GateSeverity.BLOCKING


@dataclass(frozen=True)
class LiveEnablementResult:
    """
    Full live enablement evaluation.

    configuration_preflight_ready — all config gates except executor capability
    execution_capability — MT5Executor class available (True from Phase 12.3)
    allowed — ALL gates including capability; defaults still False (kill switch etc.)
    Autonomous live loop remains unwired regardless of allowed.
    """

    allowed: bool
    configuration_preflight_ready: bool
    execution_capability: bool
    readiness_status: LiveReadinessStatus
    gates: tuple[LiveGateResult, ...]
    blocking_reasons: tuple[str, ...]
    evaluated_at: datetime
    unresolved_unknown_count: int = 0
    kill_switch_enabled: bool = True
    legacy_run_allowed: bool = False
    mt5_executor_implemented: bool = False
    message: str = ""


@dataclass
class LivePreflightContext:
    """Inputs for gate evaluation — no broker mutations."""

    settings: Settings
    requested_execution_mode: str | None = None
    symbol_info: SymbolInfo | None = None
    intents: Sequence[IntentRecord] = ()
    intent_store_error: str | None = None
    broker_query: BrokerExecutionQuery | None = None
    broker_login: int | None = None
    broker_server: str | None = None
    evaluated_at: datetime | None = None


# Backward-compatible Phase 11.9 surface
REQUIRED_FUTURE_LIVE_GATES: tuple[str, ...] = tuple(g.value for g in LiveGateName)


@dataclass(frozen=True)
class LiveGateAssessment:
    """Legacy Phase 11.9 assessment shape."""

    allowed: bool
    missing_gates: tuple[str, ...]
    message: str


def parse_strict_bool(raw: object, *, field_name: str) -> bool:
    """Only 'true' / 'false' (case-insensitive). Anything else fails closed via ValueError."""
    if isinstance(raw, bool):
        return raw
    if not isinstance(raw, str):
        msg = f"{field_name}: expected true|false, got {type(raw).__name__}"
        raise ValueError(msg)
    lowered = raw.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    msg = f"{field_name}: expected true|false, got {raw!r}"
    raise ValueError(msg)


def evaluate_live_enablement(context: LivePreflightContext) -> LiveEnablementResult:
    """
    Evaluate all live enablement gates. Fail-closed. Never submits orders.

    Even if configuration_preflight_ready is True, allowed stays False while
    MT5Executor is NOT IMPLEMENTED.
    """
    now = context.evaluated_at or datetime.now(tz=UTC)
    gates: list[LiveGateResult] = []
    settings = context.settings

    requested_mode = (
        context.requested_execution_mode
        if context.requested_execution_mode is not None
        else settings.execution_mode.value
    ).strip().lower()

    # --- Gate A: Execution mode ---
    if requested_mode == ExecutionMode.LIVE.value:
        gates.append(
            LiveGateResult(
                LiveGateName.EXECUTION_MODE,
                True,
                "EXECUTION_MODE=live requested (preflight only — not operational).",
            )
        )
    else:
        gates.append(
            LiveGateResult(
                LiveGateName.EXECUTION_MODE,
                False,
                f"EXECUTION_MODE={requested_mode!r}; live required for future live path.",
            )
        )

    # --- Gate B: Explicit allow live trading ---
    if settings.allow_live_trading:
        gates.append(
            LiveGateResult(
                LiveGateName.ALLOW_LIVE_TRADING,
                True,
                "ALLOW_LIVE_TRADING=true.",
            )
        )
    else:
        gates.append(
            LiveGateResult(
                LiveGateName.ALLOW_LIVE_TRADING,
                False,
                "ALLOW_LIVE_TRADING is false or unset.",
            )
        )

    # --- Gate C: Trading environment ---
    trading_env = settings.trading_env.strip().lower()
    if trading_env == "live":
        gates.append(
            LiveGateResult(
                LiveGateName.TRADING_ENV,
                True,
                "TRADING_ENV=live.",
            )
        )
    else:
        gates.append(
            LiveGateResult(
                LiveGateName.TRADING_ENV,
                False,
                f"TRADING_ENV={trading_env!r}; explicit 'live' required.",
            )
        )

    # --- Gate D: Broker account identity ---
    gates.append(_gate_broker_identity(settings, context))

    # --- Gate E: Symbol metadata ---
    gates.append(_gate_symbol_metadata(context.symbol_info))

    # --- Gate F: Risk config ---
    gates.append(_gate_risk_config(settings))

    # --- Gate G: Intent store ---
    intent_gate, unknown_count = _gate_intent_store(context)
    gates.append(intent_gate)

    # --- Gate H: Reconciliation ---
    gates.append(_gate_reconciliation(context, unknown_count))

    # --- Gate I: Legacy isolation ---
    if settings.allow_legacy_run:
        gates.append(
            LiveGateResult(
                LiveGateName.LEGACY_ISOLATION,
                False,
                "ALLOW_LEGACY_RUN=true — legacy exness-bot run path must be disabled.",
            )
        )
    else:
        gates.append(
            LiveGateResult(
                LiveGateName.LEGACY_ISOLATION,
                True,
                "ALLOW_LEGACY_RUN=false — legacy path sealed.",
            )
        )

    # --- Gate J: Kill switch (true = BLOCK) ---
    if settings.live_kill_switch:
        gates.append(
            LiveGateResult(
                LiveGateName.KILL_SWITCH,
                False,
                "LIVE_KILL_SWITCH=true — live blocked.",
            )
        )
    else:
        gates.append(
            LiveGateResult(
                LiveGateName.KILL_SWITCH,
                True,
                "LIVE_KILL_SWITCH=false (does not alone enable live).",
            )
        )

    # --- Gate K: Executor capability (Phase 12.3: implemented, still gated) ---
    if MT5_EXECUTOR_IMPLEMENTED:
        gates.append(
            LiveGateResult(
                LiveGateName.EXECUTOR_CAPABILITY,
                True,
                "MT5Executor implemented — capability present; other gates still required.",
                severity=GateSeverity.BLOCKING,
            )
        )
    else:
        gates.append(
            LiveGateResult(
                LiveGateName.EXECUTOR_CAPABILITY,
                False,
                "MT5Executor = NOT IMPLEMENTED — actual live execution blocked.",
                severity=GateSeverity.BLOCKING,
            )
        )

    config_gates = [g for g in gates if g.gate != LiveGateName.EXECUTOR_CAPABILITY]
    configuration_preflight_ready = all(g.allowed for g in config_gates)
    execution_capability = MT5_EXECUTOR_IMPLEMENTED and all(
        g.allowed for g in gates if g.gate == LiveGateName.EXECUTOR_CAPABILITY
    )
    allowed = configuration_preflight_ready and execution_capability

    blocking = tuple(f"{g.gate.value}: {g.reason}" for g in gates if not g.allowed)

    if not configuration_preflight_ready:
        readiness = LiveReadinessStatus.BLOCKED
        message = "Live enablement BLOCKED — one or more configuration gates failed."
    elif not execution_capability:
        readiness = LiveReadinessStatus.NOT_IMPLEMENTED
        message = (
            "Configuration preflight READY, but LIVE EXECUTION NOT IMPLEMENTED "
            "(MT5Executor missing). Not LIVE READY."
        )
    elif allowed:
        readiness = LiveReadinessStatus.PREFLIGHT_READY
        message = (
            "Enablement gates PASSED. MT5Executor boundary available. "
            "Autonomous live trading loop is NOT activated. "
            "Do not treat as production LIVE READY."
        )
    else:
        readiness = LiveReadinessStatus.LIVE_DISABLED
        message = "Live disabled."

    if (
        not any(g.gate == LiveGateName.EXECUTION_MODE and g.allowed for g in gates)
        and readiness == LiveReadinessStatus.BLOCKED
        and all(
            not g.allowed
            for g in gates
            if g.gate
            in {
                LiveGateName.EXECUTION_MODE,
                LiveGateName.ALLOW_LIVE_TRADING,
                LiveGateName.KILL_SWITCH,
            }
        )
    ):
        readiness = LiveReadinessStatus.LIVE_DISABLED
        message = "Live disabled by default (fail-closed)."

    result = LiveEnablementResult(
        allowed=allowed,
        configuration_preflight_ready=configuration_preflight_ready,
        execution_capability=execution_capability,
        readiness_status=readiness,
        gates=tuple(gates),
        blocking_reasons=blocking,
        evaluated_at=now,
        unresolved_unknown_count=unknown_count,
        kill_switch_enabled=settings.live_kill_switch,
        legacy_run_allowed=settings.allow_legacy_run,
        mt5_executor_implemented=MT5_EXECUTOR_IMPLEMENTED,
        message=message,
    )

    for gate in result.gates:
        logger.info(
            "live_preflight",
            gate=gate.gate.value,
            status="PASS" if gate.allowed else "BLOCKED",
            reason=gate.reason,
        )
    logger.info(
        "live_preflight_summary",
        readiness=result.readiness_status.value,
        configuration_preflight_ready=result.configuration_preflight_ready,
        execution_capability=result.execution_capability,
        allowed=result.allowed,
        unresolved_unknown=result.unresolved_unknown_count,
    )
    return result


def evaluate_future_live_gates(settings: Settings) -> LiveGateAssessment:
    """Phase 11.9-compatible wrapper — always allowed=False."""
    result = evaluate_live_enablement(LivePreflightContext(settings=settings))
    missing = tuple(g.gate.value for g in result.gates if not g.allowed)
    return LiveGateAssessment(
        allowed=False,
        missing_gates=missing,
        message=result.message,
    )


def assert_phase11_live_disabled(settings: Settings) -> None:
    assessment = evaluate_future_live_gates(settings)
    if assessment.allowed:
        msg = "Invariant violated: Phase 11/12 live gates must never allow trading."
        raise RuntimeError(msg)


def assert_live_execution_not_operational(settings: Settings) -> None:
    """
    Runtime guard — paper factory / research path must not run EXECUTION_MODE=live.

    Phase 12.3: MT5Executor exists but is NOT wired into build_execution_service.
    Autonomous live trading remains disabled.
    """
    if settings.execution_mode != ExecutionMode.PAPER:
        msg = (
            f"EXECUTION_MODE={settings.execution_mode.value} is not operational. "
            "Only paper execution is wired into the research runtime. "
            "MT5Executor exists as an execution boundary but live trading is DISABLED "
            "by default (enablement gates + no autonomous loop)."
        )
        raise RuntimeError(msg)


def load_intent_store_for_preflight(
    path: Path | None,
) -> tuple[tuple[IntentRecord, ...], str | None]:
    """Load intents read-only for Gate G. Returns (intents, error_message)."""
    if path is None or not path.is_file():
        return (), None
    try:
        store: PaperStateStore = FilePaperStateStore(path)
        snap = store.load()
        return snap.intents, None
    except (CorruptStateError, UnsupportedSchemaError, OSError) as exc:
        return (), str(exc)


def _gate_broker_identity(
    settings: Settings,
    context: LivePreflightContext,
) -> LiveGateResult:
    allowlist = settings.live_account_allowlist_set
    server_allow = settings.live_server_allowlist_set
    if not allowlist:
        return LiveGateResult(
            LiveGateName.BROKER_IDENTITY,
            False,
            "LIVE_ACCOUNT_ALLOWLIST empty — broker identity not configured.",
        )
    login = context.broker_login
    if login is None:
        login = settings.mt5_live_login or settings.mt5_login
    if login is None:
        return LiveGateResult(
            LiveGateName.BROKER_IDENTITY,
            False,
            "Broker account login unavailable for identity check.",
        )
    if str(login) not in allowlist:
        return LiveGateResult(
            LiveGateName.BROKER_IDENTITY,
            False,
            f"Broker login does not match LIVE_ACCOUNT_ALLOWLIST (masked={_mask_login(login)}).",
        )
    server = (
        context.broker_server or settings.mt5_live_server or settings.mt5_server or ""
    ).strip()
    if server_allow and server not in server_allow:
        return LiveGateResult(
            LiveGateName.BROKER_IDENTITY,
            False,
            "Broker server does not match LIVE_SERVER_ALLOWLIST.",
        )
    return LiveGateResult(
        LiveGateName.BROKER_IDENTITY,
        True,
        f"Broker identity matches allowlist (masked={_mask_login(login)}).",
    )


def _gate_symbol_metadata(symbol: SymbolInfo | None) -> LiveGateResult:
    if symbol is None:
        return LiveGateResult(
            LiveGateName.SYMBOL_METADATA,
            False,
            "Symbol metadata unavailable for live preflight.",
        )
    quote = validate_quote(symbol)
    if not quote.ok:
        return LiveGateResult(
            LiveGateName.SYMBOL_METADATA,
            False,
            f"Quote invalid: {quote.code.value} — {quote.message}",
        )
    stops = validate_stops_metadata(symbol)
    if not stops.ok:
        return LiveGateResult(
            LiveGateName.SYMBOL_METADATA,
            False,
            f"Stops/freeze metadata: {stops.code.value} — {stops.message}",
        )
    # Volume constraints must be present (use min volume as probe)
    vol = validate_volume(symbol.volume_min, symbol)
    if not vol.ok and vol.code.value.startswith("VOLUME"):
        return LiveGateResult(
            LiveGateName.SYMBOL_METADATA,
            False,
            f"Volume metadata: {vol.code.value} — {vol.message}",
        )
    if symbol.volume_min <= 0 or symbol.volume_step <= 0 or symbol.volume_max <= 0:
        return LiveGateResult(
            LiveGateName.SYMBOL_METADATA,
            False,
            "Invalid volume min/step/max configuration.",
        )
    return LiveGateResult(
        LiveGateName.SYMBOL_METADATA,
        True,
        f"Symbol {symbol.symbol} quote/stops/volume metadata OK.",
    )


def _gate_risk_config(settings: Settings) -> LiveGateResult:
    problems: list[str] = []
    if settings.risk_per_trade_pct <= 0 or settings.risk_per_trade_pct > 5:
        problems.append("RISK_PER_TRADE_PCT out of range")
    if settings.max_daily_loss_pct <= 0:
        problems.append("MAX_DAILY_LOSS_PCT invalid")
    if settings.max_drawdown_pct <= 0:
        problems.append("MAX_DRAWDOWN_PCT invalid")
    if settings.max_open_positions < 1:
        problems.append("MAX_OPEN_POSITIONS invalid")
    if settings.max_position_lots <= 0:
        problems.append("MAX_POSITION_LOTS invalid")
    if settings.max_spread_points < 1:
        problems.append("MAX_SPREAD_POINTS invalid")
    if settings.atr_sl_multiplier <= 0 or settings.reward_risk_ratio <= 0:
        problems.append("ATR_SL_MULTIPLIER / REWARD_RISK_RATIO invalid")
    if problems:
        return LiveGateResult(
            LiveGateName.RISK_CONFIG,
            False,
            "; ".join(problems),
        )
    return LiveGateResult(
        LiveGateName.RISK_CONFIG,
        True,
        "Risk configuration present and within declared bounds.",
    )


def _gate_intent_store(context: LivePreflightContext) -> tuple[LiveGateResult, int]:
    if context.intent_store_error:
        return (
            LiveGateResult(
                LiveGateName.INTENT_STORE,
                False,
                f"Intent store unsafe: {context.intent_store_error}",
            ),
            0,
        )
    unknown = sum(
        1 for item in context.intents if item.lifecycle == IntentLifecycle.UNKNOWN
    )
    inflight = sum(
        1 for item in context.intents if item.lifecycle == IntentLifecycle.IN_FLIGHT
    )
    if inflight > 0:
        return (
            LiveGateResult(
                LiveGateName.INTENT_STORE,
                False,
                f"{inflight} IN_FLIGHT intent(s) — must recover to UNKNOWN before live.",
            ),
            unknown,
        )
    if unknown > 0:
        return (
            LiveGateResult(
                LiveGateName.INTENT_STORE,
                False,
                f"{unknown} unresolved UNKNOWN intent(s) — live not allowed.",
            ),
            unknown,
        )
    return (
        LiveGateResult(
            LiveGateName.INTENT_STORE,
            True,
            "Intent store healthy — no IN_FLIGHT/UNKNOWN blockers.",
        ),
        0,
    )


def _gate_reconciliation(
    context: LivePreflightContext,
    unknown_count: int,
) -> LiveGateResult:
    query = context.broker_query
    if query is None or isinstance(query, UnavailableBrokerExecutionQuery):
        return LiveGateResult(
            LiveGateName.UNKNOWN_RECONCILIATION,
            False,
            "BrokerExecutionQuery unavailable — reconciliation gate fail-closed.",
        )

    unknowns = [
        item for item in context.intents if item.lifecycle == IntentLifecycle.UNKNOWN
    ]
    if not unknowns:
        return LiveGateResult(
            LiveGateName.UNKNOWN_RECONCILIATION,
            True,
            "Broker query available; no UNKNOWN intents to reconcile.",
        )

    for intent in unknowns:
        result = query.find_execution(intent)
        if result.status == IntentReconcileStatus.UNAVAILABLE:
            return LiveGateResult(
                LiveGateName.UNKNOWN_RECONCILIATION,
                False,
                "Broker reconciliation UNAVAILABLE.",
            )
        if result.status == IntentReconcileStatus.AMBIGUOUS:
            return LiveGateResult(
                LiveGateName.UNKNOWN_RECONCILIATION,
                False,
                "Broker reconciliation AMBIGUOUS — blocks live.",
            )
        # NOT_FOUND or CONFIRMED_* while row still UNKNOWN → still unresolved for live
        return LiveGateResult(
            LiveGateName.UNKNOWN_RECONCILIATION,
            False,
            f"UNKNOWN unresolved ({result.status.value}) — live blocked.",
        )

    return LiveGateResult(
        LiveGateName.UNKNOWN_RECONCILIATION,
        False,
        f"{unknown_count} unresolved UNKNOWN — live not allowed.",
    )


def _mask_login(login: int) -> str:
    text = str(login)
    if len(text) <= 4:
        return "****"
    return f"***{text[-4:]}"


def result_to_dict(result: LiveEnablementResult) -> dict[str, object]:
    """JSON-serializable readiness payload (API / CLI)."""
    return {
        "allowed": result.allowed,
        "configurationPreflightReady": result.configuration_preflight_ready,
        "executionCapability": result.execution_capability,
        "readinessStatus": result.readiness_status.value,
        "message": result.message,
        "evaluatedAt": result.evaluated_at.isoformat(),
        "unresolvedUnknownCount": result.unresolved_unknown_count,
        "killSwitchEnabled": result.kill_switch_enabled,
        "legacyRunAllowed": result.legacy_run_allowed,
        "mt5ExecutorImplemented": result.mt5_executor_implemented,
        "blockingReasons": list(result.blocking_reasons),
        "gates": [
            {
                "name": g.gate.value,
                "allowed": g.allowed,
                "reason": g.reason,
                "severity": g.severity.value,
            }
            for g in result.gates
        ],
    }


__all__ = [
    "MT5_EXECUTOR_IMPLEMENTED",
    "REQUIRED_FUTURE_LIVE_GATES",
    "GateSeverity",
    "LiveEnablementResult",
    "LiveGateAssessment",
    "LiveGateName",
    "LiveGateResult",
    "LivePreflightContext",
    "LiveReadinessStatus",
    "assert_live_execution_not_operational",
    "assert_phase11_live_disabled",
    "evaluate_future_live_gates",
    "evaluate_live_enablement",
    "load_intent_store_for_preflight",
    "parse_strict_bool",
    "result_to_dict",
]
