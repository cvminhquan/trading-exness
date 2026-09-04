"""Demo-controlled enablement gates — TRADING_ENV=demo only. Fail-closed."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import structlog

from exness_bot.config.live_enablement import MT5_EXECUTOR_IMPLEMENTED
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.domain.execution_validation import (
    validate_quote,
    validate_stops_metadata,
    validate_volume,
)
from exness_bot.domain.models import SymbolInfo
from exness_bot.paper_execution.broker_query import BrokerExecutionQuery
from exness_bot.paper_execution.contract import IntentLifecycle, IntentRecord

logger = structlog.get_logger(__name__)

_FORBIDDEN_ENVS = frozenset({"live", "production", "real", "prod"})
_REQUIRED_ENV = "demo"


class DemoGateName(StrEnum):
    TRADING_ENV = "trading_env_demo"
    KILL_SWITCH = "kill_switch"
    DEMO_APPROVAL = "demo_approval"
    LEGACY_ISOLATION = "legacy_isolation"
    BROKER_IDENTITY = "broker_identity"
    ACCOUNT_TRADE_MODE = "account_trade_mode"
    SYMBOL_METADATA = "symbol_metadata"
    QUOTE_FRESHNESS = "quote_freshness"
    INTENT_STORE = "intent_store"
    EXECUTOR_CAPABILITY = "executor_capability"
    ONE_SHOT_GUARD = "one_shot_guard"


@dataclass(frozen=True)
class DemoGateResult:
    gate: DemoGateName
    allowed: bool
    reason: str


@dataclass(frozen=True)
class DemoEnablementResult:
    allowed: bool
    gates: tuple[DemoGateResult, ...]
    blocking_reasons: tuple[str, ...]
    evaluated_at: datetime
    message: str
    trading_env: str
    kill_switch_enabled: bool
    approval_active: bool
    approval_consumed: bool


@dataclass
class DemoPreflightContext:
    settings: Settings
    symbol_info: SymbolInfo | None = None
    intents: Sequence[IntentRecord] = ()
    intent_store_error: str | None = None
    broker_query: BrokerExecutionQuery | None = None
    broker_login: int | None = None
    broker_server: str | None = None
    account_trade_mode: str | None = None
    quote_fresh: bool | None = None
    quote_age_seconds: float | None = None
    approval: OneShotApproval | None = None
    prior_submission_count: int = 0
    evaluated_at: datetime | None = None


def evaluate_demo_controlled_enablement(
    context: DemoPreflightContext,
) -> DemoEnablementResult:
    """
    Fail-closed gates for Phase 12.4 controlled DEMO smoke.

    Requires TRADING_ENV=demo. Rejects live/production/real.
    Separate from Phase 12.2 live evaluator (does not weaken it).
    """
    settings = context.settings
    now = context.evaluated_at or datetime.now(tz=UTC)
    gates: list[DemoGateResult] = []

    env = (settings.trading_env or "").strip().lower()
    if not env:
        gates.append(
            DemoGateResult(
                DemoGateName.TRADING_ENV,
                False,
                "TRADING_ENV missing — requires TRADING_ENV=demo.",
            )
        )
    elif env in _FORBIDDEN_ENVS:
        gates.append(
            DemoGateResult(
                DemoGateName.TRADING_ENV,
                False,
                f"TRADING_ENV={env!r} forbidden for controlled DEMO.",
            )
        )
    elif env != _REQUIRED_ENV:
        gates.append(
            DemoGateResult(
                DemoGateName.TRADING_ENV,
                False,
                f"TRADING_ENV={env!r}; controlled DEMO requires explicit 'demo'.",
            )
        )
    else:
        gates.append(DemoGateResult(DemoGateName.TRADING_ENV, True, "TRADING_ENV=demo."))

    if settings.live_kill_switch:
        gates.append(
            DemoGateResult(
                DemoGateName.KILL_SWITCH,
                False,
                "LIVE_KILL_SWITCH=true — controlled demo blocked.",
            )
        )
    else:
        gates.append(
            DemoGateResult(
                DemoGateName.KILL_SWITCH,
                True,
                "LIVE_KILL_SWITCH=false for one-shot demo only.",
            )
        )

    approval = context.approval
    if approval is None or not approval.active:
        gates.append(
            DemoGateResult(
                DemoGateName.DEMO_APPROVAL,
                False,
                "LIVE_DEMO_APPROVAL missing/false — operator approval required.",
            )
        )
    elif approval.consumed:
        gates.append(
            DemoGateResult(
                DemoGateName.DEMO_APPROVAL,
                False,
                "LIVE_DEMO_APPROVAL already consumed — one-shot exhausted.",
            )
        )
    else:
        gates.append(
            DemoGateResult(
                DemoGateName.DEMO_APPROVAL,
                True,
                "LIVE_DEMO_APPROVAL active (not yet consumed).",
            )
        )

    if settings.allow_legacy_run:
        gates.append(
            DemoGateResult(
                DemoGateName.LEGACY_ISOLATION,
                False,
                "ALLOW_LEGACY_RUN=true — legacy path must be disabled.",
            )
        )
    else:
        gates.append(
            DemoGateResult(DemoGateName.LEGACY_ISOLATION, True, "ALLOW_LEGACY_RUN=false.")
        )

    gates.append(_gate_demo_identity(settings, context))
    gates.append(_gate_account_trade_mode(context))
    gates.append(_gate_symbol(context.symbol_info))
    gates.append(_gate_quote_freshness(context))
    gates.append(_gate_intent_store(context))

    if not MT5_EXECUTOR_IMPLEMENTED:
        gates.append(
            DemoGateResult(
                DemoGateName.EXECUTOR_CAPABILITY,
                False,
                "MT5Executor not implemented.",
            )
        )
    else:
        gates.append(
            DemoGateResult(DemoGateName.EXECUTOR_CAPABILITY, True, "MT5Executor available.")
        )

    if context.prior_submission_count >= 1:
        gates.append(
            DemoGateResult(
                DemoGateName.ONE_SHOT_GUARD,
                False,
                "Prior controlled demo submission recorded — second order blocked.",
            )
        )
    else:
        gates.append(
            DemoGateResult(
                DemoGateName.ONE_SHOT_GUARD,
                True,
                "No prior controlled demo submission in guard ledger.",
            )
        )

    allowed = all(g.allowed for g in gates)
    blocking = tuple(f"{g.gate.value}: {g.reason}" for g in gates if not g.allowed)
    message = (
        "Controlled DEMO enablement PASSED (one-shot only)."
        if allowed
        else "Controlled DEMO enablement BLOCKED."
    )

    result = DemoEnablementResult(
        allowed=allowed,
        gates=tuple(gates),
        blocking_reasons=blocking,
        evaluated_at=now,
        message=message,
        trading_env=env,
        kill_switch_enabled=settings.live_kill_switch,
        approval_active=bool(approval and approval.active),
        approval_consumed=bool(approval and approval.consumed),
    )
    for gate in result.gates:
        logger.info(
            "demo_preflight",
            gate=gate.gate.value,
            status="PASS" if gate.allowed else "BLOCKED",
            reason=gate.reason,
        )
    return result


def _gate_demo_identity(
    settings: Settings,
    context: DemoPreflightContext,
) -> DemoGateResult:
    allowlist = settings.demo_account_allowlist_set or settings.live_account_allowlist_set
    if not allowlist:
        return DemoGateResult(
            DemoGateName.BROKER_IDENTITY,
            False,
            "DEMO_ACCOUNT_ALLOWLIST (or LIVE_ACCOUNT_ALLOWLIST) empty.",
        )
    login = context.broker_login
    if login is None:
        login = settings.mt5_demo_login or settings.mt5_login
    if login is None:
        return DemoGateResult(
            DemoGateName.BROKER_IDENTITY,
            False,
            "Demo broker login unavailable.",
        )
    if str(login) not in allowlist:
        return DemoGateResult(
            DemoGateName.BROKER_IDENTITY,
            False,
            f"Demo login mismatch allowlist (masked={_mask(login)}).",
        )
    server_allow = settings.demo_server_allowlist_set or settings.live_server_allowlist_set
    server = (
        context.broker_server
        or settings.mt5_demo_server
        or settings.mt5_server
        or ""
    ).strip()
    if server_allow and server not in server_allow:
        return DemoGateResult(
            DemoGateName.BROKER_IDENTITY,
            False,
            "Demo server does not match allowlist.",
        )
    return DemoGateResult(
        DemoGateName.BROKER_IDENTITY,
        True,
        f"Demo identity matches allowlist (masked={_mask(login)}).",
    )


def _gate_account_trade_mode(context: DemoPreflightContext) -> DemoGateResult:
    mode = (context.account_trade_mode or "").strip().lower()
    if not mode:
        return DemoGateResult(
            DemoGateName.ACCOUNT_TRADE_MODE,
            False,
            "Account trade_mode unavailable — cannot verify DEMO.",
        )
    if mode != "demo":
        return DemoGateResult(
            DemoGateName.ACCOUNT_TRADE_MODE,
            False,
            f"Account trade_mode={mode!r} is not DEMO — BLOCK.",
        )
    return DemoGateResult(
        DemoGateName.ACCOUNT_TRADE_MODE,
        True,
        "Account trade_mode=demo verified.",
    )


def _gate_symbol(symbol: SymbolInfo | None) -> DemoGateResult:
    if symbol is None:
        return DemoGateResult(
            DemoGateName.SYMBOL_METADATA,
            False,
            "Symbol metadata unavailable.",
        )
    quote = validate_quote(symbol)
    if not quote.ok:
        return DemoGateResult(
            DemoGateName.SYMBOL_METADATA,
            False,
            f"Quote invalid: {quote.code.value}",
        )
    stops = validate_stops_metadata(symbol)
    if not stops.ok:
        return DemoGateResult(
            DemoGateName.SYMBOL_METADATA,
            False,
            f"Stops/freeze: {stops.code.value}",
        )
    vol = validate_volume(symbol.volume_min, symbol)
    if not vol.ok:
        return DemoGateResult(
            DemoGateName.SYMBOL_METADATA,
            False,
            f"Volume: {vol.code.value}",
        )
    return DemoGateResult(
        DemoGateName.SYMBOL_METADATA,
        True,
        f"Symbol {symbol.symbol} metadata OK.",
    )


def _gate_quote_freshness(context: DemoPreflightContext) -> DemoGateResult:
    if context.quote_fresh is None:
        return DemoGateResult(
            DemoGateName.QUOTE_FRESHNESS,
            False,
            "Quote freshness not evaluated.",
        )
    if not context.quote_fresh:
        return DemoGateResult(
            DemoGateName.QUOTE_FRESHNESS,
            False,
            f"Quote STALE or UNAVAILABLE (age_seconds={context.quote_age_seconds}).",
        )
    return DemoGateResult(
        DemoGateName.QUOTE_FRESHNESS,
        True,
        f"Quote fresh (age_seconds={context.quote_age_seconds}).",
    )


def _gate_intent_store(context: DemoPreflightContext) -> DemoGateResult:
    if context.intent_store_error:
        return DemoGateResult(
            DemoGateName.INTENT_STORE,
            False,
            f"Intent store unsafe: {context.intent_store_error}",
        )
    unknown = sum(1 for i in context.intents if i.lifecycle == IntentLifecycle.UNKNOWN)
    inflight = sum(1 for i in context.intents if i.lifecycle == IntentLifecycle.IN_FLIGHT)
    if inflight:
        return DemoGateResult(
            DemoGateName.INTENT_STORE,
            False,
            f"{inflight} IN_FLIGHT — recover before demo smoke.",
        )
    if unknown:
        return DemoGateResult(
            DemoGateName.INTENT_STORE,
            False,
            f"{unknown} unresolved UNKNOWN — demo smoke blocked.",
        )
    return DemoGateResult(DemoGateName.INTENT_STORE, True, "Intent store healthy.")


def _mask(login: int) -> str:
    text = str(login)
    if len(text) <= 4:
        return "****"
    return f"***{text[-4:]}"
