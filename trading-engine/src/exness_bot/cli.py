"""Command-line interface."""

from __future__ import annotations

import argparse
import signal
import sys
import time

import structlog

from exness_bot import __version__
from exness_bot.config.settings import get_settings
from exness_bot.engine.factory import create_trading_engine
from exness_bot.engine.models import CycleStatus
from exness_bot.logging.setup import configure_logging

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exness-bot",
        description="Exness algorithmic trading bot via MetaTrader 5",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    run_parser = subparsers.add_parser(
        "run",
        help=(
            "LEGACY trading engine (MT5Adapter / OrderManager). "
            "NOT part of Phase 11 paper ExecutionPort architecture. Default dry-run."
        ),
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Force dry-run mode (log orders, do not submit)",
    )
    run_parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single trading cycle and exit",
    )

    subparsers.add_parser("status", help="Show current configuration and safety status")

    backtest_parser = subparsers.add_parser("backtest", help="Run strategy backtest")
    backtest_parser.add_argument("--file", required=True, help="Path to historical CSV data")
    backtest_parser.add_argument(
        "--json",
        dest="json_output",
        default=None,
        help="Write machine-readable JSON report to this path",
    )

    baseline_parser = subparsers.add_parser(
        "baseline",
        help="Run Phase 7.2 baseline backtest and write report artifacts",
    )
    baseline_parser.add_argument(
        "--file",
        default=None,
        help="Optional CSV path; defaults to best dataset under data/",
    )

    candles_parser = subparsers.add_parser(
        "candles",
        help="Run the live closed-candle engine (no orders, no strategy)",
    )
    candles_parser.add_argument(
        "--once",
        action="store_true",
        help="Poll once and exit",
    )

    signals_parser = subparsers.add_parser(
        "signals",
        help="Run the research signal engine (no orders)",
    )
    signals_parser.add_argument(
        "--once",
        action="store_true",
        help="Warm up and process the latest closed-candle poll once",
    )

    paper_parser = subparsers.add_parser(
        "paper",
        help="Run paper execution (virtual orders only, no MT5 trades)",
    )
    paper_parser.add_argument(
        "--once",
        action="store_true",
        help="Warm up, poll once, apply paper exits/signals, then exit",
    )

    subparsers.add_parser(
        "execution-orchestration-smoke",
        help=(
            "Phase 12.6 Fake/Paper orchestration diagnostic. "
            "Never calls LiveMT5ExecutionTransport / order_send."
        ),
    )

    subparsers.add_parser(
        "live-preflight",
        help=(
            "Evaluate live enablement gates (read-only). "
            "Does NOT submit orders."
        ),
    )

    demo_smoke = subparsers.add_parser(
        "demo-execution-smoke",
        help=(
            "Phase 12.4 controlled MT5 DEMO one-shot smoke. "
            "No strategy loop. Requires --execute --confirm DEMO-EXECUTE to submit."
        ),
    )
    demo_smoke.add_argument(
        "--execute",
        action="store_true",
        help="Allow the single broker submission after all gates pass",
    )
    demo_smoke.add_argument(
        "--confirm",
        type=str,
        default="",
        help="Must be exactly DEMO-EXECUTE to authorize submission",
    )

    return parser


def handle_status() -> int:
    settings = get_settings()
    logger.info(
        "bot_status",
        version=__version__,
        trading_mode=settings.trading_mode.value,
        dry_run=settings.dry_run,
        is_dry_run_mode=settings.is_dry_run_mode,
        allow_live_trading=settings.allow_live_trading,
        is_live_trading_enabled=settings.is_live_trading_enabled,
        symbol=settings.symbol,
        timeframe=settings.timeframe,
    )
    return 0


