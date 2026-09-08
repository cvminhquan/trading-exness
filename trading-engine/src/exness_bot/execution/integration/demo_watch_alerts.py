"""Phase 17.2.4 — read-only watcher alerts (no broker mutation).

Deduped terminal/log/beep notifications for significant watch transitions.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from exness_bot.market_analysis.mtf_service import (
    MTF_LONG_THRESHOLD,
    MTF_SHORT_THRESHOLD,
)

if TYPE_CHECKING:
    from exness_bot.execution.integration.demo_watch import WatchSnapshot


class WatchAlertKind(StrEnum):
    DIRECTIONAL = "DIRECTIONAL"
    READY = "READY"
    ENTRY_ZONE = "ENTRY_ZONE"
    THRESHOLD_CROSS_LONG = "THRESHOLD_CROSS_LONG"
    THRESHOLD_CROSS_SHORT = "THRESHOLD_CROSS_SHORT"
    BLOCK_REASONS = "BLOCK_REASONS"
    BLOCKED_AFTER_ENTRY = "BLOCKED_AFTER_ENTRY"
    ELIGIBLE = "ELIGIBLE"
    SETUP_STATE = "SETUP_STATE"


@dataclass(frozen=True)
class WatchAlert:
    kind: WatchAlertKind
    lines: tuple[str, ...]
    dedupe_key: str
    beep: bool = False


def _fmt(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.5g}"
    return str(value)


def alert_identity_key(snap: WatchSnapshot) -> str:
    """Spam key: setup_id + setup_state + eligible + block_reasons."""
    reasons = ",".join(snap.block_reasons)
    return (
        f"{snap.setup_id or '-'}|{snap.setup_state}|"
        f"{int(snap.candidate_eligible)}|{reasons}"
    )


def _weighted(snap: WatchSnapshot | None) -> float | None:
    if snap is None or snap.mtf_diagnostics is None:
        return None
    return snap.mtf_diagnostics.mtf_weighted_score


def distance_to_entry_zone(snap: WatchSnapshot) -> float | None:
    """Distance from executable price to nearest edge of entry zone."""
    px = snap.executable_price
    lo = snap.entry_zone_low
    hi = snap.entry_zone_high
    if px is None or lo is None or hi is None:
        return None
    if lo <= px <= hi:
        return 0.0
    if px < lo:
        return float(lo - px)
    return float(px - hi)


def format_directional_alert(snap: WatchSnapshot) -> tuple[str, ...]:
    entry = "N/A"
    if snap.entry_zone_low is not None and snap.entry_zone_high is not None:
        entry = f"{_fmt(snap.entry_zone_low)} - {_fmt(snap.entry_zone_high)}"
    dist = distance_to_entry_zone(snap)
    return (
        "========================================",
        "DIRECTIONAL SETUP DETECTED",
        "========================================",
        f"Direction: {snap.final_signal}",
        f"Setup state: {snap.setup_state}",
        f"Entry zone: {entry}",
        f"Current executable price: {_fmt(snap.executable_price)}",
        f"Distance to entry zone: {_fmt(dist)}",
        "",
        "No execution.",
        "BROKER MUTATION: NO",
        "========================================",
    )


def format_ready_alert(snap: WatchSnapshot) -> tuple[str, ...]:
    entry = "N/A"
    if snap.entry_zone_low is not None and snap.entry_zone_high is not None:
        entry = f"{_fmt(snap.entry_zone_low)} - {_fmt(snap.entry_zone_high)}"
    score = _weighted(snap)
    return (
        "========================================",
        "CONTROLLED DEMO CANDIDATE READY",
        "========================================",
        f"SYMBOL: {snap.symbol}",
        f"DIRECTION: {snap.final_signal}",
        f"MTF_SCORE: {_fmt(score)}",
        f"ENTRY_ZONE: {entry}",
        f"EXECUTABLE_PRICE: {_fmt(snap.executable_price)}",
        f"SL: {_fmt(snap.stop_loss)}",
        f"TP1: {_fmt(snap.tp1)}",
        f"PROPOSED_VOLUME: {_fmt(snap.proposed_volume)}",
        f"ESTIMATED_RISK_USD: {_fmt(snap.estimated_risk_usd)}",
        f"RISK_BUDGET_USD: {_fmt(snap.risk_budget_usd)}",
        "========================================",
        "",
        "IMPORTANT:",
        "READY IS INFORMATIONAL ONLY.",
        "NO BROKER MUTATION WAS PERFORMED.",
        "RUN PREVIEW MANUALLY BEFORE ANY DEMO ACTION.",
        "========================================",
    )


def format_entry_zone_alert(snap: WatchSnapshot) -> tuple[str, ...]:
    return (
        "========================================",
        "ENTRY_ZONE REACHED",
        "========================================",
        f"SYMBOL: {snap.symbol}",
        f"DIRECTION: {snap.final_signal}",
        f"SETUP_ID: {_fmt(snap.setup_id)}",
        f"CANDIDATE_ELIGIBLE: {_fmt(snap.candidate_eligible)}",
        f"BLOCK_REASONS: {', '.join(snap.block_reasons) if snap.block_reasons else '—'}",
        "BROKER MUTATION: NO",
        "========================================",
    )


def format_generic_alert(kind: WatchAlertKind, snap: WatchSnapshot) -> tuple[str, ...]:
    score = _weighted(snap)
    return (
        "========================================",
        f"WATCH ALERT: {kind.value}",
        "========================================",
        f"SYMBOL: {snap.symbol}",
        f"FINAL_SIGNAL: {snap.final_signal}",
        f"SETUP_STATE: {snap.setup_state}",
        f"SETUP_ID: {_fmt(snap.setup_id)}",
        f"MTF_SCORE: {_fmt(score)}",
        f"CANDIDATE_ELIGIBLE: {_fmt(snap.candidate_eligible)}",
        f"BLOCK_REASONS: {', '.join(snap.block_reasons) if snap.block_reasons else '—'}",
        "BROKER MUTATION: NO",
        "========================================",
    )


def evaluate_watch_alerts(
    prev: WatchSnapshot | None,
    curr: WatchSnapshot,
    *,
    seen_keys: set[str],
) -> list[WatchAlert]:
    """
    Build alerts for significant transitions.

    Dedupes by alert kind + identity key (setup_id/state/eligible/reasons).
    Mutates ``seen_keys`` when an alert is emitted.
    """
    from exness_bot.execution.integration.demo_watch import is_ready

    alerts: list[WatchAlert] = []
    identity = alert_identity_key(curr)

    def _emit(kind: WatchAlertKind, lines: tuple[str, ...], *, beep: bool) -> None:
        key = f"{kind.value}|{identity}"
        if key in seen_keys:
            return
        seen_keys.add(key)
        alerts.append(WatchAlert(kind=kind, lines=lines, dedupe_key=key, beep=beep))

    if (
        prev is not None
        and prev.final_signal == "WAIT"
        and curr.final_signal in {"LONG", "SHORT"}
        and curr.setup_state != "ENTRY_ZONE"
    ) or (
        prev is None
        and curr.final_signal in {"LONG", "SHORT"}
        and curr.setup_state not in {"ENTRY_ZONE", "NO_SETUP"}
    ):
        _emit(WatchAlertKind.DIRECTIONAL, format_directional_alert(curr), beep=True)

    if is_ready(curr) and (prev is None or not is_ready(prev)):
        _emit(WatchAlertKind.READY, format_ready_alert(curr), beep=True)

    if (
        prev is not None
        and prev.setup_state != "ENTRY_ZONE"
        and curr.setup_state == "ENTRY_ZONE"
    ):
        _emit(WatchAlertKind.ENTRY_ZONE, format_entry_zone_alert(curr), beep=True)

    if (
        prev is not None
        and not prev.candidate_eligible
        and curr.candidate_eligible
        and not is_ready(curr)
    ):
        _emit(
            WatchAlertKind.ELIGIBLE,
            format_generic_alert(WatchAlertKind.ELIGIBLE, curr),
            beep=False,
        )

    if prev is not None and prev.block_reasons != curr.block_reasons:
        _emit(
            WatchAlertKind.BLOCK_REASONS,
            format_generic_alert(WatchAlertKind.BLOCK_REASONS, curr),
            beep=False,
        )

    if (
        prev is not None
        and prev.setup_state == "ENTRY_ZONE"
        and curr.setup_state == "ENTRY_ZONE"
        and not curr.candidate_eligible
        and curr.block_reasons
        and (prev.candidate_eligible or prev.block_reasons != curr.block_reasons)
    ):
        _emit(
            WatchAlertKind.BLOCKED_AFTER_ENTRY,
            format_generic_alert(WatchAlertKind.BLOCKED_AFTER_ENTRY, curr),
            beep=True,
        )

    if (
        prev is not None
        and prev.setup_state != curr.setup_state
        and curr.setup_state != "ENTRY_ZONE"
        and not any(a.kind == WatchAlertKind.DIRECTIONAL for a in alerts)
    ):
        _emit(
            WatchAlertKind.SETUP_STATE,
            format_generic_alert(WatchAlertKind.SETUP_STATE, curr),
            beep=False,
        )

    prev_w = _weighted(prev)
    curr_w = _weighted(curr)
    if prev_w is not None and curr_w is not None:
        if prev_w < MTF_LONG_THRESHOLD <= curr_w:
            _emit(
                WatchAlertKind.THRESHOLD_CROSS_LONG,
                format_generic_alert(WatchAlertKind.THRESHOLD_CROSS_LONG, curr),
                beep=True,
            )
        if prev_w > MTF_SHORT_THRESHOLD >= curr_w:
            _emit(
                WatchAlertKind.THRESHOLD_CROSS_SHORT,
                format_generic_alert(WatchAlertKind.THRESHOLD_CROSS_SHORT, curr),
                beep=True,
            )

    return alerts


def try_beep() -> bool:
    """Best-effort Windows / terminal bell. Never raises."""
    try:
        import sys

        if sys.platform == "win32":
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                return True
            except Exception:
                pass
        print("\a", end="", flush=True)
        return True
    except Exception:
        return False


def append_alert_log(
    path: Path | str,
    *,
    snap: WatchSnapshot,
    alert: WatchAlert,
) -> None:
    """Append one alert line — no credentials."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ts = snap.timestamp.isoformat()
    score = _weighted(snap)
    reasons = ",".join(snap.block_reasons) if snap.block_reasons else "-"
    line = (
        f"{ts}\tkind={alert.kind.value}\tsymbol={snap.symbol}\t"
        f"signal={snap.final_signal}\tsetup_state={snap.setup_state}\t"
        f"setup_id={snap.setup_id or '-'}\teligible={snap.candidate_eligible}\t"
        f"mtf_score={score}\tblock_reasons={reasons}\n"
    )
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line)


def emit_alerts(
    alerts: list[WatchAlert],
    *,
    snap: WatchSnapshot,
    out: TextIO,
    beep_enabled: bool,
    alert_log: Path | str | None,
) -> None:
    for alert in alerts:
        print("\n".join(["", *alert.lines, ""]), file=out)
        if beep_enabled and alert.beep:
            try_beep()
        if alert_log is not None:
            with suppress(Exception):
                append_alert_log(alert_log, snap=snap, alert=alert)
