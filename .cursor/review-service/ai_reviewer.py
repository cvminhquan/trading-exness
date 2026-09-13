from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MODEL = os.getenv("REVIEW_AI_MODEL", "gpt-5.6-sol")
API_URL = os.getenv("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses")
MAX_DIFF_CHARS = int(os.getenv("REVIEW_MAX_DIFF_CHARS", "90000"))

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "FIX_REQUIRED", "BLOCKED"]},
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "fix_task": {"type": ["string", "null"]},
        "next_task": {"type": ["string", "null"]},
    },
    "required": ["verdict", "summary", "findings", "fix_task", "next_task"],
    "additionalProperties": False,
}
SYSTEM = """Bạn là reviewer kỹ thuật fail-closed cho trading-exness.
Chỉ review code; không được tự hợp thức hóa thay đổi ngoài task.
Không cho phép broker mutation mới, LIVE trading, order_send mới, secret/.env changes,
strategy/risk threshold tuning ngoài scope, auto-merge hoặc push master.
PASS chỉ khi diff phù hợp task và không có finding blocking.
FIX_REQUIRED khi có bug/correctness/test/isolation issue có thể sửa trong scope.
BLOCKED khi thiếu evidence quan trọng hoặc có thay đổi nguy hiểm/ngoài scope.
Không gọi confidence là win probability. External/AI không được feed execution.
Trả JSON đúng schema, ngắn gọn và cụ thể."""


def configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _read(path: Path, limit: int = 30000) -> str:
    if not path.exists():
        return "<missing>"
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def build_input(root: Path, event: dict[str, Any], diff: str, changed: list[str]) -> str:
    task = _read(root / ".cursor" / "collab" / "current-task.md", 40000)
    report = _read(root / ".cursor" / "collab" / "cursor-report.md", 30000)
    return "\n\n".join([
        f"EVENT:\n{json.dumps(event, ensure_ascii=False)}",
        "CURRENT TASK:\n" + task,
        "CURSOR REPORT:\n" + report,
        "CHANGED FILES:\n" + "\n".join(changed),
        "GIT DIFF:\n" + diff[:MAX_DIFF_CHARS],
    ])
def _extract_output_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                texts.append(content["text"])
    if not texts:
        raise RuntimeError("OpenAI response missing output_text")
    return "\n".join(texts)


def review(root: Path, event: dict[str, Any], diff: str, changed: list[str]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    body = {
        "model": MODEL,
        "store": False,
        "reasoning": {"effort": os.getenv("REVIEW_AI_REASONING", "high")},
        "instructions": SYSTEM,
        "input": build_input(root, event, diff, changed),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "trading_review_verdict",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    }
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=raw,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI connection failed: {exc}") from exc

    result = json.loads(_extract_output_text(payload))
    verdict = result.get("verdict")
    if verdict not in {"PASS", "FIX_REQUIRED", "BLOCKED"}:
        raise RuntimeError("invalid AI verdict")
    if verdict == "FIX_REQUIRED" and not result.get("fix_task"):
        raise RuntimeError("FIX_REQUIRED requires fix_task")
    return result
