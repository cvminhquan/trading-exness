"""Load persisted baseline backtest JSON artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from exness_bot.backtest.baseline_runner import BaselineResult, baseline_paths


def backtests_directory(project_root: Path | None = None) -> Path:
    root = project_root or Path(__file__).resolve().parents[4]
    return root / "data" / "backtests"


def list_backtest_files(project_root: Path | None = None) -> list[Path]:
    directory = backtests_directory(project_root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def backtest_id_from_path(path: Path) -> str:
    return path.stem


def load_baseline(path: Path) -> BaselineResult:
    """Load a baseline JSON file into BaselineResult."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return BaselineResult.model_validate(raw)


def load_baseline_by_id(report_id: str, project_root: Path | None = None) -> BaselineResult | None:
    directory = backtests_directory(project_root)
    candidate = directory / f"{report_id}.json"
    if not candidate.is_file():
        return None
    return load_baseline(candidate)


def load_all_baselines(project_root: Path | None = None) -> list[tuple[str, BaselineResult]]:
    results: list[tuple[str, BaselineResult]] = []
    for path in list_backtest_files(project_root):
        try:
            results.append((backtest_id_from_path(path), load_baseline(path)))
        except (json.JSONDecodeError, ValueError):
            continue
    return results


def default_baseline_path(project_root: Path | None = None) -> Path:
    return baseline_paths(project_root).json_path
