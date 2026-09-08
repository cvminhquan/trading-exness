"""Phase 17.2.2 — read-only MTF setup watcher (never mutates broker).

Observes MTF → CanonicalTradeSetup → ExecutionCandidate eligibility.
MUST NOT import or call ExecutionOrchestrator / GatedMT5 / Live transport / order_send.
"""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TextIO

from exness_bot.broker.mt5.connection_manager import ConnectionState, MT5ConnectionManager
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.identity import (
    DemoMarketSnapshot,
    ReadOnlyMt5DemoProbe,
    resolve_broker_symbol_explicit,
)
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.data.mt5_provider import MT5TradingDataProvider
from exness_bot.domain.models import Tick
from exness_bot.execution.integration.candidate_status import (
    build_candidate_status_from_mtf_provider,
)
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    ExecutionCandidate,
    ExecutionCandidateStatus,
)
from exness_bot.market_analysis.contract.spread import (
    compute_raw_spread_points,
    normalize_spread_points,
)
from exness_bot.market_analysis.contract.store import (
    InMemorySetupLifecycleStore,
    SetupLifecycleStore,
    SqliteSetupLifecycleStore,
)
from exness_bot.market_analysis.mtf_diagnostics import (
    MtfDecisionDiagnostics,
    build_mtf_decision_diagnostics,
    format_mtf_decision_summary,
    format_mtf_verbose_timeframes,
)
from exness_bot.market_analysis.sizing import size_position

DEFAULT_INTERVAL_SECONDS = 15
MIN_INTERVAL_SECONDS = 5

WATCHER_AGENT_NOTE = (
    "candidate-demo-watch is READ-ONLY. "
    "It never runs candidate-demo-execution-smoke --execute. "
    "READY is informational only — operator must re-run PREVIEW manually."
)


def _executable_price(*, side: str, tick: Tick) -> float:
    """BUY/LONG uses ASK; SELL/SHORT uses BID — local copy to avoid executor imports."""
    if side == "LONG":
        return float(tick.ask)
    return float(tick.bid)


@dataclass(frozen=True)
class WatchSnapshot:
    """One read-only observation of analysis / setup / eligibility."""

    timestamp: datetime
    symbol: str
    data_state: str  # LIVE | DISCONNECTED | UNAVAILABLE
    final_signal: str
    confidence: float | None
    confidence_meaning: str
    setup_id: str | None
    setup_state: str
    analysis_fingerprint: str | None
    entry_zone_low: float | None
    entry_zone_high: float | None
    executable_price: float | None
    stop_loss: float | None
    tp1: float | None
    tp2: float | None
    tp3: float | None
    proposed_volume: float | None
    estimated_risk_usd: float | None
    risk_budget_usd: float | None
    broker_executable: bool | None
    risk_acceptable: bool | None
    candidate_eligible: bool
    block_reasons: tuple[str, ...]
    bid: float | None
    ask: float | None
    raw_spread_points: float | None
    normalized_spread_points: float | None
    max_spread_points: int
    mtf_diagnostics: MtfDecisionDiagnostics | None = None


def is_ready(snap: WatchSnapshot) -> bool:
    """Informational READY — does NOT authorize broker mutation."""
    if snap.data_state != "LIVE":
        return False
    if snap.final_signal not in {"LONG", "SHORT"}:
        return False
    if snap.setup_state != "ENTRY_ZONE":
        return False
    if not snap.candidate_eligible:
        return False
    return len(snap.block_reasons) == 0