def handle_run(dry_run: bool | None, once: bool) -> int:
    """
    LEGACY / DEPRECATED stack: MT5Adapter → TradingEngine → OrderManager → order_send.

    Phase 11 commands (`candles`, `signals`, `paper`) must NEVER call this path.
    Prefer `exness-bot paper` for research execution (ExecutionPort / PaperExecutor).

    Requires ALLOW_LEGACY_RUN=true. EXECUTION_MODE=paper does not route here.
    """
    settings = get_settings()
    if not settings.allow_legacy_run:
        logger.error(
            "legacy_run_blocked",
            message=(
                "exness-bot run is LEGACY/DEPRECATED and blocked by default. "
                "Set ALLOW_LEGACY_RUN=true only if you intentionally need the old "
                "OrderManager/MT5Adapter stack. Prefer: exness-bot paper"
            ),
            execution_mode=settings.execution_mode.value,
            allow_legacy_run=False,
        )
        return 1

    if dry_run is not None:
        object.__setattr__(settings, "dry_run", dry_run)

    logger.warning(
        "legacy_run_stack",
        message=(
            "exness-bot run uses the LEGACY MT5Adapter trading stack "
            "(ALLOW_LEGACY_RUN=true). Phase 11 paper/signals/candles stay isolated."
        ),
        trading_mode=settings.trading_mode.value,
        dry_run=settings.is_dry_run_mode,
        allow_live_trading=settings.allow_live_trading,
        execution_mode=settings.execution_mode.value,
        allow_legacy_run=settings.allow_legacy_run,
    )

    try:
        from exness_bot.broker.mt5.adapter import MT5Adapter
    except ImportError:
        logger.error(
            "mt5_import_failed",
            message="MetaTrader5 package is not available on this platform",
        )
        return 1

    broker = MT5Adapter(settings)
    if not broker.connect():
        logger.error("mt5_connect_failed")
        return 1

    engine = create_trading_engine(settings, broker)
    engine.startup()

    shutdown_requested = False

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info("shutdown_signal_received")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    exit_code = 0
    try:
        if once:
            result = engine.tick()
            logger.info(
                "tick_complete",
                status=result.status.value,
                message=result.message,
                paused=result.paused,
            )
            if result.paused:
                exit_code = 1
        else:
            while not shutdown_requested:
                if engine.is_paused:
                    logger.error(
                        "engine_paused_stopping",
                        reason=engine.pause_reason.value if engine.pause_reason else None,
                    )
                    exit_code = 1
                    break

                result = engine.tick()
                logger.info("tick_complete", status=result.status.value, message=result.message)

                if result.status == CycleStatus.PAUSED:
                    exit_code = 1
                    break

                time.sleep(settings.loop_poll_seconds)
    finally:
        engine.shutdown()

    return exit_code


def handle_backtest(data_file: str, json_output: str | None) -> int:
    from exness_bot.backtest.runner import BacktestRunner

    settings = get_settings()
    runner = BacktestRunner(settings)
    try:
        runner.run(data_file, json_output=json_output)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("backtest_failed", error=str(exc))
        return 1
    return 0


def handle_baseline(data_file: str | None) -> int:
    from exness_bot.backtest.baseline_runner import (
        baseline_paths,
        run_baseline,
        write_baseline_outputs,
    )

    settings = get_settings()
    result = run_baseline(settings, data_path=data_file)
    write_baseline_outputs(result, baseline_paths())
    logger.info(
        "baseline_complete",
        status=result.status,
        classification=result.classification.classification.value,
    )
    return 0 if result.status in {"completed", "insufficient_data"} else 1


