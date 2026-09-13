from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPO = Path(__file__).resolve().parents[2]
COLLAB = REPO / ".cursor" / "collab"
TASK = COLLAB / "current-task.md"
RULE = REPO / ".cursor" / "rules" / "agent-collaboration.mdc"
STATE_DIR = COLLAB / "runner-state"
STATE_FILE = STATE_DIR / "state.json"
LOCK_FILE = STATE_DIR / "runner.lock"
LOG_FILE = STATE_DIR / "runner.log"
DEFAULT_INTERVAL = 10
DEFAULT_COOLDOWN = 60

STATUS_RE = re.compile(r"(?m)^Status:\s*([^\r\n]+)\s*$")
PHASE_RE = re.compile(r"(?m)^Phase:\s*([^\r\n]+)\s*$")
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{utc_now()}] {message}\n"
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line)


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"state_load_error error={exc}")
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
@contextlib.contextmanager
def single_instance_lock() -> Iterator[None]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("a+b")
    try:
        handle.seek(0)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("runner already active") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("runner already active") from exc
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        handle.close()
def find_agent_cli() -> Path | None:
    env_path = os.environ.get("CURSOR_AGENT_CLI")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    base = Path(os.environ.get("APPDATA", "")) / "Cursor" / "User" / "globalStorage" / "anysphere.cursor-agent-worker" / "agent-cli" / ".local" / "share" / "cursor-agent" / "versions"
    if not base.exists():
        return None
    candidates = sorted(base.glob("*/cursor-agent.cmd"), key=lambda p: p.parent.name, reverse=True)
    return candidates[0] if candidates else None


def run_cmd(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def auth_status(agent: Path) -> tuple[bool, str]:
    try:
        cp = run_cmd([str(agent), "status"], timeout=20)
    except Exception as exc:
        return False, f"status_error:{exc}"
    output = ((cp.stdout or "") + "\n" + (cp.stderr or "")).strip()
    logged_in = cp.returncode == 0 and "not logged in" not in output.lower()
    return logged_in, output[:500]
def parse_task(text: str) -> tuple[str, str]:
    status_match = STATUS_RE.search(text)
    phase_match = PHASE_RE.search(text)
    status = status_match.group(1).strip() if status_match else "UNKNOWN"
    phase = phase_match.group(1).strip() if phase_match else "UNKNOWN"
    return status, phase


def build_prompt() -> str:
    return (
        "Bạn là Cursor implementation agent cho repo trading-exness. "
        "Đọc .cursor/collab/current-task.md và .cursor/rules/agent-collaboration.mdc trước khi làm. "
        "Chỉ thực hiện nếu exact Status: READY. Trước mọi edit, inspect git status và git diff; "
        "không reset/revert unrelated changes và không đụng trading-engine/exness_bot.db nếu task không yêu cầu. "
        "Thực hiện đúng scope/safety boundaries, không mở rộng phase. Chạy test/lint/typecheck theo task. "
        "Ghi kết quả đầy đủ vào .cursor/collab/cursor-report.md. Khi hoàn tất, đổi duy nhất Status: READY "
        "thành Status: IMPLEMENTED trong current-task.md rồi STOP. Tuyệt đối không tự mở phase tiếp theo. "
        "Không order_send, không LIVE, không real DEMO broker mutation, không secret changes trừ khi task explicitly cho phép."
    )


def task_ready() -> tuple[bool, str, str, str]:
    if not TASK.exists():
        return False, "MISSING", "UNKNOWN", ""
    text = TASK.read_text(encoding="utf-8", errors="replace")
    status, phase = parse_task(text)
    return status == "READY", status, phase, sha256_text(text)
def should_trigger(state: dict[str, Any], task_sha: str, cooldown: int) -> tuple[bool, str]:
    last_success = state.get("last_success_sha")
    if last_success == task_sha:
        return False, "dedup_success"
    last_attempt = state.get("last_attempt_sha")
    last_attempt_epoch = float(state.get("last_attempt_epoch", 0) or 0)
    if last_attempt == task_sha and time.time() - last_attempt_epoch < cooldown:
        return False, "cooldown"
    return True, "ready"


def run_agent(agent: Path, phase: str, task_sha: str, dry_run: bool) -> int:
    state = load_state()
    state.update({
        "last_attempt_sha": task_sha,
        "last_attempt_epoch": time.time(),
        "last_attempt_at": utc_now(),
        "phase": phase,
        "runner_state": "DRY_RUN" if dry_run else "RUNNING_AGENT",
    })
    save_state(state)
    if dry_run:
        log(f"dry_run_trigger phase={phase} sha={task_sha}")
        return 0
    logged_in, auth_text = auth_status(agent)
    if not logged_in:
        state = load_state()
        state.update({"runner_state": "BLOCKED_AUTH", "last_error": "Cursor Agent CLI not authenticated"})
        save_state(state)
        log(f"agent_blocked_auth phase={phase} sha={task_sha} status={auth_text!r}")
        return 11
    cmd = [
        str(agent), "-p", "--trust", "--workspace", str(REPO),
        "--output-format", "text", build_prompt(),
    ]
    log(f"agent_start phase={phase} sha={task_sha} cli={agent}")
    cp = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=60 * 60)
    output_tail = ((cp.stdout or "") + "\n" + (cp.stderr or ""))[-4000:]
    ready, status, _, current_sha = task_ready()
    state = load_state()
    state.update({
        "last_exit_code": cp.returncode,
        "last_finished_at": utc_now(),
        "last_output_tail": output_tail,
        "post_status": status,
        "post_task_sha": current_sha,
    })
    if cp.returncode == 0 and status == "IMPLEMENTED":
        state.update({"last_success_sha": task_sha, "runner_state": "WAITING_REVIEW", "last_error": None})
        log(f"agent_success phase={phase} sha={task_sha}")
    elif cp.returncode == 0 and ready:
        state.update({"runner_state": "ERROR", "last_error": "agent exited 0 but task remained READY"})
        log(f"agent_incomplete phase={phase} sha={task_sha}")
    else:
        state.update({"runner_state": "ERROR", "last_error": f"agent exit={cp.returncode} post_status={status}"})
        log(f"agent_error phase={phase} sha={task_sha} exit={cp.returncode} post_status={status}")
    save_state(state)
    return cp.returncode