def meaningful_change(
    prev: WatchSnapshot | None, curr: WatchSnapshot
) -> bool:
    """True when a full report should print (not just heartbeat)."""
    if prev is None:
        return True
    if prev.data_state != curr.data_state:
        return True
    if prev.final_signal != curr.final_signal:
        return True
    if prev.setup_state != curr.setup_state:
        return True
    if prev.setup_id != curr.setup_id:
        return True
    if prev.candidate_eligible != curr.candidate_eligible:
        return True
    if prev.block_reasons != curr.block_reasons:
        return True
    if prev.analysis_fingerprint != curr.analysis_fingerprint:
        return True
    prev_why = (
        None if prev.mtf_diagnostics is None else prev.mtf_diagnostics.decision_reasons
    )
    curr_why = (
        None if curr.mtf_diagnostics is None else curr.mtf_diagnostics.decision_reasons
    )
    if prev_why != curr_why:
        return True
    prev_w = (
        None
        if prev.mtf_diagnostics is None
        else prev.mtf_diagnostics.mtf_weighted_score
    )
    curr_w = (
        None
        if curr.mtf_diagnostics is None
        else curr.mtf_diagnostics.mtf_weighted_score
    )
    return prev_w != curr_w


def ready_transition(prev: WatchSnapshot | None, curr: WatchSnapshot) -> bool:
    """Emit READY once per transition into the ready state."""
    if not is_ready(curr):
        return False
    if prev is None:
        return True
    return not is_ready(prev)


def _fmt(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.5g}"
    return str(value)


def _fmt_spread(value: float | None) -> str:
    if value is None:
        return "N/A"
    return repr(value)


def format_heartbeat(snap: WatchSnapshot) -> str:
    ts = snap.timestamp.astimezone().strftime("%H:%M:%S")
    weighted = "N/A"
    if snap.mtf_diagnostics is not None and snap.mtf_diagnostics.mtf_weighted_score is not None:
        weighted = f"{snap.mtf_diagnostics.mtf_weighted_score:+.1f}"
    return (
        f"[{ts}] {snap.symbol} {snap.setup_state} {snap.final_signal} "
        f"w={weighted} eligible={_fmt(snap.candidate_eligible)} data={snap.data_state}"
    )


def format_full_report(
    snap: WatchSnapshot, *, verbose_analysis: bool = False
) -> list[str]:
    reasons = ", ".join(snap.block_reasons) if snap.block_reasons else "—"
    lines: list[str] = ["======== SETUP WATCH ========", f"TIMESTAMP: {snap.timestamp.isoformat()}"]
    if snap.mtf_diagnostics is not None:
        lines.extend(["", *format_mtf_decision_summary(snap.mtf_diagnostics)])
        if verbose_analysis:
            lines.extend(["", *format_mtf_verbose_timeframes(snap.mtf_diagnostics)])
    lines.extend(
        [
            f"DATA_STATE: {snap.data_state}",
            f"SYMBOL: {snap.symbol}",
            f"BID: {_fmt(snap.bid)}",
            f"ASK: {_fmt(snap.ask)}",
            f"RAW_SPREAD_POINTS: {_fmt_spread(snap.raw_spread_points)}",
            f"NORMALIZED_SPREAD_POINTS: {_fmt_spread(snap.normalized_spread_points)}",
            f"MAX_SPREAD_POINTS: {snap.max_spread_points}",
            f"FINAL_SIGNAL: {snap.final_signal}",
            f"CONFIDENCE: {_fmt(snap.confidence)}",
            f"CONFIDENCE_MEANING: {snap.confidence_meaning or 'N/A'}",
            f"SETUP_ID: {_fmt(snap.setup_id)}",
            f"SETUP_STATE: {snap.setup_state}",
            f"ENTRY_ZONE_LOW: {_fmt(snap.entry_zone_low)}",
            f"ENTRY_ZONE_HIGH: {_fmt(snap.entry_zone_high)}",
            f"EXECUTABLE_PRICE: {_fmt(snap.executable_price)}",
            f"SL: {_fmt(snap.stop_loss)}",
            f"TP1: {_fmt(snap.tp1)}",
            f"TP2: {_fmt(snap.tp2)}",
            f"TP3: {_fmt(snap.tp3)}",
            f"PROPOSED_VOLUME: {_fmt(snap.proposed_volume)}",
            f"ESTIMATED_RISK_USD: {_fmt(snap.estimated_risk_usd)}",
            f"RISK_BUDGET_USD: {_fmt(snap.risk_budget_usd)}",
            f"BROKER_EXECUTABLE: {_fmt(snap.broker_executable)}",
            f"RISK_ACCEPTABLE: {_fmt(snap.risk_acceptable)}",
            f"CANDIDATE_ELIGIBLE: {_fmt(snap.candidate_eligible)}",
            f"BLOCK_REASONS: {reasons}",
            "BROKER MUTATION: NO",
            "ORDER_SEND: NO",
            "=============================",
        ]
    )
    return lines