def handle_candles(once: bool) -> int:
    from exness_bot.candle_engine.events import CandlePollStatus
    from exness_bot.candle_engine.factory import build_candle_engine
    from exness_bot.candle_engine.loop import run_polling_loop
    from exness_bot.data.factory import create_trading_data_provider

    settings = get_settings()
    provider = create_trading_data_provider(settings)
    engine = build_candle_engine(settings, provider)

    if once:
        result = engine.poll()
        logger.info(
            "candle_engine_once",
            status=result.status.value,
            message=result.message,
            events=len(result.events),
            latest_closed_at=(
                result.latest_closed_at.isoformat() if result.latest_closed_at else None
            ),
        )
        for event in result.events:
            candle = event.candle
            logger.info(
                "closed_candle_event",
                symbol=candle.symbol,
                timeframe=candle.timeframe.value,
                timestamp=candle.timestamp.isoformat(),
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                detected_at=event.detected_at.isoformat(),
                idempotency_key=event.idempotency_key,
                source=event.source,
            )
        if result.status in {
            CandlePollStatus.BROKER_DISCONNECTED,
            CandlePollStatus.DATA_UNAVAILABLE,
            CandlePollStatus.INVALID_CANDLE,
        }:
            return 1
        return 0

    run_polling_loop(engine, float(settings.candle_poll_interval_seconds))
    return 0


def handle_signals(once: bool) -> int:
    from exness_bot.candle_engine.events import CandlePollStatus
    from exness_bot.candle_engine.factory import build_candle_engine
    from exness_bot.data.factory import create_trading_data_provider
    from exness_bot.signal_engine.factory import build_signal_engine
    from exness_bot.signal_engine.loop import run_signal_polling_loop
    from exness_bot.signal_engine.models import SignalCycleStatus

    settings = get_settings()
    provider = create_trading_data_provider(settings)
    candle_engine = build_candle_engine(settings, provider)
    signal_engine = build_signal_engine(settings, provider)

    if not once:
        run_signal_polling_loop(
            candle_engine,
            signal_engine,
            float(settings.candle_poll_interval_seconds),
        )
        return 0

    warmed = signal_engine.warmup_from_provider()
    logger.info(
        "signal_engine_warmup",
        status=warmed.status.value,
        message=warmed.message,
        results=len(warmed.results),
    )
    poll = candle_engine.poll()
    processed = signal_engine.process_events(poll.events) if poll.events else warmed
    logger.info(
        "signal_engine_once",
        candle_status=poll.status.value,
        signal_status=processed.status.value,
        results=len(processed.results),
        catchup=processed.catchup_count,
    )
    for item in processed.results:
        logger.info(
            "research_signal",
            signal=item.signal.value,
            timestamp=item.candle_timestamp.isoformat(),
            strategy=item.strategy,
            actionable=item.actionable,
            reason=item.reason,
            idempotency_key=item.idempotency_key,
        )
    logger.info("signal_engine_stopped")
    if poll.status in {
        CandlePollStatus.BROKER_DISCONNECTED,
        CandlePollStatus.DATA_UNAVAILABLE,
        CandlePollStatus.INVALID_CANDLE,
    }:
        return 1
    if warmed.status in {
        SignalCycleStatus.DATA_UNAVAILABLE,
        SignalCycleStatus.INSUFFICIENT_HISTORY,
    } and not poll.events:
        return 1
    return 0


