"""Operator CLI for autonomous DEMO loop — never auto-started by API."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.evidence import mask_login
from exness_bot.domain.enums import Timeframe
from exness_bot.execution.auto_demo.decision_store import SqliteAutoDemoDecisionStore
from exness_bot.execution.auto_demo.factory import (
    build_auto_demo_candidate_execution_service,
    resolve_auto_demo_state_path,
)
from exness_bot.execution.auto_demo.hot_read import (
    auto_demo_run_allowed,
    hot_read_safety_settings,
    load_auto_demo_settings,
)
from exness_bot.execution.auto_demo.loop import (
    AutoDemoCandidateBundle,
    AutonomousDemoExecutionLoop,
    ClosedM15Observation,
)
from exness_bot.execution.auto_demo.runtime_snapshot import make_auto_demo_snapshot_provider
from exness_bot.execution.auto_demo.status import build_auto_demo_status
from exness_bot.execution.integration.candidate_status import (
    build_candidate_status_from_mtf_provider,
)
from exness_bot.execution.integration.factory import require_durable_setup_store
from exness_bot.execution.integration.service import CandidateExecutionContext
from exness_bot.market_data.candles import closed_candles_only
from exness_bot.paper_execution.intent_store import SnapshotIntentStore

AGENT_NOTE = (
    "AI/Cursor agents must NEVER enable AUTO_DEMO_EXECUTION_ENABLED "
    "or run auto_demo with LiveMT5ExecutionTransport against real money."
)


def _decision_store(settings: Settings) -> SqliteAutoDemoDecisionStore:
    fallback = Path("auto_demo_decisions.db")
    return SqliteAutoDemoDecisionStore.from_settings_database_url(
        settings.database_url,
        fallback=fallback,
    )


def cmd_status(settings: Settings) -> int:
    store = _decision_store(settings)
    broker_login = None
    trade_mode = None
    try:
        from exness_bot.data.factory import create_trading_data_provider

        provider = create_trading_data_provider(settings)
        snapshot = provider.get_snapshot()
        if snapshot.account is not None:
            broker_login = snapshot.account.login
            trade_mode = snapshot.account.trade_mode
    except Exception:
        pass
    status = build_auto_demo_status(
        settings,
        store,
        broker_login=broker_login,
        account_trade_mode=trade_mode,
    )
    print(json.dumps(status, indent=2, default=str))
    return 0


def cmd_preflight(settings: Settings) -> int:
    """Read-only readiness — never requires LIVE_KILL_SWITCH=false."""
    from exness_bot.data.factory import create_trading_data_provider
    from exness_bot.execution.auto_demo.preflight import (
        build_provider_preflight_readers,
        run_auto_demo_preflight,
    )

    provider = create_trading_data_provider(settings)
    read_account, read_candles, read_tick = build_provider_preflight_readers(provider)
    result = run_auto_demo_preflight(
        settings,
        read_account=read_account,
        read_candles=read_candles,
        read_tick=read_tick,
    )
    print(json.dumps(result.as_dict(), indent=2, default=str))
    return 0 if result.preflight == "PASS" else 2


def _observe_from_provider(
    provider: Any, symbol: str
) -> Callable[[], ClosedM15Observation | None]:
    def observe() -> ClosedM15Observation | None:
        now = datetime.now(tz=UTC)
        raw = provider.get_candles(symbol, Timeframe.M15, count=50)
        closed = closed_candles_only(raw or [], Timeframe.M15, now=now)
        if not closed:
            return None
        latest = closed[-1]
        return ClosedM15Observation(
            symbol=symbol,
            timeframe="M15",
            closed_at=latest.timestamp,
        )

    return observe


def _build_bundle_from_provider(
    settings: Settings, provider: Any, setup_store: Any
) -> Callable[[ClosedM15Observation], AutoDemoCandidateBundle]:
    def build(observation: ClosedM15Observation) -> AutoDemoCandidateBundle:
        built = build_candidate_status_from_mtf_provider(
            settings=settings,
            provider=provider,
            setup_store=setup_store,
            symbol=observation.symbol,
        )
        snapshot = provider.get_snapshot()
        tick = None
        quote = None
        get_tick = getattr(provider, "get_tick", None)
        get_symbol = getattr(provider, "get_symbol_info", None)
        if callable(get_tick):
            try:
                tick = get_tick(observation.symbol)
            except Exception:
                tick = None
        if callable(get_symbol):
            try:
                quote = get_symbol(observation.symbol)
            except Exception:
                quote = None

        tf_status = built.timeframe_status or {}
        context = CandidateExecutionContext(
            tick=tick,
            quote=quote,
            snapshot=snapshot,
            timeframe_status=tf_status,
            now=datetime.now(tz=UTC),
        )
        if built.blocked_result:
            return AutoDemoCandidateBundle(
                candidate=None,
                context=context,
                blocked_reasons=(built.blocked_result,),
                signal=built.final_signal,
            )
        status = built.status
        if status is None or status.candidate is None or not status.eligible:
            reasons = () if status is None else status.reasons
            return AutoDemoCandidateBundle(
                candidate=None if status is None else status.candidate,
                context=context,
                blocked_reasons=reasons or ("CANDIDATE_NOT_ELIGIBLE",),
                signal=built.final_signal,
            )
        return AutoDemoCandidateBundle(
            candidate=status.candidate,
            context=context,
            blocked_reasons=(),
            signal=built.final_signal or status.candidate.side,
        )

    return build


def _require_live_transport_human(settings: Settings) -> Any:
    """Only construct LiveMT5 when operator explicitly runs mutate path."""
    from exness_bot.broker.mt5.execution_transport import LiveMT5ExecutionTransport
    from exness_bot.broker.mt5.trading_client import MT5TradingClient

    client = MT5TradingClient(settings)
    return LiveMT5ExecutionTransport(client=client)


def _intent_loader(store_holder: dict[str, SnapshotIntentStore]) -> Callable[[], Any]:
    """Expose unresolved UNKNOWN only — never live IN_FLIGHT.

    Orchestrator persists IN_FLIGHT *before* gated submit. Passing that row
    into ``_gate_intent_store`` would false-block the active submission.
    UnresolvedIntentGuard already blocks *new* plans when IN_FLIGHT exists.
    """

    def load() -> Any:
        store = store_holder.get("store")
        if store is None:
            return ()
        return tuple(store.list_unknown())

    return load


def _build_mutate_stack(
    settings: Settings,
    *,
    dry: bool,
) -> tuple[Any, Any, SqliteAutoDemoDecisionStore, Any, Path]:
    """Shared once/run wiring — durable intent path + verified runtime snapshot."""
    from exness_bot.broker.mt5.execution_transport import FakeMT5ExecutionTransport
    from exness_bot.data.factory import create_trading_data_provider

    provider = create_trading_data_provider(settings)
    setup_store = require_durable_setup_store(settings)
    decision_store = _decision_store(settings)
    transport: Any = (
        FakeMT5ExecutionTransport() if dry else _require_live_transport_human(settings)
    )
    state_path = resolve_auto_demo_state_path()
    store_holder: dict[str, SnapshotIntentStore] = {}

    def safety() -> Settings:
        return hot_read_safety_settings(settings)

    snapshot_provider = make_auto_demo_snapshot_provider(
        provider,
        settings,
        intent_loader=_intent_loader(store_holder),
        settings_provider=safety,
    )
    service, _gated, intent_store = build_auto_demo_candidate_execution_service(
        settings,
        transport=transport,
        snapshot_provider=snapshot_provider,
        setup_store=setup_store,
        state_path=state_path,
        settings_provider=safety,
    )
    store_holder["store"] = intent_store
    return provider, setup_store, decision_store, service, state_path


def cmd_once(settings: Settings, *, dry: bool) -> int:
    print(AGENT_NOTE)
    if not auto_demo_run_allowed(settings) and not dry:
        print("AUTO_DEMO_EXECUTION_ENABLED=false — refusing mutate run.")
        return 2

    provider, setup_store, store, service, state_path = _build_mutate_stack(
        settings, dry=dry
    )
    print(f"intent_state_path={state_path}")

    symbol = settings.symbol
    loop = AutonomousDemoExecutionLoop(
        settings=settings,
        decision_store=store,
        observe_closed_m15=_observe_from_provider(provider, symbol),
        build_bundle=_build_bundle_from_provider(settings, provider, setup_store),
        service=service,
        account_provider=lambda: provider.get_snapshot().account,
        positions_provider=lambda: list(provider.get_snapshot().positions),
        settings_provider=lambda: hot_read_safety_settings(settings),
        poll_seconds=float(min(15, max(3, settings.loop_poll_seconds))),
    )
    record = loop.run_once()
    if record is None:
        print("No closed M15 observation.")
        return 0
    account = provider.get_snapshot().account
    print(
        json.dumps(
            {
                "decision_id": record.decision_id,
                "state": record.state,
                "blocked_reasons": record.blocked_reasons,
                "intent_state_path": str(state_path),
                "account_login_masked": (
                    None if account is None else mask_login(account.login)
                ),
            },
            indent=2,
        )
    )
    return 0


def cmd_run(settings: Settings, *, dry: bool) -> int:
    print(AGENT_NOTE)
    if not auto_demo_run_allowed(settings):
        print("AUTO_DEMO_EXECUTION_ENABLED=false — refusing run.")
        return 2
    if dry:
        print("dry mode uses FakeMT5 — no broker mutation.")
    else:
        print("LIVE transport path — DEMO account only. Ctrl+C to stop.")

    provider, setup_store, store, service, state_path = _build_mutate_stack(
        settings, dry=dry
    )
    print(f"intent_state_path={state_path}")
    symbol = settings.symbol
    stop = {"flag": False}

    def should_stop() -> bool:
        return stop["flag"]

    loop = AutonomousDemoExecutionLoop(
        settings=settings,
        decision_store=store,
        observe_closed_m15=_observe_from_provider(provider, symbol),
        build_bundle=_build_bundle_from_provider(settings, provider, setup_store),
        service=service,
        account_provider=lambda: provider.get_snapshot().account,
        positions_provider=lambda: list(provider.get_snapshot().positions),
        settings_provider=lambda: hot_read_safety_settings(settings),
        sleep_fn=time.sleep,
        should_stop=should_stop,
        poll_seconds=float(min(15, max(3, 5))),
    )
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        stop["flag"] = True
        print("Stopped.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m exness_bot.execution.auto_demo",
        description="Phase 17.3 autonomous DEMO execution loop (DEMO ONLY).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Show enablement + last decision (no secrets)")
    sub.add_parser(
        "preflight",
        help="Read-only DEMO readiness (account/allowlist/M15; no order_send)",
    )
    once = sub.add_parser("once", help="Evaluate latest closed M15 once")
    once.add_argument(
        "--dry",
        action="store_true",
        help="Use FakeMT5ExecutionTransport (no broker mutation)",
    )
    run = sub.add_parser("run", help="Poll for new closed M15 candles")
    run.add_argument(
        "--dry",
        action="store_true",
        help="Use FakeMT5ExecutionTransport (no broker mutation)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Same canonical Settings loader for status / preflight / once / run.
    settings = load_auto_demo_settings()
    if args.command == "status":
        return cmd_status(settings)
    if args.command == "preflight":
        return cmd_preflight(settings)
    if args.command == "once":
        return cmd_once(settings, dry=bool(args.dry))
    if args.command == "run":
        return cmd_run(settings, dry=bool(args.dry))
    parser.error(f"Unknown command: {args.command}")
    return 2

if __name__ == "__main__":
    sys.exit(main())
