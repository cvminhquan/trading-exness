"""Load sanitized Gemini grounding fixtures (network-free)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from exness_bot.market_analysis.integration.replay.models import ReplayFixture


def default_fixture_root() -> Path:
    # tests/fixtures/gemini_grounding relative to repo trading-engine
    here = Path(__file__).resolve()
    engine_root = here.parents[5]  # .../trading-engine
    candidate = engine_root / "tests" / "fixtures" / "gemini_grounding"
    if candidate.exists():
        return candidate
    # fallback cwd
    cwd = Path.cwd() / "tests" / "fixtures" / "gemini_grounding"
    return cwd


def default_technical_fixture_root() -> Path:
    root = default_fixture_root().parent / "technical_snapshots"
    return root


def load_fixture(path: Path) -> ReplayFixture:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ReplayFixture(
        fixture_id=str(data.get("fixture_id") or path.stem),
        description=str(data.get("description") or ""),
        response=dict(data.get("response") or {}),
        expected=dict(data.get("expected") or {}),
        path=str(path),
    )


def load_all_fixtures(root: Path | None = None) -> list[ReplayFixture]:
    base = root or default_fixture_root()
    files = sorted(base.glob("grounding_*.json"))
    return [load_fixture(p) for p in files]


def load_technical_case(case_file: str) -> dict[str, Any]:
    path = default_technical_fixture_root() / case_file
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"technical fixture must be object: {case_file}")
    return data


def fixture_set_hash(fixtures: list[ReplayFixture]) -> str:
    h = hashlib.sha256()
    for fx in sorted(fixtures, key=lambda f: f.fixture_id):
        raw = Path(fx.path).read_bytes() if fx.path else b""
        h.update(fx.fixture_id.encode("utf-8"))
        h.update(raw)
    return h.hexdigest()[:24]
