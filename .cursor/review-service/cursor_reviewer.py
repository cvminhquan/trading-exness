from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

MAX_DIFF_CHARS = int(os.getenv("REVIEW_MAX_DIFF_CHARS", "90000"))
VERDICTS = {"PASS", "FIX_REQUIRED", "BLOCKED"}


def _find_agent_cli() -> Path:
    override = os.getenv("CURSOR_AGENT_CLI")
    if override:
        path = Path(override)
        if path.exists():
            return path
    appdata = Path(os.getenv("APPDATA", ""))
    base = appdata / "Cursor/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local/share/cursor-agent/versions"
    matches = sorted(base.glob("*/cursor-agent.cmd")) if base.exists() else []
    if not matches:
        raise RuntimeError("Cursor Agent CLI not found")
    return matches[-1]


def configured() -> bool:
    try:
        agent = _find_agent_cli()
        result = subprocess.run([str(agent), "status"], capture_output=True, text=True, timeout=15, check=False)
        output = f"{result.stdout}\n{result.stderr}".lower()
        return result.returncode == 0 and "not logged in" not in output
    except Exception:
        return False


def _read(path: Path, limit: int) -> str:
    if not path.exists():
        return "<missing>"
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def build_prompt(root: Path, event: dict[str, Any], diff: str, changed: list[str]) -> str:
    task = _read(root / ".cursor/collab/current-task.md", 40000)
    report = _read(root / ".cursor/collab/cursor-report.md", 30000)
    payload = "\n\n".join([
        f"EVENT:\n{json.dumps(event, ensure_ascii=False)}",
        "CURRENT TASK:\n" + task,
        "CURSOR REPORT:\n" + report,
        "CHANGED FILES:\n" + "\n".join(changed),
        "GIT DIFF:\n" + diff[:MAX_DIFF_CHARS],
    ])
    return f"""You are the fail-closed technical reviewer for trading-exness.
Review only; do not edit files, run broker mutations, enable LIVE, call order_send, change secrets, push, merge, or open a new phase.
PASS only if the implementation matches the task and has no blocking correctness/safety/test issue.
FIX_REQUIRED for an in-scope fixable issue. BLOCKED if evidence is insufficient or changes are unsafe/out of scope.
External/AI analysis must never feed execution. Do not describe confidence as win probability.
Return ONLY one JSON object, no markdown fences. Use ASCII-only English in all JSON string values. Use exactly these keys:
verdict: PASS|FIX_REQUIRED|BLOCKED
summary: string
findings: array of strings
fix_task: string or null
next_task: null
For FIX_REQUIRED, fix_task must be concrete and scoped. next_task must always be null.

{payload}"""


def _parse_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Cursor reviewer returned no JSON object")
        return json.loads(stripped[start:end + 1])


def review(root: Path, event: dict[str, Any], diff: str, changed: list[str]) -> dict[str, Any]:
    agent = _find_agent_cli()
    if not configured():
        raise RuntimeError("Cursor Agent CLI is not authenticated")
    command = [
        str(agent), "-p", "--trust", "--workspace", str(root),
        "--output-format", "text",
    ]
    result = subprocess.run(
        command, input=build_prompt(root, event, diff, changed), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=900, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:3000]
        raise RuntimeError(f"Cursor reviewer failed rc={result.returncode}: {detail}")
    verdict = _parse_json(result.stdout)
    if verdict.get("verdict") not in VERDICTS:
        raise RuntimeError("invalid Cursor reviewer verdict")
    if not isinstance(verdict.get("summary"), str) or not isinstance(verdict.get("findings"), list):
        raise RuntimeError("invalid Cursor reviewer payload")
    if verdict["verdict"] == "FIX_REQUIRED" and not verdict.get("fix_task"):
        raise RuntimeError("FIX_REQUIRED requires fix_task")
    if verdict.get("next_task") is not None:
        raise RuntimeError("reviewer must not open next task")
    return verdict



