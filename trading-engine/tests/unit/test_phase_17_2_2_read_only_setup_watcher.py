"""Phase 17.2.2 — read-only setup watcher tests (no broker mutation)."""

from __future__ import annotations

import ast
import inspect
import io
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.config.settings import Settings
from exness_bot.execution.integration import demo_watch as demo_watch_mod
from exness_bot.execution.integration.demo_watch import (
    DEFAULT_INTERVAL_SECONDS,
    MIN_INTERVAL_SECONDS,
    WatchSnapshot,
    build_watch_snapshot,
    clamp_interval_seconds,
    format_full_report,
    format_heartbeat,
    format_ready_banner,
    is_ready,
    meaningful_change,
    ready_transition,
    run_watch_loop,
)
from exness_bot.market_analysis.contract.identity import (
    ANALYSIS_CONTRACT_VERSION,
    MTF_STRATEGY_ID,
    compute_analysis_fingerprint,
    compute_setup_id,
)
from exness_bot.market_analysis.contract.lifecycle import compute_expires_at
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    EligibilityResult,
    ExecutionCandidate,
    ExecutionCandidateStatus,
    SetupLifecycleState,
)
from exness_bot.market_analysis.setup import TakeProfitLevel

_NOW = datetime(2026, 9, 8, 18, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings.model_construct(
        max_spread_points=260,
        risk_per_trade_pct=0.5,
    )


def _setup(
    *,
    state: SetupLifecycleState = SetupLifecycleState.ENTRY_ZONE,
    setup_id: str | None = None,
) -> CanonicalTradeSetup:
    c = _NOW - timedelta(minutes=5)
    tps = (
        TakeProfitLevel(1, 2355.0, 30.0, 1.5, "TP1"),
        TakeProfitLevel(2, 2370.0, 40.0, 3.0, "TP2"),
        TakeProfitLevel(3, 2390.0, 30.0, 5.0, "TP3"),
    )
    sid = setup_id or compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=c,
        direction="LONG",
    )
    fp = compute_analysis_fingerprint(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=c,
        direction="LONG",
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        stop_loss=2330.0,
        take_profit_prices=[2355.0, 2370.0, 2390.0],
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )
    return CanonicalTradeSetup(
        setup_id=sid,
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        primary_timeframe="M15",
        direction="LONG",
        source_candle_timestamp=c,
        created_at=_NOW,
        expires_at=compute_expires_at(
            source_candle_timestamp=c, primary_timeframe="M15", max_candles=8
        ),
        entry_type="PULLBACK",
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        entry_price=2340.0,
        stop_loss=2330.0,
        take_profits=tps,
        confidence_score=80.0,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        analysis_fingerprint=fp,
        state=state,
        risk_snapshot={"risk_budget_usd": 50.0},
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )


def _status(
    *,
    eligible: bool = False,
    setup_state: str = "NO_SETUP",
    setup_id: str | None = None,
    fingerprint: str | None = None,
    reasons: tuple[str, ...] = ("FINAL_SIGNAL_WAIT", "NO_DIRECTIONAL_SETUP"),
    candidate: ExecutionCandidate | None = None,
    confidence: float | None = 40.0,
) -> ExecutionCandidateStatus:
    return ExecutionCandidateStatus(
        eligible=eligible,
        setup_state=setup_state,
        setup_id=setup_id,
        analysis_fingerprint=fingerprint,
        candidate=candidate,
        reasons=reasons,
        warnings=(),
        strategy_id=MTF_STRATEGY_ID,
        confidence_score=confidence,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        generated_at=_NOW,
    )


def _candidate(setup: CanonicalTradeSetup) -> ExecutionCandidate:
    elig = EligibilityResult(
        eligible=True,
        reasons=("ALL_CHECKS_PASSED",),
        blocking=(),
        warnings=(),
    )
    return ExecutionCandidate(
        candidate_id="cand-1",
        setup_id=setup.setup_id,
        analysis_fingerprint=setup.analysis_fingerprint,
        symbol=setup.symbol,
        broker_symbol=setup.broker_symbol,
        side="LONG",
        entry=setup.entry_price,
        stop_loss=setup.stop_loss,
        take_profits=setup.take_profits,
        proposed_volume=0.02,
        estimated_risk_usd=20.0,
        estimated_risk_pct=0.2,
        broker_executable=True,
        risk_acceptable=True,
        eligibility=elig,
        created_at=_NOW,
    )


