"""Phase 17.2.4 — read-only watcher alert tests."""

from __future__ import annotations

import ast
import inspect
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from exness_bot.execution.integration.demo_watch import (
    WatchSnapshot,
    is_ready,
    run_watch_loop,
)
from exness_bot.execution.integration.demo_watch_alerts import (
    WatchAlertKind,
    alert_identity_key,
    evaluate_watch_alerts,
    format_ready_alert,
    try_beep,
)
from exness_bot.market_analysis.mtf_diagnostics import MtfDecisionDiagnostics
from exness_bot.market_analysis.mtf_service import MTF_LONG_THRESHOLD, MTF_SHORT_THRESHOLD

_NOW = datetime(2026, 9, 8, 22, 0, tzinfo=UTC)


def _diag(score: float) -> MtfDecisionDiagnostics:
    return MtfDecisionDiagnostics(
        slices=(),
        m15_score=score,
        h1_score=score,
        h4_score=score,
        d1_score=score,
        mtf_weighted_score=score,
        long_threshold=MTF_LONG_THRESHOLD,
        short_threshold=MTF_SHORT_THRESHOLD,
        base_direction="WAIT",
        h1_h4_conflict=False,
        h4_d1_conflict=False,
        conflict_penalty=1.0,
        final_signal="WAIT",
        confidence=40.0,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        decision_reasons=("SCORE_INSIDE_WAIT_ZONE",),
        distance_to_long_threshold=MTF_LONG_THRESHOLD - score,
        distance_to_short_threshold=score - MTF_SHORT_THRESHOLD,
    )


def _snap(**overrides: object) -> WatchSnapshot:
    base: dict[str, object] = dict(
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
        mtf_diagnostics=_diag(0.0),
    )
    base.update(overrides)
    return WatchSnapshot(**base)  # type: ignore[arg-type]


def test_wait_repeated_no_alert_spam() -> None:
    seen: set[str] = set()
    a = _snap()
    b = _snap(timestamp=_NOW + timedelta(seconds=15))
    assert evaluate_watch_alerts(a, b, seen_keys=seen) == []
    assert evaluate_watch_alerts(b, b, seen_keys=seen) == []


def test_wait_to_short_directional_once() -> None:
    seen: set[str] = set()
    wait = _snap()
    short = _snap(
        final_signal="SHORT",
        setup_state="WAITING_FOR_ENTRY",
        setup_id="sid-1",
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        executable_price=2350.0,
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
        mtf_diagnostics=_diag(-25.0),
    )
    first = evaluate_watch_alerts(wait, short, seen_keys=seen)
    assert any(a.kind == WatchAlertKind.DIRECTIONAL for a in first)
    # Also fix first assertion - lines from DIRECTIONAL alert specifically
    dir_alert = next(a for a in first if a.kind == WatchAlertKind.DIRECTIONAL)
    assert "DIRECTIONAL SETUP DETECTED" in "\n".join(dir_alert.lines)
    second = evaluate_watch_alerts(short, short, seen_keys=seen)
    assert second == []


def test_short_waiting_repeated_no_spam() -> None:
    seen: set[str] = set()
    wait = _snap()
    short = _snap(
        final_signal="SHORT",
        setup_state="WAITING_FOR_ENTRY",
        setup_id="sid-1",
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    assert evaluate_watch_alerts(wait, short, seen_keys=seen)
    again = _snap(
        timestamp=_NOW + timedelta(seconds=15),
        final_signal="SHORT",
        setup_state="WAITING_FOR_ENTRY",
        setup_id="sid-1",
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    assert evaluate_watch_alerts(short, again, seen_keys=seen) == []


def test_waiting_to_entry_zone_alert() -> None:
    seen: set[str] = set()
    waiting = _snap(
        final_signal="LONG",
        setup_state="WAITING_FOR_ENTRY",
        setup_id="sid-1",
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    entry = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id="sid-1",
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        executable_price=2340.0,
        block_reasons=("SPREAD_TOO_WIDE",),
        candidate_eligible=False,
    )
    alerts = evaluate_watch_alerts(waiting, entry, seen_keys=seen)
    kinds = {a.kind for a in alerts}
    assert WatchAlertKind.ENTRY_ZONE in kinds


def test_eligible_false_to_true_ready_once() -> None:
    seen: set[str] = set()
    blocked = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id="sid-ready",
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        executable_price=2340.0,
        stop_loss=2330.0,
        tp1=2355.0,
        proposed_volume=0.02,
        estimated_risk_usd=20.0,
        risk_budget_usd=50.0,
        candidate_eligible=False,
        block_reasons=("SPREAD_TOO_WIDE",),
        mtf_diagnostics=_diag(25.0),
    )
    ready = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id="sid-ready",
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        executable_price=2340.0,
        stop_loss=2330.0,
        tp1=2355.0,
        proposed_volume=0.02,
        estimated_risk_usd=20.0,
        risk_budget_usd=50.0,
        candidate_eligible=True,
        block_reasons=(),
        mtf_diagnostics=_diag(25.0),
    )
    assert is_ready(ready)
    alerts = evaluate_watch_alerts(blocked, ready, seen_keys=seen)
    ready_alerts = [a for a in alerts if a.kind == WatchAlertKind.READY]
    assert len(ready_alerts) == 1
    text = "\n".join(ready_alerts[0].lines)
    assert "CONTROLLED DEMO CANDIDATE READY" in text
    assert "READY IS INFORMATIONAL ONLY" in text
    assert "MTF_SCORE:" in text
    # same identity → no second READY
    assert evaluate_watch_alerts(ready, ready, seen_keys=seen) == []


