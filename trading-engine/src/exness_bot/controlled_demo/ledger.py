"""Durable one-shot submission ledger for controlled DEMO smoke."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SmokeLedgerState:
    submission_count: int
    last_intent_id: str | None
    last_ack_status: str | None
    updated_at: str | None


class DemoSmokeLedger:
    """Persists that a controlled smoke already submitted — blocks a second order."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> SmokeLedgerState:
        if not self._path.is_file():
            return SmokeLedgerState(0, None, None, None)
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return SmokeLedgerState(
            submission_count=int(raw.get("submission_count", 0)),
            last_intent_id=raw.get("last_intent_id"),
            last_ack_status=raw.get("last_ack_status"),
            updated_at=raw.get("updated_at"),
        )

    def record_submission(self, *, intent_id: str, ack_status: str) -> None:
        state = self.load()
        payload = {
            "submission_count": state.submission_count + 1,
            "last_intent_id": intent_id,
            "last_ack_status": ack_status,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)