def handle_paper(once: bool) -> int:
    from exness_bot.candle_engine.events import CandlePollStatus
    from exness_bot.candle_engine.factory import build_candle_engine
    from exness_bot.data.factory import create_trading_data_provider
    from exness_bot.paper_execution.factory import (
        build_execution_service,
        refresh_execution_quote,
    )
    from exness_bot.paper_execution.loop import (
        process_closed_candles,
        run_paper_polling_loop,
    )
    from exness_bot.signal_engine.factory import build_signal_engine
    from exness_bot.signal_engine.models import SignalCycleStatus

    settings = get_settings()
    provider = create_trading_data_provider(settings)
    candle_engine = build_candle_engine(settings, provider)
    signal_engine = build_signal_engine(settings, provider)
    execution = build_execution_service(settings, provider=provider)

    if not once:
        run_paper_polling_loop(
            candle_engine,
            signal_engine,
            execution,
            float(settings.candle_poll_interval_seconds),
            refresh_quote=lambda: refresh_execution_quote(execution, settings, provider),
        )
        return 0

    logger.info("paper_execution_started", mode=settings.execution_mode.value)
    before = provider.get_snapshot()
    warmed = signal_engine.warmup_from_provider()
    logger.info(
        "signal_engine_warmup",
        status=warmed.status.value,
        message=warmed.message,
        results=len(warmed.results),
    )
    refresh_execution_quote(execution, settings, provider)
    poll = candle_engine.poll()
    if poll.events:
        process_closed_candles(poll.events, signal_engine, execution)
    account = execution.account_state()
    after = provider.get_snapshot()
    last = execution.last_execution()
    session = execution.session()
    logger.info(
        "paper_execution_once",
        candle_status=poll.status.value,
        paper_open=len(execution.open_positions()),
        paper_balance=account.balance,
        paper_equity=account.equity,
        last_execution=last.status.value if last else None,
        broker_positions_before=len(before.positions),
        broker_positions_after=len(after.positions),
    )
    logger.info(
        "paper_validation_summary",
        session_id=session.session_id,
        candles_processed=session.candles_processed,
        signal_count=session.signal_count,
        execution_count=session.execution_count,
        rejected_count=session.rejected_count,
        paper_open=session.open_positions,
        realized_pnl=session.realized_pnl,
        unrealized_pnl=session.unrealized_pnl,
        drawdown_pct=session.drawdown_pct,
        broker_positions_before=len(before.positions),
        broker_positions_after=len(after.positions),
        broker_positions_unchanged=len(before.positions) == len(after.positions),
    )
    logger.info("paper_execution_stopped")
    if poll.status in {
        CandlePollStatus.BROKER_DISCONNECTED,
        CandlePollStatus.DATA_UNAVAILABLE,
        CandlePollStatus.INVALID_CANDLE,
    }:
        return 1
    if warmed.status in {
        SignalCycleStatus.DATA_UNAVAILABLE,
        SignalCycleStatus.INSUFFICIENT_HISTORY,
    } and not poll.events:
        return 1
    return 0


def handle_live_preflight() -> int:
    """
    Read-only live enablement report.

    NEVER constructs a live executor. NEVER mutates broker state.
    Exit 1 when live is not allowed (always in Phase 12.2).
    """
    import os

    from exness_bot.backtest.config import BacktestConfig
    from exness_bot.config.live_enablement import (
        LivePreflightContext,
        evaluate_live_enablement,
        load_intent_store_for_preflight,
    )
    from exness_bot.config.settings import Settings
    from exness_bot.paper_execution.broker_query import UnavailableBrokerExecutionQuery
    from exness_bot.paper_execution.factory import DEFAULT_STATE_PATH

    requested = os.environ.get("EXECUTION_MODE", "paper").strip().lower()
    # Force paper for Settings parse; requested mode is evaluated separately for Gate A.
    settings = Settings(EXECUTION_MODE="paper")
    intents, store_error = load_intent_store_for_preflight(DEFAULT_STATE_PATH)
    config = BacktestConfig.from_settings(settings)
    symbol = config.to_symbol_info(close_price=2350.0).model_copy(
        update={
            "stops_level": config.paper_stops_level,
            "freeze_level": config.paper_freeze_level,
        }
    )

    result = evaluate_live_enablement(
        LivePreflightContext(
            settings=settings,
            requested_execution_mode=requested,
            symbol_info=symbol,
            intents=intents,
            intent_store_error=store_error,
            broker_query=UnavailableBrokerExecutionQuery(),
            broker_login=settings.mt5_live_login or settings.mt5_login,
            broker_server=settings.mt5_live_server or settings.mt5_server,
        )
    )
    logger.info(
        "live_preflight_report",
        readiness=result.readiness_status.value,
        allowed=result.allowed,
        configuration_preflight_ready=result.configuration_preflight_ready,
        execution_capability=result.execution_capability,
        message=result.message,
        note="LIVE EXECUTION NOT IMPLEMENTED",
        blocking_count=len(result.blocking_reasons),
    )
    for gate in result.gates:
        logger.info(
            "live_preflight_gate",
            gate=gate.gate.value,
            status="PASS" if gate.allowed else "BLOCKED",
            reason=gate.reason,
        )
    return 0 if result.allowed else 1


