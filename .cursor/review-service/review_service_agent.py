from __future__ import annotations

import json
import re
import threading
from http.server import ThreadingHTTPServer
from typing import Any

import cursor_reviewer
import review_service as base

TASK_FILE = base.ROOT / ".cursor" / "collab" / "current-task.md"
TERMINAL = {"PASS", "FIX_REQUIRED", "BLOCKED"}


def combined_diff() -> str:
    parts = [
        base.run_git("diff", "--no-ext-diff", "--binary"),
        base.run_git("diff", "--cached", "--no-ext-diff", "--binary"),
    ]
    text = "\n".join(parts)
    return text[:120000]


def render_review(event: dict[str, Any], result: dict[str, Any]) -> None:
    lines = [
        "# CHATGPT REVIEW",
        "",
        f"Status: {result['verdict']}",
        f"Phase: {event.get('phase', 'UNKNOWN')}",
        f"Task SHA256: {event.get('taskSha256', 'UNKNOWN')}",
        f"Updated: {base.utc_now()}",
        "",
        "## Summary",
        result.get("summary", ""),
        "",
        "## Findings",
    ]
    findings = result.get("findings") or ["KhÃ´ng cÃ³ finding blocking."]
    lines.extend(f"- {item}" for item in findings)
    base.REVIEW_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def _replace_status(text: str, status: str) -> str:
    if re.search(r"(?m)^Status:\s*.+$", text):
        return re.sub(r"(?m)^Status:\s*.+$", f"Status: {status}", text, count=1)
    return f"Status: {status}\n" + text


def apply_task_transition(result: dict[str, Any]) -> None:
    if not TASK_FILE.exists():
        return
    current = TASK_FILE.read_text(encoding="utf-8", errors="replace")
    verdict = result["verdict"]
    if verdict == "PASS":
        TASK_FILE.write_text(_replace_status(current, "DONE"), encoding="utf-8")
        return
    if verdict != "FIX_REQUIRED":
        return
    fix_task = str(result.get("fix_task") or "").strip()
    if not fix_task:
        raise RuntimeError("FIX_REQUIRED without fix_task")
    unsafe_patterns = [r"order_send\s*\(", r"TRADING_ENV\s*=\s*live", r"LIVE_KILL_SWITCH\s*=\s*false", r"AUTO_DEMO_EXECUTION_ENABLED\s*=\s*true"]
    if any(re.search(pattern, fix_task, re.I) for pattern in unsafe_patterns):
        raise RuntimeError("unsafe fix_task rejected")
    phase_match = re.search(r"(?m)^Phase:\s*(.+)$", current)
    phase = phase_match.group(1).strip() if phase_match else "CURRENT"
    rewritten = (
        "# CURRENT TASK\n\n"
        "Status: READY\nOwner: Cursor\nReviewer/Lead: Cursor Review Service\n"
        f"Phase: {phase} â€” Review Fix\n\n"
        "## Má»¥c tiÃªu fix\n" + fix_task + "\n\n"
        "## Boundaries\n"
        "- Chá»‰ sá»­a finding cá»§a review hiá»‡n táº¡i.\n"
        "- KhÃ´ng Ä‘á»•i strategy/risk thresholds ngoÃ i finding.\n"
        "- KhÃ´ng thÃªm broker mutation, LIVE trading, order_send hoáº·c secret changes.\n"
        "- Cháº¡y targeted regressions vÃ  ghi cursor-report.md.\n"
        "- Khi xong Ä‘á»•i Status: IMPLEMENTED rá»“i Dá»ªNG.\n"
    )
    TASK_FILE.write_text(rewritten, encoding="utf-8")

def process_event(event: dict[str, Any]) -> None:
    key = event["taskSha256"].lower()
    with base.LOCK:
        state = base.load_state()
        record = state.get(key, {})
        if record.get("state") in TERMINAL:
            base.log(f"duplicate_terminal sha256={key} state={record['state']}")
            return
        state[key] = {"state": "REVIEWING", "updatedAt": base.utc_now(), "phase": event.get("phase")}
        base.save_state(state)
    try:
        violations = base.safety_scan()
        if violations:
            result = {
                "verdict": "BLOCKED",
                "summary": "Safety guardrail cháº·n automated review.",
                "findings": violations,
                "fix_task": None,
                "next_task": None,
            }
        elif not cursor_reviewer.configured():
            result = {
                "verdict": "BLOCKED",
                "summary": "Cursor Agent CLI chÆ°a Ä‘Æ°á»£c cáº¥u hÃ¬nh cho AI reviewer.",
                "findings": ["Safety pre-scan passed; AI review chÆ°a cháº¡y."],
                "fix_task": None,
                "next_task": None,
            }
        else:
            changed = base.changed_files()
            result = cursor_reviewer.review(base.ROOT, event, combined_diff(), changed)
        render_review(event, result)
        apply_task_transition(result)
        final_state = result["verdict"]
        with base.LOCK:
            state = base.load_state()
            state[key] = {
                "state": final_state,
                "updatedAt": base.utc_now(),
                "phase": event.get("phase"),
                "model": "cursor-agent" if cursor_reviewer.configured() else None,
                "findings": result.get("findings", []),
            }
            base.save_state(state)
        base.log(f"agent_event_processed sha256={key} state={final_state}")
    except Exception as exc:
        with base.LOCK:
            state = base.load_state()
            state[key] = {"state": "ERROR", "updatedAt": base.utc_now(), "error": str(exc)}
            base.save_state(state)
        base.log(f"agent_event_error sha256={key} error={exc}")


class AgentHandler(base.Handler):
    server_version = "TradingReviewAgent/0.2"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {
                "ok": True,
                "service": "review-agent",
                "aiConfigured": cursor_reviewer.configured(),
                "model": "cursor-agent",
            })
            return
        super().do_GET()


def main() -> None:
    base.process_event = process_event
    base.BASE.mkdir(parents=True, exist_ok=True)
    base.log(f"agent_service_started host={base.HOST} port={base.PORT} model=cursor-agent")
    server = ThreadingHTTPServer((base.HOST, base.PORT), AgentHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        base.log("agent_service_stopped")


if __name__ == "__main__":
    main()