def format_ready_banner(snap: WatchSnapshot) -> list[str]:
    from exness_bot.execution.integration.demo_watch_alerts import format_ready_alert

    return list(format_ready_alert(snap))


def _tp_at(
    setup: CanonicalTradeSetup | None, index: int
) -> float | None:
    if setup is None or index >= len(setup.take_profits):
        return None
    return float(setup.take_profits[index].price)


def _unavailable_snapshot(
    *,
    symbol: str,
    data_state: str,
    max_spread_points: int,
    message_reason: str,
    now: datetime | None = None,
) -> WatchSnapshot:
    ts = now or datetime.now(tz=UTC)
    return WatchSnapshot(
        timestamp=ts,
        symbol=symbol,
        data_state=data_state,
        final_signal="WAIT",
        confidence=None,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        setup_id=None,
        setup_state="NO_SETUP",
        analysis_fingerprint=None,
        entry_zone_low=None,
        entry_zone_high=None,
        executable_price=None,
        stop_loss=None,
        tp1=None,
        tp2=None,
        tp3=None,
        proposed_volume=None,
        estimated_risk_usd=None,
        risk_budget_usd=None,
        broker_executable=None,
        risk_acceptable=None,
        candidate_eligible=False,
        block_reasons=(message_reason,),
        bid=None,
        ask=None,
        raw_spread_points=None,
        normalized_spread_points=None,
        max_spread_points=max_spread_points,
    )


