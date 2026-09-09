"""Append-only forward signal journal.

Supports PRECOMMITTED (schema only in 16.2.4A.2 — not wired to CandleEngine)
and RETROSPECTIVE_REPLAY (used for initialization/evaluation).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from exness_bot.market_analysis.research.forward.protocol import (
    CLASSIFICATIONS,
    EVALUATION_MODES,
    OUTCOME_STATES,
    ensure_utc,
)
from exness_bot.market_analysis.research.forward.store import (
    DEFAULT_SYMBOL,
    journal_path,
)


@dataclass
class JournalEntry:
    timestamp: str
    symbol: str
    v1_signal: str
    v1_score: float | None
    v2_signal: str
    v2_score: float | None
    m15_score: float | None
    h1_score: float | None
    h4_score: float | None
    d1_score: float | None
    impulse_score: float | None
    structure_transition: str | None
    regime: str | None
    cohort: str
    classification: str  # OBSERVED | FORWARD_UNSEEN
    evaluation_mode: str  # PRECOMMITTED | RETROSPECTIVE_REPLAY
    generated_at: str
    candle_timestamp: str
    freeze_fingerprint_hash: str
    forward_dataset_hash: str | None
    outcome_state: str = "PENDING"  # PENDING | MATURED | INVALID_DATA
    exit_r: float | None = None
    mae_r: float | None = None
    mfe_r: float | None = None
    exit_reason: str | None = None
    whipsaw: bool | None = None
    bars_held: int | None = None
    direction: str | None = None
    source: str | None = None  # v1 | v2
    bars_until_v1_same: int | None = None
    latency_bucket: str | None = None
    clustered: bool = False
    discrepancy: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def identity_key(self) -> str:
        return (
            f"{self.symbol}|{self.candle_timestamp}|{self.source}|"
            f"{self.evaluation_mode}|{self.direction}"
        )


def _validate_entry(entry: JournalEntry) -> None:
    if entry.classification not in CLASSIFICATIONS:
        msg = f"invalid classification: {entry.classification}"
        raise ValueError(msg)
    if entry.evaluation_mode not in EVALUATION_MODES:
        msg = f"invalid evaluation_mode: {entry.evaluation_mode}"
        raise ValueError(msg)
    if entry.outcome_state not in OUTCOME_STATES:
        msg = f"invalid outcome_state: {entry.outcome_state}"
        raise ValueError(msg)


def load_journal(
    symbol: str = DEFAULT_SYMBOL,
    *,
    root: Path | None = None,
) -> list[JournalEntry]:
    path = journal_path(symbol, root=root)
    if not path.exists():
        return []
    entries: list[JournalEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        extras = raw.pop("extras", {}) or {}
        # Tolerate unknown keys in extras
        known = set(JournalEntry.__dataclass_fields__)
        spill = {k: raw.pop(k) for k in list(raw) if k not in known}
        extras.update(spill)
        entries.append(JournalEntry(**raw, extras=extras))
    return entries


def append_journal_entries(
    entries: list[JournalEntry],
    *,
    symbol: str = DEFAULT_SYMBOL,
    root: Path | None = None,
    allow_rewrite: bool = False,
) -> dict[str, Any]:
    """Append-only. Same identity_key → record discrepancy, do not silently rewrite."""
    path = journal_path(symbol, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_journal(symbol, root=root)
    by_key = {e.identity_key: e for e in existing}

    added = 0
    discrepancies = 0
    skipped_identical = 0
    new_lines: list[str] = []

    for entry in entries:
        _validate_entry(entry)
        key = entry.identity_key
        if key in by_key:
            prev = by_key[key]
            if _signal_payload(prev) == _signal_payload(entry):
                skipped_identical += 1
                continue
            if not allow_rewrite:
                # Explicit discrepancy record — do not overwrite prior decision
                disc = JournalEntry(
                    **{
                        **entry.as_dict(),
                        "discrepancy": (
                            f"recompute_differs_from_journal:"
                            f"prev_v1={prev.v1_signal}/{prev.v1_score},"
                            f"prev_v2={prev.v2_signal}/{prev.v2_score}"
                        ),
                        "generated_at": datetime.now(tz=UTC).isoformat(),
                    }
                )
                # Use a distinct identity by tagging discrepancy in source extras
                disc.extras = {**entry.extras, "discrepancy_of": key}
                new_lines.append(json.dumps(disc.as_dict(), default=str))
                discrepancies += 1
                continue
        by_key[key] = entry
        new_lines.append(json.dumps(entry.as_dict(), default=str))
        added += 1

    if new_lines:
        with path.open("a", encoding="utf-8") as fh:
            for line in new_lines:
                fh.write(line + "\n")

    return {
        "path": str(path),
        "added": added,
        "discrepancies": discrepancies,
        "skipped_identical": skipped_identical,
        "total_after": len(existing) + added + discrepancies,
    }


def update_matured_outcomes(
    updates: list[dict[str, Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    root: Path | None = None,
) -> dict[str, Any]:
    """Rewrite journal file only for outcome maturation fields (explicit).

    Signal fields remain immutable; only outcome_* fields may change PENDING→MATURED.
    """
    path = journal_path(symbol, root=root)
    entries = load_journal(symbol, root=root)
    by_key = {e.identity_key: i for i, e in enumerate(entries)}
    matured = 0
    for upd in updates:
        key = upd["identity_key"]
        if key not in by_key:
            continue
        i = by_key[key]
        e = entries[i]
        if e.outcome_state == "MATURED" and e.exit_r is not None:
            # Already matured — do not silently change R
            if upd.get("exit_r") is not None and upd["exit_r"] != e.exit_r:
                e.discrepancy = (
                    f"outcome_recompute_differs: prev={e.exit_r} new={upd['exit_r']}"
                )
            continue
        e.outcome_state = upd.get("outcome_state", "MATURED")
        e.exit_r = upd.get("exit_r")
        e.mae_r = upd.get("mae_r")
        e.mfe_r = upd.get("mfe_r")
        e.exit_reason = upd.get("exit_reason")
        e.whipsaw = upd.get("whipsaw")
        e.bars_held = upd.get("bars_held")
        matured += 1

    # Full rewrite for maturation is allowed and documented (outcome fields only)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e.as_dict(), default=str) + "\n")
    return {"matured_updates": matured, "total": len(entries)}


def _signal_payload(e: JournalEntry) -> tuple[Any, ...]:
    return (
        e.v1_signal,
        e.v1_score,
        e.v2_signal,
        e.v2_score,
        e.classification,
        e.evaluation_mode,
        e.direction,
        e.source,
    )


def count_by_mode(entries: list[JournalEntry]) -> dict[str, int]:
    pre = sum(1 for e in entries if e.evaluation_mode == "PRECOMMITTED")
    retro = sum(1 for e in entries if e.evaluation_mode == "RETROSPECTIVE_REPLAY")
    pending = sum(1 for e in entries if e.outcome_state == "PENDING")
    matured = sum(1 for e in entries if e.outcome_state == "MATURED")
    return {
        "precommitted_signal_count": pre,
        "retrospective_signal_count": retro,
        "pending_outcomes": pending,
        "matured_outcomes": matured,
    }


def make_entry(
    *,
    candle_ts: datetime,
    symbol: str,
    v1_signal: str,
    v1_score: float | None,
    v2_signal: str,
    v2_score: float | None,
    m15_score: float | None,
    h1_score: float | None,
    h4_score: float | None,
    d1_score: float | None,
    impulse_score: float | None,
    structure_transition: str | None,
    regime: str | None,
    cohort: str,
    classification: str,
    evaluation_mode: str,
    freeze_hash: str,
    dataset_hash: str | None,
    direction: str | None,
    source: str | None,
    generated_at: datetime | None = None,
) -> JournalEntry:
    ts = ensure_utc(candle_ts)
    gen = ensure_utc(generated_at) if generated_at else datetime.now(tz=UTC)
    return JournalEntry(
        timestamp=ts.isoformat(),
        symbol=symbol,
        v1_signal=v1_signal,
        v1_score=v1_score,
        v2_signal=v2_signal,
        v2_score=v2_score,
        m15_score=m15_score,
        h1_score=h1_score,
        h4_score=h4_score,
        d1_score=d1_score,
        impulse_score=impulse_score,
        structure_transition=structure_transition,
        regime=regime,
        cohort=cohort,
        classification=classification,
        evaluation_mode=evaluation_mode,
        generated_at=gen.isoformat(),
        candle_timestamp=ts.isoformat(),
        freeze_fingerprint_hash=freeze_hash,
        forward_dataset_hash=dataset_hash,
        direction=direction,
        source=source,
    )