def _snap(**overrides: object) -> WatchSnapshot:
    base = dict(
        timestamp=_NOW,
        symbol="XAUUSD",
        data_state="LIVE",
        final_signal="WAIT",
        confidence=40.0,
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
        block_reasons=("FINAL_SIGNAL_WAIT", "NO_DIRECTIONAL_SETUP"),
        bid=2340.0,
        ask=2342.6,
        raw_spread_points=260.0,
        normalized_spread_points=260.0,
        max_spread_points=260,
    )
    base.update(overrides)
    return WatchSnapshot(**base)  # type: ignore[arg-type]


def test_clamp_interval_minimum() -> None:
    assert clamp_interval_seconds(1) == MIN_INTERVAL_SECONDS
    assert clamp_interval_seconds(15) == DEFAULT_INTERVAL_SECONDS


def test_no_setup_heartbeat() -> None:
    snap = _snap()
    line = format_heartbeat(snap)
    assert "NO_SETUP" in line
    assert "WAIT" in line
    assert "XAUUSD" in line


def test_transition_no_setup_to_waiting() -> None:
    a = _snap()
    b = _snap(
        final_signal="LONG",
        setup_state="WAITING_FOR_ENTRY",
        setup_id="sid-1",
        analysis_fingerprint="fp-1",
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    assert meaningful_change(a, b)
    assert not is_ready(b)


def test_transition_waiting_to_entry_zone() -> None:
    a = _snap(
        final_signal="LONG",
        setup_state="WAITING_FOR_ENTRY",
        setup_id="sid-1",
        analysis_fingerprint="fp-1",
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    b = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id="sid-1",
        analysis_fingerprint="fp-1",
        block_reasons=("SPREAD_TOO_WIDE",),
    )
    assert meaningful_change(a, b)


def test_transition_entry_zone_to_waiting() -> None:
    a = _snap(final_signal="LONG", setup_state="ENTRY_ZONE", setup_id="sid-1")
    b = _snap(
        final_signal="LONG",
        setup_state="WAITING_FOR_ENTRY",
        setup_id="sid-1",
    )
    assert meaningful_change(a, b)


def test_transition_invalidated_expired_superseded() -> None:
    base = _snap(final_signal="LONG", setup_state="ENTRY_ZONE", setup_id="sid-1")
    for state in ("INVALIDATED", "EXPIRED", "SUPERSEDED"):
        nxt = _snap(final_signal="LONG", setup_state=state, setup_id="sid-1")
        assert meaningful_change(base, nxt)


def test_setup_id_stability_quote_only_no_change() -> None:
    """Quote moves must not invent a new setup_id in the watch model."""
    setup = _setup()
    status = _status(
        eligible=False,
        setup_state="WAITING_FOR_ENTRY",
        setup_id=setup.setup_id,
        fingerprint=setup.analysis_fingerprint,
        reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    s1 = build_watch_snapshot(
        symbol="XAUUSD",
        settings=_settings(),
        status=status,
        setup=setup,
        candidate=None,
        final_signal="LONG",
        market=None,
        equity=10_000.0,
        now=_NOW,
    )
    s2 = build_watch_snapshot(
        symbol="XAUUSD",
        settings=_settings(),
        status=status,
        setup=setup,
        candidate=None,
        final_signal="LONG",
        market=None,
        equity=10_000.0,
        now=_NOW + timedelta(seconds=15),
    )
    assert s1.setup_id == s2.setup_id == setup.setup_id
    assert s1.analysis_fingerprint == s2.analysis_fingerprint
    # timestamp alone is not a meaningful watch change
    assert not meaningful_change(
        s1,
        WatchSnapshot(**{**s1.__dict__, "timestamp": s2.timestamp, "bid": 2341.0}),
    )


def test_block_reason_change_is_meaningful() -> None:
    a = _snap(block_reasons=("FINAL_SIGNAL_WAIT",))
    b = _snap(block_reasons=("FINAL_SIGNAL_WAIT", "SPREAD_TOO_WIDE"))
    assert meaningful_change(a, b)


def test_eligible_false_to_true_and_ready_once() -> None:
    setup = _setup()
    not_ready = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id=setup.setup_id,
        analysis_fingerprint=setup.analysis_fingerprint,
        candidate_eligible=False,
        block_reasons=("SPREAD_TOO_WIDE",),
        stop_loss=setup.stop_loss,
        tp1=2355.0,
        proposed_volume=0.02,
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
    )
    ready = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id=setup.setup_id,
        analysis_fingerprint=setup.analysis_fingerprint,
        candidate_eligible=True,
        block_reasons=(),
        stop_loss=setup.stop_loss,
        tp1=2355.0,
        proposed_volume=0.02,
        estimated_risk_usd=20.0,
        risk_budget_usd=50.0,
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        executable_price=2341.4,
        broker_executable=True,
        risk_acceptable=True,
    )
    assert meaningful_change(not_ready, ready)
    assert ready_transition(not_ready, ready)
    assert is_ready(ready)
    assert not ready_transition(ready, ready)

    banner = "\n".join(format_ready_banner(ready))
    assert "CONTROLLED DEMO CANDIDATE READY" in banner
    assert "BROKER MUTATION: NO" in banner or "NO BROKER MUTATION WAS PERFORMED" in banner
    assert "READY IS INFORMATIONAL ONLY" in banner
    assert "DIRECTION: LONG" in banner