def build_watch_snapshot(
    *,
    symbol: str,
    settings: Settings,
    status: ExecutionCandidateStatus | None,
    setup: CanonicalTradeSetup | None,
    candidate: ExecutionCandidate | None,
    final_signal: str,
    market: DemoMarketSnapshot | None,
    equity: float | None,
    data_state: str = "LIVE",
    blocked_message: str | None = None,
    now: datetime | None = None,
    mtf_diagnostics: MtfDecisionDiagnostics | None = None,
) -> WatchSnapshot:
    """Pure assembler — no MT5 / no execution side effects."""
    ts = now or datetime.now(tz=UTC)
    max_spread = int(settings.max_spread_points)

    if data_state != "LIVE" or status is None:
        reason = blocked_message or (
            "DATA_UNAVAILABLE" if data_state == "UNAVAILABLE" else "DISCONNECTED"
        )
        snap = _unavailable_snapshot(
            symbol=symbol,
            data_state=data_state,
            max_spread_points=max_spread,
            message_reason=reason,
            now=ts,
        )
        if mtf_diagnostics is None:
            return snap
        return WatchSnapshot(**{**snap.__dict__, "mtf_diagnostics": mtf_diagnostics})

    bid: float | None = None
    ask: float | None = None
    raw_spread: float | None = None
    normalized: float | None = None
    if market is not None:
        bid = float(market.symbol.bid)
        ask = float(market.symbol.ask)
        point = float(market.symbol.point) if market.symbol.point > 0 else 0.0
        if point > 0:
            raw_spread = compute_raw_spread_points(bid=bid, ask=ask, point=point)
            normalized = normalize_spread_points(raw_spread)
        else:
            raw_spread = float(market.spread_points)
            normalized = normalize_spread_points(raw_spread)

    side = final_signal if final_signal in {"LONG", "SHORT"} else (
        setup.direction if setup is not None else "LONG"
    )
    exec_px: float | None = None
    if market is not None and setup is not None:
        exec_px = _executable_price(side=side, tick=market.tick)

    proposed_volume: float | None = None
    estimated_risk: float | None = None
    risk_budget: float | None = None
    broker_exec: bool | None = None
    risk_ok: bool | None = None

    if candidate is not None:
        proposed_volume = candidate.proposed_volume
        estimated_risk = candidate.estimated_risk_usd
        broker_exec = candidate.broker_executable
        risk_ok = candidate.risk_acceptable
        if setup is not None and "risk_budget_usd" in setup.risk_snapshot:
            raw_b = setup.risk_snapshot.get("risk_budget_usd")
            risk_budget = float(raw_b) if isinstance(raw_b, (int, float)) else None
    elif setup is not None and market is not None and equity is not None and equity > 0:
        # Display-only sizing when candidate withheld due to ineligibility.
        sizing, _blocks = size_position(
            equity=float(equity),
            risk_percent=float(settings.risk_per_trade_pct),
            entry=float(setup.entry_price),
            stop_loss=float(setup.stop_loss),
            symbol=market.symbol,
        )
        proposed_volume = sizing.normalized_volume
        estimated_risk = sizing.estimated_risk_usd
        risk_budget = sizing.risk_budget_usd
        broker_exec = sizing.broker_executable
        risk_ok = sizing.risk_acceptable
    elif setup is not None and "risk_budget_usd" in setup.risk_snapshot:
        raw_b = setup.risk_snapshot.get("risk_budget_usd")
        risk_budget = float(raw_b) if isinstance(raw_b, (int, float)) else None

    block = tuple(status.reasons) if not status.eligible else ()
    if blocked_message and blocked_message not in block:
        block = (*block, blocked_message)

    return WatchSnapshot(
        timestamp=ts,
        symbol=symbol,
        data_state=data_state,
        final_signal=final_signal,
        confidence=status.confidence_score,
        confidence_meaning=status.confidence_meaning or "EVIDENCE_ALIGNMENT",
        setup_id=status.setup_id,
        setup_state=status.setup_state,
        analysis_fingerprint=status.analysis_fingerprint,
        entry_zone_low=None if setup is None else setup.entry_zone_low,
        entry_zone_high=None if setup is None else setup.entry_zone_high,
        executable_price=exec_px,
        stop_loss=None if setup is None else setup.stop_loss,
        tp1=_tp_at(setup, 0),
        tp2=_tp_at(setup, 1),
        tp3=_tp_at(setup, 2),
        proposed_volume=proposed_volume,
        estimated_risk_usd=estimated_risk,
        risk_budget_usd=risk_budget,
        broker_executable=broker_exec,
        risk_acceptable=risk_ok,
        candidate_eligible=bool(status.eligible),
        block_reasons=block,
        bid=bid,
        ask=ask,
        raw_spread_points=raw_spread,
        normalized_spread_points=normalized,
        max_spread_points=max_spread,
        mtf_diagnostics=mtf_diagnostics,
    )


def _diagnostics_from_analysis(analysis: Any) -> MtfDecisionDiagnostics | None:
    if analysis is None or analysis.aggregate_trace is None:
        return None
    weights = analysis.tf_weights or {
        "M15": 0.20,
        "H1": 0.30,
        "H4": 0.30,
        "D1": 0.20,
    }
    return build_mtf_decision_diagnostics(
        analysis,
        weights=weights,
        trace=analysis.aggregate_trace,
    )


