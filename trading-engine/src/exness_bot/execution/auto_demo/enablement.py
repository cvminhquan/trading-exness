"""Phase 17.3 autonomous DEMO enablement — sticky approval, no one-shot guard."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

import structlog

from exness_bot.config.live_enablement import MT5_EXECUTOR_IMPLEMENTED
from exness_bot.controlled_demo.enablement import (
    DemoEnablementResult,
    DemoGateName,
    DemoGateResult,
    DemoPreflightContext,
    _gate_account_trade_mode,
    _gate_demo_identity,
    _gate_intent_store,
    _gate_quote_freshness,
    _gate_spread_limit,
    _gate_symbol,
    _gate_terminal_trade_permission,
)

logger = structlog.get_logger(__name__)

_FORBIDDEN_ENVS = frozenset({"live", "production", "real", "prod"})
_REQUIRED_ENV = "demo"


class AutoDemoGateName(StrEnum):
    """Extra gate label surfaced in blocking_reasons (DemoGateName has no slot)."""

    AUTO_DEMO_ENABLED = "auto_demo_enabled"
    EXECUTION_MODE = "execution_mode"


def evaluate_auto_demo_enablement(context: DemoPreflightContext) -> DemoEnablementResult:
    """
    Fail-closed gates for autonomous DEMO loop.

    Differences vs controlled one-shot enablement:
    - Requires AUTO_DEMO_EXECUTION_ENABLED=true
    - LIVE_DEMO_APPROVAL is sticky (not consumed per order)
    - No ONE_SHOT_GUARD (multi-candle loop allowed)
    - Still DEMO-only: TRADING_ENV=demo, allowlist, trade_mode=demo
    - EXECUTION_MODE=live is fail-closed (must not claim live while DEMO path runs)
    """
    from exness_bot.config.settings import ExecutionMode

    settings = context.settings
    now = context.evaluated_at or datetime.now(tz=UTC)
    gates: list[DemoGateResult] = []
    extra_reasons: list[str] = []

    auto_on = bool(getattr(settings, "auto_demo_execution_enabled", False))
    if not auto_on:
        extra_reasons.append(
            f"{AutoDemoGateName.AUTO_DEMO_ENABLED.value}: "
            "AUTO_DEMO_EXECUTION_ENABLED=false — autonomous DEMO blocked."
        )
    else:
        logger.info(
            "auto_demo_preflight",
            gate=AutoDemoGateName.AUTO_DEMO_ENABLED.value,
            status="PASS",
            reason="AUTO_DEMO_EXECUTION_ENABLED=true.",
        )

    mode = settings.execution_mode
    mode_value = mode.value if hasattr(mode, "value") else str(mode)
    if mode == ExecutionMode.LIVE or str(mode_value).strip().lower() == "live":
        extra_reasons.append(
            f"{AutoDemoGateName.EXECUTION_MODE.value}: "
            "EXECUTION_MODE=live forbidden on autonomous DEMO path — fail closed."
        )
    elif str(mode_value).strip().lower() != "paper":
        extra_reasons.append(
            f"{AutoDemoGateName.EXECUTION_MODE.value}: "
            f"EXECUTION_MODE={mode_value!r} unsupported for autonomous DEMO — fail closed."
        )
    else:
        logger.info(
            "auto_demo_preflight",
            gate=AutoDemoGateName.EXECUTION_MODE.value,
            status="PASS",
            reason="EXECUTION_MODE=paper.",
        )

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
                f"TRADING_ENV={env!r} forbidden for autonomous DEMO.",
            )
        )
    elif env != _REQUIRED_ENV:
        gates.append(
            DemoGateResult(
                DemoGateName.TRADING_ENV,
                False,
                f"TRADING_ENV={env!r}; autonomous DEMO requires explicit 'demo'.",
            )
        )
    else:
        gates.append(DemoGateResult(DemoGateName.TRADING_ENV, True, "TRADING_ENV=demo."))

    if settings.live_kill_switch:
        gates.append(
            DemoGateResult(
                DemoGateName.KILL_SWITCH,
                False,
                "LIVE_KILL_SWITCH=true — autonomous DEMO blocked.",
            )
        )
    else:
        gates.append(
            DemoGateResult(DemoGateName.KILL_SWITCH, True, "LIVE_KILL_SWITCH=false.")
        )

    if not settings.live_demo_approval:
        gates.append(
            DemoGateResult(
                DemoGateName.DEMO_APPROVAL,
                False,
                "LIVE_DEMO_APPROVAL=false — operator approval required.",
            )
        )
    else:
        gates.append(
            DemoGateResult(
                DemoGateName.DEMO_APPROVAL,
                True,
                "LIVE_DEMO_APPROVAL=true (sticky for autonomous loop).",
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
    gates.append(_gate_terminal_trade_permission(context))
    gates.append(_gate_symbol(context.symbol_info))
    gates.append(_gate_quote_freshness(context))
    gates.append(_gate_spread_limit(settings, context.symbol_info))
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

    gates.append(
        DemoGateResult(
            DemoGateName.ONE_SHOT_GUARD,
            True,
            "ONE_SHOT_GUARD skipped for autonomous DEMO loop.",
        )
    )

    gate_ok = all(g.allowed for g in gates)
    allowed = gate_ok and auto_on and not extra_reasons
    blocking = tuple(
        [
            *extra_reasons,
            *(f"{g.gate.value}: {g.reason}" for g in gates if not g.allowed),
        ]
    )
    message = (
        "Autonomous DEMO enablement PASSED."
        if allowed
        else "Autonomous DEMO enablement BLOCKED."
    )

    result = DemoEnablementResult(
        allowed=allowed,
        gates=tuple(gates),
        blocking_reasons=blocking,
        evaluated_at=now,
        message=message,
        trading_env=env,
        kill_switch_enabled=settings.live_kill_switch,
        approval_active=bool(settings.live_demo_approval),
        approval_consumed=False,
    )
    for gate in result.gates:
        logger.info(
            "auto_demo_preflight",
            gate=gate.gate.value,
            status="PASS" if gate.allowed else "BLOCKED",
            reason=gate.reason,
        )
    return result
