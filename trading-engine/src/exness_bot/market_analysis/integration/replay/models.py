"""Offline grounding replay models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReplayFixture:
    fixture_id: str
    description: str
    response: dict[str, Any]
    expected: dict[str, Any] = field(default_factory=dict)
    path: str | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "description": self.description,
            "path": self.path,
        }


@dataclass
class ReplayCaseResult:
    fixture_id: str
    passed: bool
    checks: dict[str, bool]
    errors: list[str] = field(default_factory=list)
    source_count: int = 0
    status_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "passed": self.passed,
            "checks": self.checks,
            "errors": self.errors,
            "source_count": self.source_count,
            "status_hint": self.status_hint,
        }