def poll_watch_once(
    *,
    settings: Settings,
    provider: Any,
    setup_store: SetupLifecycleStore,
    symbol: str,
    probe: ReadOnlyMt5DemoProbe | None = None,
    now: datetime | None = None,
) -> WatchSnapshot:
    """Single read-only evaluation — stops before any execution orchestration."""
    built = build_candidate_status_from_mtf_provider(
        settings=settings,
        provider=provider,
        setup_store=setup_store,
        symbol=symbol,
    )
    mtf_diag = _diagnostics_from_analysis(built.analysis)

    market: DemoMarketSnapshot | None = None
    equity: float | None = None
    try:
        broker_sym = resolve_broker_symbol_explicit(settings)
        if probe is not None:
            identity = probe.fetch_account()
            equity = float(identity.account.equity)
            market = probe.fetch_market(broker_sym)
        else:
            tick = provider.get_tick(symbol)
            info = provider.get_symbol_info(broker_sym)
            snap = provider.get_snapshot()
            account = getattr(snap, "account", None)
            if account is not None:
                equity = float(getattr(account, "equity", 0.0) or 0.0)
            if tick is not None and info is not None:
                point = float(info.point) if info.point > 0 else 0.01
                market = DemoMarketSnapshot(
                    symbol=info,
                    tick=tick,
                    freshness=QuoteFreshness.LIVE,
                    age_seconds=0.0,
                    spread_points=abs(float(tick.ask) - float(tick.bid)) / point,
                )
    except Exception:
        market = None

    if built.blocked_result is not None:
        data_state = "UNAVAILABLE"
        if "MTF_DATA_UNAVAILABLE" in built.blocked_result:
            data_state = "UNAVAILABLE"
        return build_watch_snapshot(
            symbol=symbol,
            settings=settings,
            status=None,
            setup=None,
            candidate=None,
            final_signal=built.final_signal or "WAIT",
            market=market,
            equity=equity,
            data_state=data_state,
            blocked_message=built.blocked_result.split(":", 1)[0],
            now=now,
            mtf_diagnostics=mtf_diag,
        )

    assert built.status is not None
    status = built.status
    setup = setup_store.get(status.setup_id) if status.setup_id else None
    final_signal = built.final_signal or (
        "WAIT"
        if "FINAL_SIGNAL_WAIT" in status.reasons
        else (
            status.candidate.side
            if status.candidate is not None
            else (setup.direction if setup is not None else "WAIT")
        )
    )

    return build_watch_snapshot(
        symbol=symbol,
        settings=settings,
        status=status,
        setup=setup,
        candidate=status.candidate,
        final_signal=final_signal,
        market=market,
        equity=equity,
        data_state="LIVE",
        now=now,
        mtf_diagnostics=mtf_diag,
    )


def clamp_interval_seconds(value: float) -> float:
    return max(float(MIN_INTERVAL_SECONDS), float(value))


def run_watch_loop(
    *,
    poll_fn: Callable[[], WatchSnapshot],
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    stop_event: threading.Event | None = None,
    max_iterations: int | None = None,
    out: TextIO | None = None,
    install_signals: bool = True,
    verbose_analysis: bool = False,
    beep: bool = False,
    alert_log: str | None = None,
) -> int:
    """
    Poll until stop / max_iterations.

    Pure control loop — poll_fn must remain read-only.
    """
    import sys
    from pathlib import Path

    from exness_bot.execution.integration.demo_watch_alerts import (
        emit_alerts,
        evaluate_watch_alerts,
    )

    stream = out or sys.stdout
    stop = stop_event or threading.Event()
    interval = clamp_interval_seconds(interval_seconds)
    prev: WatchSnapshot | None = None
    iterations = 0
    seen_alert_keys: set[str] = set()
    log_path = Path(alert_log) if alert_log else None

    def handle_signal(_signum: int, _frame: object) -> None:
        stop.set()

    if install_signals and threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    print(WATCHER_AGENT_NOTE, file=stream)
    print(
        f"Watching (interval={interval}s, verbose_analysis={verbose_analysis}, "
        f"beep={beep}, alert_log={alert_log or 'off'}). "
        "Ctrl+C to stop. Broker mutation: NO",
        file=stream,
    )

    try:
        while not stop.is_set():
            snap = poll_fn()
            iterations += 1
            if meaningful_change(prev, snap):
                print(
                    "\n".join(
                        [
                            "",
                            *format_full_report(
                                snap, verbose_analysis=verbose_analysis
                            ),
                        ]
                    ),
                    file=stream,
                )
            else:
                print(format_heartbeat(snap), file=stream)

            alerts = evaluate_watch_alerts(prev, snap, seen_keys=seen_alert_keys)
            if alerts:
                emit_alerts(
                    alerts,
                    snap=snap,
                    out=stream,
                    beep_enabled=beep,
                    alert_log=log_path,
                )

            prev = snap
            if max_iterations is not None and iterations >= max_iterations:
                break
            if stop.wait(interval):
                break
    finally:
        print("", file=stream)
        print("Watcher stopped.", file=stream)
        print("Broker mutation performed: NO", file=stream)
    return 0