def test_data_unavailable_snapshot() -> None:
    snap = build_watch_snapshot(
        symbol="XAUUSD",
        settings=_settings(),
        status=None,
        setup=None,
        candidate=None,
        final_signal="WAIT",
        market=None,
        equity=None,
        data_state="DISCONNECTED",
        blocked_message="DISCONNECTED",
        now=_NOW,
    )
    assert snap.data_state == "DISCONNECTED"
    assert snap.candidate_eligible is False
    assert "DISCONNECTED" in snap.block_reasons
    text = "\n".join(format_full_report(snap))
    assert "DATA_STATE: DISCONNECTED" in text


def test_run_loop_heartbeat_and_graceful_stop() -> None:
    buf = io.StringIO()
    stop = threading.Event()
    snaps = [
        _snap(),
        _snap(timestamp=_NOW + timedelta(seconds=15)),
        _snap(timestamp=_NOW + timedelta(seconds=30)),
    ]
    idx = {"i": 0}

    def poll() -> WatchSnapshot:
        i = idx["i"]
        idx["i"] = min(i + 1, len(snaps) - 1)
        return snaps[i]

    code = run_watch_loop(
        poll_fn=poll,
        interval_seconds=5,
        stop_event=stop,
        max_iterations=3,
        out=buf,
        install_signals=False,
    )
    assert code == 0
    out = buf.getvalue()
    assert "SETUP WATCH" in out  # first full report
    assert "NO_SETUP" in out
    assert "Watcher stopped." in out
    assert "Broker mutation performed: NO" in out


def test_ready_emitted_once_in_loop() -> None:
    buf = io.StringIO()
    setup = _setup()
    blocked = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id=setup.setup_id,
        candidate_eligible=False,
        block_reasons=("SPREAD_TOO_WIDE",),
    )
    ready = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id=setup.setup_id,
        candidate_eligible=True,
        block_reasons=(),
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        stop_loss=2330.0,
        tp1=2355.0,
        proposed_volume=0.02,
        estimated_risk_usd=20.0,
        risk_budget_usd=50.0,
    )
    still_ready = WatchSnapshot(
        **{**ready.__dict__, "timestamp": _NOW + timedelta(seconds=15)}
    )
    sequence = [blocked, ready, still_ready]
    idx = {"i": 0}

    def poll() -> WatchSnapshot:
        i = idx["i"]
        snap = sequence[min(i, len(sequence) - 1)]
        idx["i"] = i + 1
        return snap

    run_watch_loop(
        poll_fn=poll,
        interval_seconds=5,
        max_iterations=3,
        out=buf,
        install_signals=False,
    )
    assert buf.getvalue().count("CONTROLLED DEMO CANDIDATE READY") == 1


