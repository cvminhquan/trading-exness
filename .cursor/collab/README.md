# AI Collaboration Workspace

Mục tiêu: Cursor làm implementation agent, review service làm reviewer, ChatGPT giữ vai trò lead/architect; user không cần chuyển tay `sync` / `review`.

## Core files
- `current-task.md`: source of truth; runner chỉ chạy khi exact `Status: READY`.
- `cursor-report.md`: Cursor ghi implementation/tests/risks rồi đổi task thành `IMPLEMENTED`.
- `chatgpt-review.md`: reviewer ghi `PASS | FIX_REQUIRED | BLOCKED`.
- `cursor-task-runner.py`: daemon `READY -> Cursor Agent CLI -> IMPLEMENTED`.
- `repo-watcher.ps1`: giữ nguyên pipeline `IMPLEMENTED -> webhook review`.
- `start-autonomy.ps1`: launcher local cho runner + watcher + review service.
- `install-autonomy-startup.ps1`: cài Scheduled Task chạy khi user logon.

## Autonomous flow
`READY -> Cursor Agent CLI -> IMPLEMENTED -> repo-watcher -> review service -> DONE/BLOCKED/READY fix`.

Nếu reviewer trả `FIX_REQUIRED`, review service rewrite cùng phase về `READY`; runner nhận SHA task mới và tự chạy lại sau cooldown/dedup.

## Safety
- Không trigger `IMPLEMENTED`, `DONE`, `BLOCKED` hay status khác `READY`.
- Runner có OS file lock single-instance, durable state, cooldown và SHA dedup.
- Không tự mở phase mới; đó vẫn là trách nhiệm của lead/reviewer.
- Không lưu API key/secret trong repo. Cursor Agent phải auth qua `cursor-agent login` hoặc `CURSOR_API_KEY` ngoài repo.
- Headless prompt yêu cầu inspect git status/diff, giữ unrelated changes, không chạm `trading-engine/exness_bot.db` nếu task không yêu cầu.
- Không cho phép tự động LIVE/real DEMO/order_send; các task trading vẫn phải tuân thủ current-task boundaries.

## Operations
- One-shot dry-run: `python .cursor/collab/cursor-task-runner.py --once --dry-run`.
- Daemon: `python .cursor/collab/cursor-task-runner.py`.
- Launcher: `powershell -ExecutionPolicy Bypass -File .cursor/collab/start-autonomy.ps1`.
- Startup: `powershell -ExecutionPolicy Bypass -File .cursor/collab/install-autonomy-startup.ps1`.

Runtime state/log nằm trong `.cursor/collab/runner-state/` và được gitignore.