def handle_demo_execution_smoke(*, execute: bool, confirm: str) -> int:
    """
    Phase 12.9 — controlled DEMO one-shot.

    Default (no --execute): connect read-only, evaluate gates, never submit.
    With --execute --confirm DEMO-EXECUTE: exactly one submission via
    ExecutionOrchestrator → GatedMT5ExecutionPort → MT5Executor →
    OneShotExecutionTransport → LiveMT5ExecutionTransport.
    No strategy loop. No retry. Explicit VOLUME=0.01.
    """
    from exness_bot.broker.mt5.connection_manager import ConnectionState, MT5ConnectionManager
    from exness_bot.broker.mt5.execution_query import ReadOnlyMt5BrokerExecutionQuery
    from exness_bot.broker.mt5.execution_transport import (
        FakeMT5ExecutionTransport,
        LiveMT5ExecutionTransport,
        MT5TransportResult,
        TransportOutcome,
    )
    from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient
    from exness_bot.broker.mt5.trading_client import MT5TradingClient
    from exness_bot.config.settings import Settings, TradingMode
    from exness_bot.controlled_demo.approval import OneShotApproval
    from exness_bot.controlled_demo.identity import ReadOnlyMt5DemoProbe
    from exness_bot.controlled_demo.smoke import CONFIRM_PHRASE, ControlledDemoSmoke
    from exness_bot.paper_execution.factory import ENGINE_ROOT

    settings = Settings()
    if settings.trading_mode == TradingMode.LIVE:
        logger.error(
            "demo_smoke_blocked",
            reason="TRADING_MODE=live forbidden for controlled DEMO smoke",
        )
        return 1

    state_path = ENGINE_ROOT / ".demo_smoke_state.json"
    ledger_path = ENGINE_ROOT / ".demo_smoke_ledger.json"
    manager: MT5ConnectionManager | None = None

    try:
        if execute:
            trading = MT5TradingClient(settings)
            manager = MT5ConnectionManager(settings, client=trading)
            status = manager.connect()
            if status.state != ConnectionState.CONNECTED:
                logger.error("demo_smoke_mt5_unavailable", message=status.message)
                return 1
            probe_client: MT5ReadOnlyClient = trading
            transport: object = LiveMT5ExecutionTransport(client=trading)
            broker_query: object = ReadOnlyMt5BrokerExecutionQuery(trading)
            real_submission = True
        else:
            logger.info(
                "demo_smoke_preflight_only",
                note="No broker submission without --execute --confirm DEMO-EXECUTE",
                confirm_required=CONFIRM_PHRASE,
            )
            readonly = MT5ReadOnlyClient(settings)
            manager = MT5ConnectionManager(settings, client=readonly)
            status = manager.connect()
            if status.state != ConnectionState.CONNECTED:
                logger.error("demo_smoke_mt5_unavailable", message=status.message)
                return 1
            probe_client = readonly
            transport = FakeMT5ExecutionTransport(
                default=MT5TransportResult(
                    outcome=TransportOutcome.REJECTED,
                    comment="preflight_only_no_submit",
                )
            )
            broker_query = ReadOnlyMt5BrokerExecutionQuery(readonly)
            real_submission = False

        from exness_bot.config.live_enablement import load_intent_store_for_preflight
        from exness_bot.controlled_demo.preflight import run_demo_preflight

        probe = ReadOnlyMt5DemoProbe(
            probe_client,
            stale_after_seconds=settings.live_data_stale_seconds,
        )
        intents, store_error = load_intent_store_for_preflight(state_path)
        preflight = run_demo_preflight(
            settings=settings,
            probe=probe,
            intents=intents,
            intent_store_error=store_error,
            broker_query=broker_query,  # type: ignore[arg-type]
            ledger_path=ledger_path,
            approval=OneShotApproval(active=settings.live_demo_approval),
        )
        logger.info(
            "demo_preflight_report",
            overall=preflight.overall.value,
            message=preflight.message,
            masked_login=preflight.masked_login,
            trade_mode=preflight.trade_mode,
            server=preflight.broker_server,
            broker_symbol=preflight.broker_symbol,
        )
        for check in preflight.checks:
            logger.info(
                "demo_preflight_gate",
                name=check.name,
                status=check.status.value,
                detail=check.detail,
            )

        if not execute:
            # Preflight-only: never submit
            return 0 if preflight.overall.value == "PASS" else 1

        if preflight.overall.value != "PASS":
            logger.error(
                "demo_smoke_execute_blocked_by_preflight",
                overall=preflight.overall.value,
                message=preflight.message,
                note="NO order_send — preflight must PASS before --execute",
            )
            return 1

        smoke = ControlledDemoSmoke(
            settings=settings,
            probe=probe,
            transport=transport,  # type: ignore[arg-type]
            approval=OneShotApproval(active=settings.live_demo_approval),
            state_path=state_path,
            ledger_path=ledger_path,
            confirm_phrase=confirm,
            execute=execute,
            broker_query=broker_query,  # type: ignore[arg-type]
            real_broker_submission=real_submission,
        )
        result = smoke.run()
        logger.info(
            "demo_smoke_result",
            blocked=result.blocked,
            submitted=result.submitted,
            message=result.message,
            transport_send_count=result.transport_send_count,
            lifecycle=result.lifecycle.value if result.lifecycle else None,
            ack=result.ack.status.value if result.ack else None,
            reconcile=result.reconcile_status,
        )
        if result.enablement is not None:
            for gate in result.enablement.gates:
                logger.info(
                    "demo_smoke_gate",
                    gate=gate.gate.value,
                    status="PASS" if gate.allowed else "BLOCKED",
                    reason=gate.reason,
                )
        if result.submitted:
            if result.evidence is not None:
                logger.info("demo_smoke_evidence", **result.evidence.as_dict())
            if result.lifecycle is not None and result.lifecycle.value == "UNKNOWN":
                logger.warning(
                    "demo_smoke_unknown_operator",
                    message=(
                        "EXECUTION STATE: UNKNOWN | "
                        "ACTION REQUIRED: READ-ONLY BROKER RECONCILIATION | "
                        "AUTOMATIC RESUBMISSION: DISABLED"
                    ),
                )
            logger.warning(
                "demo_smoke_post_safety",
                message=(
                    "Re-enable LIVE_KILL_SWITCH=true and set LIVE_DEMO_APPROVAL=false. "
                    "No strategy loop was started."
                ),
            )
        if result.blocked and not result.submitted:
            return 1
        return 0 if result.submitted else 1
    except Exception as exc:
        logger.error("demo_smoke_failed", error=str(exc))
        return 1
    finally:
        if manager is not None:
            from contextlib import suppress

            with suppress(Exception):
                manager.disconnect()


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "status":
        return handle_status()
    if args.command == "run":
        return handle_run(dry_run=args.dry_run, once=args.once)
    if args.command == "backtest":
        return handle_backtest(data_file=args.file, json_output=args.json_output)
    if args.command == "baseline":
        return handle_baseline(data_file=args.file)
    if args.command == "candles":
        return handle_candles(once=args.once)
    if args.command == "signals":
        return handle_signals(once=args.once)
    if args.command == "paper":
        return handle_paper(once=args.once)
    if args.command == "execution-orchestration-smoke":
        from exness_bot.execution.smoke_cli import run_orchestration_smoke

        return run_orchestration_smoke()
    if args.command == "live-preflight":
        return handle_live_preflight()
    if args.command == "demo-execution-smoke":
        return handle_demo_execution_smoke(
            execute=bool(args.execute),
            confirm=str(args.confirm or ""),
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