def test_cli_has_no_execute_or_confirm_flags() -> None:
    from exness_bot.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["candidate-demo-watch", "--symbol", "XAUUSD"])
    assert args.command == "candidate-demo-watch"
    assert not hasattr(args, "execute")
    assert not hasattr(args, "confirm")
    assert args.interval_seconds == 15.0


def test_demo_watch_module_has_no_mutation_imports() -> None:
    source = Path(inspect.getfile(demo_watch_mod)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            for alias in node.names:
                imported.add(f"{node.module}.{alias.name}")

    forbidden = (
        "exness_bot.execution.orchestrator",
        "exness_bot.execution.mt5.gated_port",
        "exness_bot.broker.mt5.executor",
        "exness_bot.broker.mt5.execution_transport",
        "exness_bot.execution.integration.demo_factory",
        "exness_bot.execution.integration.demo_cli",
        "exness_bot.execution.integration.demo_revalidate",
        "exness_bot.execution.integration.factory",
        "exness_bot.execution.integration.service",
    )
    for mod in forbidden:
        assert mod not in imported, f"forbidden import: {mod}"
        assert not any(
            name == mod or name.startswith(mod + ".") for name in imported
        ), f"forbidden import prefix: {mod}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "order_send":
            raise AssertionError("order_send attribute access found in demo_watch")
        if isinstance(node, ast.Name) and node.id == "order_send":
            raise AssertionError("order_send name found in demo_watch")


def test_importing_demo_watch_does_not_load_live_transport() -> None:
    import sys

    from exness_bot.execution.integration import candidate_status as cs

    cs_src = Path(inspect.getfile(cs)).read_text(encoding="utf-8")
    for token in (
        "LiveMT5ExecutionTransport",
        "GatedMT5ExecutionPort",
        "ExecutionOrchestrator",
        "order_send",
        "demo_factory",
    ):
        assert token not in cs_src

    assert "exness_bot.execution.integration.demo_watch" in sys.modules


def test_full_report_contains_required_labels() -> None:
    setup = _setup()
    status = _status(
        eligible=False,
        setup_state="ENTRY_ZONE",
        setup_id=setup.setup_id,
        fingerprint=setup.analysis_fingerprint,
        reasons=("RISK_NOT_ACCEPTABLE", "MIN_VOLUME_EXCEEDS_RISK_BUDGET"),
    )
    snap = build_watch_snapshot(
        symbol="XAUUSD",
        settings=_settings(),
        status=status,
        setup=setup,
        candidate=None,
        final_signal="LONG",
        market=None,
        equity=None,
        now=_NOW,
    )
    text = "\n".join(format_full_report(snap))
    for label in (
        "TIMESTAMP:",
        "BID:",
        "ASK:",
        "RAW_SPREAD_POINTS:",
        "NORMALIZED_SPREAD_POINTS:",
        "MAX_SPREAD_POINTS:",
        "FINAL_SIGNAL:",
        "CONFIDENCE:",
        "CONFIDENCE_MEANING:",
        "SETUP_ID:",
        "SETUP_STATE:",
        "ENTRY_ZONE_LOW:",
        "ENTRY_ZONE_HIGH:",
        "EXECUTABLE_PRICE:",
        "SL:",
        "TP1:",
        "TP2:",
        "TP3:",
        "PROPOSED_VOLUME:",
        "ESTIMATED_RISK_USD:",
        "RISK_BUDGET_USD:",
        "BROKER_EXECUTABLE:",
        "RISK_ACCEPTABLE:",
        "CANDIDATE_ELIGIBLE:",
        "BLOCK_REASONS:",
    ):
        assert label in text
    assert "MIN_VOLUME_EXCEEDS_RISK_BUDGET" in text
