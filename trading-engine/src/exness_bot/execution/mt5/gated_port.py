"""Gated MT5 ExecutionPort — demo safety recheck before MT5Executor.

Does NOT own intent lifecycle. Does NOT import MetaTrader5.
order_send remains only inside LiveMT5ExecutionTransport.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from exness_bot.broker.mt5.executor import MT5Executor, parse_symbol_map, resolve_broker_symbol
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.enablement import (
    DemoEnablementResult,
    DemoGateName,
    DemoGateResult,
    DemoPreflightContext,
    evaluate_demo_controlled_enablement,
)
from exness_bot.domain.models import SymbolInfo
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot
from exness_bot.paper_execution.contract import AckStatus, ExecutionAck, ExecutionIntent

logger = structlog.get_logger(__name__)

SnapshotProvider = Callable[[], GatedExecutionSnapshot]
EnablementEvaluator = Callable[[DemoPreflightContext], DemoEnablementResult]
SettingsProvider = Callable[[], Settings]


class GatedExecutionBlocked(Exception):
    """Fail-closed: gates rejected submission before MT5Executor."""

    def __init__(self, message: str, *, enablement: DemoEnablementResult | None = None) -> None:
        super().__init__(message)
        self.enablement = enablement


@dataclass
class GatedMT5ExecutionPort:
    """
    ExecutionPort decorator:

        submit → re-check demo gates → MT5Executor.submit

    If any gate fails: MT5Executor is NOT called.
    """

    settings: Settings
    executor: MT5Executor
    snapshot_provider: SnapshotProvider
    raise_on_block: bool = False
    enablement_evaluator: EnablementEvaluator = field(
        default=evaluate_demo_controlled_enablement
    )
    settings_provider: SettingsProvider | None = None

    def __post_init__(self) -> None:
        self.submit_count = 0
        self.executor_submit_count = 0
        self.last_block_reason: str | None = None
        self.last_enablement: DemoEnablementResult | None = None

    def _effective_settings(self) -> Settings:
        if self.settings_provider is not None:
            return self.settings_provider()
        return self.settings

    def submit(self, intent: ExecutionIntent, *, quote: SymbolInfo) -> ExecutionAck:
        self.submit_count += 1
        now = datetime.now(tz=UTC)
        snapshot = self.snapshot_provider()
        enablement = self._evaluate(intent=intent, quote=quote, snapshot=snapshot)
        self.last_enablement = enablement
        if not enablement.allowed:
            reason = "; ".join(enablement.blocking_reasons) or enablement.message
            self.last_block_reason = reason
            logger.warning(
                "gated_mt5_blocked",
                intent_id=intent.intent_id,
                reason=reason,
            )
            if self.raise_on_block:
                raise GatedExecutionBlocked(reason, enablement=enablement)
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.REJECTED,
                timestamp=now,
                reason=f"GATED_MT5_BLOCKED: {reason}",
            )

        # Pre-submit recheck complete — only now may MT5Executor run.
        self.executor_submit_count += 1
        return self.executor.submit(intent, quote=quote)

    def _evaluate(
        self,
        *,
        intent: ExecutionIntent,
        quote: SymbolInfo,
        snapshot: GatedExecutionSnapshot,
    ) -> DemoEnablementResult:
        settings = self._effective_settings()
        approval = snapshot.approval
        if approval is None:
            approval = OneShotApproval(active=settings.live_demo_approval)

        context = DemoPreflightContext(
            settings=settings,
            symbol_info=quote,
            intents=snapshot.intents,
            intent_store_error=snapshot.intent_store_error,
            broker_login=snapshot.broker_login,
            broker_server=snapshot.broker_server,
            account_trade_mode=snapshot.account_trade_mode,
            trade_allowed=snapshot.trade_allowed,
            terminal_trade_allowed=snapshot.terminal_trade_allowed,
            quote_fresh=snapshot.quote_fresh,
            quote_age_seconds=snapshot.quote_age_seconds,
            approval=approval,
            prior_submission_count=snapshot.prior_submission_count,
        )
        result = self.enablement_evaluator(context)
        symbol_block = _check_symbol_allowlist(settings, intent.symbol)
        if symbol_block is None:
            return result
        extra = DemoGateResult(DemoGateName.SYMBOL_METADATA, False, symbol_block)
        return DemoEnablementResult(
            allowed=False,
            gates=(*result.gates, extra),
            blocking_reasons=(
                *result.blocking_reasons,
                f"{extra.gate.value}: {extra.reason}",
            ),
            evaluated_at=result.evaluated_at,
            message="Controlled DEMO enablement BLOCKED.",
            trading_env=result.trading_env,
            kill_switch_enabled=result.kill_switch_enabled,
            approval_active=result.approval_active,
            approval_consumed=result.approval_consumed,
        )


def _check_symbol_allowlist(settings: Settings, symbol: str) -> str | None:
    """
    Explicit symbol mapping required — empty map is not allow-all.

    Reuses LIVE_SYMBOL_MAP / MT5_SYMBOL semantics (same as MT5Executor).
    """
    mapping = parse_symbol_map(
        settings.live_symbol_map,
        fallback_canonical=settings.symbol,
        fallback_broker=settings.mt5_symbol,
    )
    if not mapping:
        return "Symbol allowlist/map empty — BLOCK (no allow-all)."
    if resolve_broker_symbol(symbol, mapping) is None:
        return f"Symbol {symbol!r} not in explicit LIVE_SYMBOL_MAP / MT5_SYMBOL allowlist."
    return None