def test_block_reasons_changed_alert_once() -> None:
    seen: set[str] = set()
    a = _snap(block_reasons=("FINAL_SIGNAL_WAIT",))
    b = _snap(block_reasons=("FINAL_SIGNAL_WAIT", "SPREAD_TOO_WIDE"))
    alerts = evaluate_watch_alerts(a, b, seen_keys=seen)
    assert any(x.kind == WatchAlertKind.BLOCK_REASONS for x in alerts)
    assert evaluate_watch_alerts(b, b, seen_keys=seen) == []


def test_sound_failure_does_not_crash() -> None:
    with patch(
        "winsound.MessageBeep",
        side_effect=RuntimeError("no sound"),
    ):
        assert try_beep() in {True, False}


def test_try_beep_never_raises() -> None:
    # Always callable without exception
    try_beep()


def test_alert_log_written(tmp_path: Path) -> None:
    from exness_bot.execution.integration.demo_watch_alerts import append_alert_log

    seen: set[str] = set()
    wait = _snap()
    short = _snap(
        final_signal="SHORT",
        setup_state="WAITING_FOR_ENTRY",
        setup_id="sid-log",
        block_reasons=("PRICE_NOT_IN_ENTRY_ZONE",),
    )
    alerts = evaluate_watch_alerts(wait, short, seen_keys=seen)
    log = tmp_path / "alerts.log"
    append_alert_log(log, snap=short, alert=alerts[0])
    text = log.read_text(encoding="utf-8")
    assert "DIRECTIONAL" in text
    assert "password" not in text.lower()
    assert "sid-log" in text


def test_loop_ready_alert_once() -> None:
    buf = io.StringIO()
    blocked = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id="sid-loop",
        candidate_eligible=False,
        block_reasons=("SPREAD_TOO_WIDE",),
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        stop_loss=2330.0,
        tp1=2355.0,
        proposed_volume=0.02,
        mtf_diagnostics=_diag(22.0),
    )
    ready = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        setup_id="sid-loop",
        candidate_eligible=True,
        block_reasons=(),
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        executable_price=2340.0,
        stop_loss=2330.0,
        tp1=2355.0,
        proposed_volume=0.02,
        estimated_risk_usd=20.0,
        risk_budget_usd=50.0,
        mtf_diagnostics=_diag(22.0),
    )
    still = WatchSnapshot(
        **{**ready.__dict__, "timestamp": _NOW + timedelta(seconds=15)}
    )
    seq = [blocked, ready, still]
    idx = {"i": 0}

    def poll() -> WatchSnapshot:
        i = idx["i"]
        snap = seq[min(i, len(seq) - 1)]
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


def test_cli_flags_no_execute() -> None:
    from exness_bot.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "candidate-demo-watch",
            "--beep",
            "--alert-log",
            "logs/candidate_watch_alerts.log",
        ]
    )
    assert args.beep is True
    assert args.alert_log.endswith("candidate_watch_alerts.log")
    assert not hasattr(args, "execute")
    assert not hasattr(args, "confirm")


def test_alert_module_no_mutation_imports() -> None:
    import exness_bot.execution.integration.demo_watch_alerts as mod

    source = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = (
        "exness_bot.execution.orchestrator",
        "exness_bot.broker.mt5.executor",
        "exness_bot.broker.mt5.execution_transport",
        "exness_bot.execution.integration.demo_factory",
    )
    for mod_name in forbidden:
        assert mod_name not in imported


def test_ready_alert_format_fields() -> None:
    ready = _snap(
        final_signal="LONG",
        setup_state="ENTRY_ZONE",
        candidate_eligible=True,
        block_reasons=(),
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        executable_price=2340.0,
        stop_loss=2330.0,
        tp1=2355.0,
        proposed_volume=0.02,
        estimated_risk_usd=12.0,
        risk_budget_usd=50.0,
        mtf_diagnostics=_diag(21.0),
    )
    text = "\n".join(format_ready_alert(ready))
    for label in (
        "SYMBOL:",
        "DIRECTION:",
        "MTF_SCORE:",
        "ENTRY_ZONE:",
        "EXECUTABLE_PRICE:",
        "SL:",
        "TP1:",
        "PROPOSED_VOLUME:",
        "ESTIMATED_RISK_USD:",
        "RISK_BUDGET_USD:",
    ):
        assert label in text


def test_identity_key_stable() -> None:
    a = _snap(setup_id="x", setup_state="ENTRY_ZONE", candidate_eligible=False)
    b = _snap(
        timestamp=_NOW + timedelta(seconds=30),
        setup_id="x",
        setup_state="ENTRY_ZONE",
        candidate_eligible=False,
    )
    assert alert_identity_key(a) == alert_identity_key(b)
