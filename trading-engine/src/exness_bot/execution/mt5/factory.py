"""Explicit factory for gated MT5 ExecutionPort — never default runtime."""

from __future__ import annotations

from collections.abc import Callable

from exness_bot.broker.mt5.execution_transport import MT5ExecutionTransport
from exness_bot.broker.mt5.executor import MT5Executor
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.enablement import (
    DemoEnablementResult,
    DemoPreflightContext,
    evaluate_demo_controlled_enablement,
)
from exness_bot.controlled_demo.oneshot_transport import OneShotExecutionTransport
from exness_bot.execution.mt5.gated_port import GatedMT5ExecutionPort
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot

SnapshotProvider = Callable[[], GatedExecutionSnapshot]
EnablementEvaluator = Callable[[DemoPreflightContext], DemoEnablementResult]
SettingsProvider = Callable[[], Settings]


def build_gated_mt5_execution_port(
    settings: Settings,
    *,
    transport: MT5ExecutionTransport,
    snapshot_provider: SnapshotProvider,
    wrap_oneshot: bool = True,
    enablement_evaluator: EnablementEvaluator | None = None,
    settings_provider: SettingsProvider | None = None,
) -> GatedMT5ExecutionPort:
    """
    Compose: optional OneShotTransport → MT5Executor → GatedMT5ExecutionPort.

    NOT called by build_execution_service / paper loop / strategy loop.
    Caller must supply Fake or Live transport explicitly.
    Inner MT5Executor.require_enablement=False because demo gates live in the outer port.
    """
    if settings.allow_legacy_run:
        msg = "ALLOW_LEGACY_RUN=true — gated MT5 factory refuses to compose."
        raise RuntimeError(msg)

    inner_transport: MT5ExecutionTransport = (
        OneShotExecutionTransport(transport) if wrap_oneshot else transport
    )

    executor = MT5Executor(
        transport=inner_transport,
        settings=settings,
        require_enablement=False,
    )
    return GatedMT5ExecutionPort(
        settings=settings,
        executor=executor,
        snapshot_provider=snapshot_provider,
        enablement_evaluator=enablement_evaluator or evaluate_demo_controlled_enablement,
        settings_provider=settings_provider,
    )
