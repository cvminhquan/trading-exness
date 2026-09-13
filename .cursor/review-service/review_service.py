from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.getenv("REVIEW_SERVICE_HOST", "127.0.0.1")
PORT = int(os.getenv("REVIEW_SERVICE_PORT", "8765"))
ROOT = Path(os.getenv("REVIEW_REPO", r"C:\Users\Quan\OneDrive\Desktop\trading-exness")).resolve()
BASE = ROOT / ".cursor" / "review-service"
STATE_FILE = BASE / "state" / "events.json"
LOG_FILE = BASE / "logs" / "service.log"
REVIEW_FILE = ROOT / ".cursor" / "collab" / "chatgpt-review.md"
SECRET = os.getenv("REVIEW_WEBHOOK_SECRET", "")
LOCK = threading.Lock()

ALLOWED_EVENTS = {"REVIEW_REQUESTED"}
ALLOWED_STATES = {"RECEIVED", "REVIEWING", "BLOCKED", "PASS", "FIX_REQUIRED", "ERROR"}
FORBIDDEN_DIFF = [
    re.compile(r"(^|/)\.env($|\.)", re.I),
    re.compile(r"(^|/)secrets?(/|$)", re.I),
    re.compile(r"(^|/)credentials?(/|$)", re.I),
]
FORBIDDEN_CONTENT = [
    re.compile(r"order_send\s*\(", re.I),
    re.compile(r"LIVE_KILL_SWITCH\s*=\s*false", re.I),
    re.compile(r"TRADING_ENV\s*=\s*live", re.I),
    re.compile(r"AUTO_DEMO_EXECUTION_ENABLED\s*=\s*true", re.I),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_now()}] {message}\n")


def load_state() -> dict[str, dict]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, dict]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(STATE_FILE)
def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def changed_files() -> list[str]:
    names: set[str] = set()
    for args in (("diff", "--name-only"), ("diff", "--cached", "--name-only")):
        names.update(line.strip() for line in run_git(*args).splitlines() if line.strip())
    status = run_git("status", "--porcelain")
    for line in status.splitlines():
        if len(line) > 3:
            names.add(line[3:].split(" -> ")[-1].strip())
    return sorted(names)


def safety_scan() -> list[str]:
    violations: list[str] = []
    files = changed_files()
    for name in files:
        normalized = name.replace("\\", "/")
        if any(pattern.search(normalized) for pattern in FORBIDDEN_DIFF):
            violations.append(f"forbidden_file:{normalized}")
    production = [name for name in files if not name.startswith((".cursor/", "docs/", "trading-engine/tests/"))]
    for name in production:
        diff = run_git("diff", "--no-ext-diff", "--unified=0", "--", name) + run_git(
            "diff", "--cached", "--no-ext-diff", "--unified=0", "--", name
        )
        added = "\n".join(
            line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
        )
        for pattern in FORBIDDEN_CONTENT:
            if pattern.search(added):
                violations.append(f"forbidden_added_content:{name}:{pattern.pattern}")
    return violations
def write_review(event: dict, status: str, details: list[str]) -> None:
    phase = event.get("phase", "UNKNOWN")
    sha = event.get("taskSha256", "UNKNOWN")
    body = [
        "# CHATGPT REVIEW",
        "",
        f"Status: {status}",
        f"Phase: {phase}",
        f"Task SHA256: {sha}",
        f"Updated: {utc_now()}",
        "",
        "## Automated pre-review",
    ]
    body.extend(f"- {item}" for item in details)
    REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_FILE.write_text("\n".join(body) + "\n", encoding="utf-8")


def validate_event(event: object) -> tuple[bool, str]:
    if not isinstance(event, dict):
        return False, "payload_not_object"
    if event.get("event") not in ALLOWED_EVENTS:
        return False, "unsupported_event"
    sha = event.get("taskSha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", sha):
        return False, "invalid_task_sha256"
    if event.get("status") != "IMPLEMENTED":
        return False, "invalid_status"
    return True, "ok"


def process_event(event: dict) -> None:
    key = event["taskSha256"].lower()
    with LOCK:
        state = load_state()
        record = state.get(key, {})
        if record.get("state") in {"PASS", "FIX_REQUIRED", "BLOCKED"}:
            log(f"duplicate_terminal sha256={key} state={record['state']}")
            return
        state[key] = {"state": "REVIEWING", "updatedAt": utc_now(), "phase": event.get("phase")}
        save_state(state)
    try:
        violations = safety_scan()
        if violations:
            final_state = "BLOCKED"
            details = ["Safety guardrail blocked automated review.", *violations]
        else:
            final_state = "BLOCKED"
            details = [
                "Safety pre-scan passed.",
                "AI reviewer chÆ°a Ä‘Æ°á»£c cáº¥u hÃ¬nh; khÃ´ng tá»± suy diá»…n PASS/FIX_REQUIRED.",
                "KhÃ´ng cÃ³ broker mutation, merge hoáº·c push master tá»« review service.",
            ]
        write_review(event, final_state, details)
        with LOCK:
            state = load_state()
            state[key] = {
                "state": final_state,
                "updatedAt": utc_now(),
                "phase": event.get("phase"),
                "violations": violations,
            }
            save_state(state)
        log(f"event_processed sha256={key} state={final_state}")
    except Exception as exc:
        with LOCK:
            state = load_state()
            state[key] = {"state": "ERROR", "updatedAt": utc_now(), "error": str(exc)}
            save_state(state)
        log(f"event_error sha256={key} error={exc}")


class Handler(BaseHTTPRequestHandler):
    server_version = "TradingReviewService/0.1"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "review", "aiConfigured": False})
            return
        if self.path == "/state":
            self._json(200, {"events": load_state()})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhook/review":
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 65536:
            self._json(400, {"error": "invalid_content_length"})
            return
        raw = self.rfile.read(length)
        if SECRET:
            supplied = self.headers.get("X-Review-Signature", "")
            expected = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(supplied, expected):
                self._json(401, {"error": "invalid_signature"})
                return
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "invalid_json"})
            return
        valid, reason = validate_event(event)
        if not valid:
            self._json(400, {"error": reason})
            return
        key = event["taskSha256"].lower()
        with LOCK:
            state = load_state()
            existing = state.get(key)
            if existing and existing.get("state") in ALLOWED_STATES:
                self._json(200, {"accepted": False, "duplicate": True, "state": existing["state"]})
                return
            state[key] = {"state": "RECEIVED", "updatedAt": utc_now(), "phase": event.get("phase")}
            save_state(state)
        threading.Thread(target=process_event, args=(event,), daemon=True).start()
        self._json(202, {"accepted": True, "taskSha256": key})

    def log_message(self, fmt: str, *args: object) -> None:
        log("http " + (fmt % args))


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    log(f"service_started host={HOST} port={PORT} repo={ROOT}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log("service_stopped")


if __name__ == "__main__":
    main()