def tick(*, dry_run: bool, cooldown: int) -> int:
    ready, status, phase, task_sha = task_ready()
    state = load_state()
    if not ready:
        if state.get("runner_state") != f"IDLE_{status}":
            state.update({"runner_state": f"IDLE_{status}", "observed_status": status, "observed_at": utc_now()})
            save_state(state)
        return 0
    trigger, reason = should_trigger(state, task_sha, cooldown)
    if not trigger:
        return 0
    agent = find_agent_cli()
    if agent is None:
        state.update({"runner_state": "BLOCKED_CLI", "last_error": "cursor-agent CLI not found"})
        save_state(state)
        log(f"blocked_cli phase={phase} sha={task_sha}")
        return 12
    return run_agent(agent, phase, task_sha, dry_run)
def main() -> int:
    parser = argparse.ArgumentParser(description="Watch current-task.md and run Cursor Agent for READY tasks")
    parser.add_argument("--once", action="store_true", help="Evaluate one tick then exit")
    parser.add_argument("--dry-run", action="store_true", help="Detect trigger without launching Cursor Agent")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--cooldown", type=int, default=DEFAULT_COOLDOWN)
    args = parser.parse_args()
    try:
        with single_instance_lock():
            log(f"runner_started once={args.once} dry_run={args.dry_run} interval={args.interval} cooldown={args.cooldown}")
            while True:
                try:
                    tick(dry_run=args.dry_run, cooldown=max(0, args.cooldown))
                except subprocess.TimeoutExpired:
                    state = load_state()
                    state.update({"runner_state": "ERROR", "last_error": "Cursor Agent timed out", "updated_at": utc_now()})
                    save_state(state)
                    log("agent_timeout")
                except Exception as exc:
                    state = load_state()
                    state.update({"runner_state": "ERROR", "last_error": str(exc), "updated_at": utc_now()})
                    save_state(state)
                    log(f"runner_tick_error error={exc}")
                if args.once:
                    break
                time.sleep(max(2, args.interval))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        log("runner_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