def _watch_setup_store(settings: Settings) -> SetupLifecycleStore:
    """Durable sqlite store when available — never imports execution factory."""
    url = str(getattr(settings, "database_url", "sqlite:///exness_bot.db"))
    if str(url).startswith("sqlite"):
        try:
            return SqliteSetupLifecycleStore(url)
        except Exception:
            return InMemorySetupLifecycleStore()
    return InMemorySetupLifecycleStore()


def handle_candidate_demo_watch(
    *,
    symbol: str = "XAUUSD",
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    max_iterations: int | None = None,
    verbose_analysis: bool = False,
    beep: bool = False,
    alert_log: str | None = None,
) -> int:
    """CLI entry — read-only MT5 observation loop."""
    from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient

    settings = Settings()
    setup_store = _watch_setup_store(settings)
    interval = clamp_interval_seconds(interval_seconds)
    manager: MT5ConnectionManager | None = None
    stop = threading.Event()

    def poll() -> WatchSnapshot:
        nonlocal manager
        try:
            if manager is None:
                readonly = MT5ReadOnlyClient(settings)
                manager = MT5ConnectionManager(settings, client=readonly)
                status = manager.connect()
                if status.state != ConnectionState.CONNECTED:
                    return _unavailable_snapshot(
                        symbol=symbol,
                        data_state="DISCONNECTED",
                        max_spread_points=int(settings.max_spread_points),
                        message_reason="DISCONNECTED",
                    )
            else:
                health = manager.health_check()
                if health.state != ConnectionState.CONNECTED:
                    with suppress(Exception):
                        manager.reconnect()
                    health = manager.health_check()
                    if health.state != ConnectionState.CONNECTED:
                        return _unavailable_snapshot(
                            symbol=symbol,
                            data_state="DISCONNECTED",
                            max_spread_points=int(settings.max_spread_points),
                            message_reason="DISCONNECTED",
                        )

            assert manager is not None
            provider = MT5TradingDataProvider(settings, connection_manager=manager)
            probe = ReadOnlyMt5DemoProbe(
                manager.client,
                stale_after_seconds=settings.live_data_stale_seconds,
            )
            return poll_watch_once(
                settings=settings,
                provider=provider,
                setup_store=setup_store,
                symbol=symbol,
                probe=probe,
            )
        except Exception:
            return _unavailable_snapshot(
                symbol=symbol,
                data_state="UNAVAILABLE",
                max_spread_points=int(settings.max_spread_points),
                message_reason="DATA_UNAVAILABLE",
            )

    try:
        return run_watch_loop(
            poll_fn=poll,
            interval_seconds=interval,
            stop_event=stop,
            max_iterations=max_iterations,
            install_signals=True,
            verbose_analysis=verbose_analysis,
            beep=beep,
            alert_log=alert_log,
        )
    finally:
        if manager is not None:
            with suppress(Exception):
                manager.disconnect()
