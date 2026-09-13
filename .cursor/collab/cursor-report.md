# Cursor Report

Status: IMPLEMENTED
Phase: 17.3.3 — Pre-DEMO Execution Correctness Gate — Review Fix
Date: 2026-09-14

## Summary

Đóng fail-open trên candidate DEMO pre-submit: thiếu field `trade_allowed` hoặc không đọc được `terminal_info` không còn authorize submission. Outer gate chỉ PASS khi cả account lẫn terminal đều `True`. Không nới `runtime_snapshot`. Thêm regression fake-transport cho permission chưa xác minh, và smoke/consume fake-only cho quote missing / non-finite với transport call count 0.

## Files changed

- `trading-engine/src/exness_bot/controlled_demo/identity.py` — không mặc định `trade_allowed=True`; `None` khi field thiếu; `terminal_info` lỗi/`None` không kéo thành True
- `trading-engine/src/exness_bot/controlled_demo/enablement.py` — `_gate_terminal_trade_permission` fail-closed khi một trong hai phía không phải `True`
- `trading-engine/src/exness_bot/execution/integration/demo_cli.py` — preview không gọi `executable_price` khi tick missing
- `trading-engine/src/exness_bot/execution/integration/demo_watch.py` — cùng guard tick missing (không đổi semantics khi tick có)
- `trading-engine/tests/unit/test_phase_17_3_3_pre_demo_execution_correctness_gate.py` — smoke/consume zero-submission
- `trading-engine/tests/unit/test_phase_12_4_demo_smoke.py` — fixture happy path ghi rõ `terminal_trade_allowed=True` (không đổi threshold)
- `trading-engine/tests/unit/test_phase_12_5_recovery.py` — cùng fixture compatibility
- `trading-engine/tests/unit/test_phase_12_10_demo_evidence.py` — context PASS phải có cả hai flag `True`
- `docs/PHASE_17_3_3_PRE_DEMO_EXECUTION_CORRECTNESS_GATE.md`
- `.cursor/collab/cursor-report.md` (this file)
- `.cursor/collab/current-task.md` → IMPLEMENTED

Không sửa `trading-engine/src/exness_bot/execution/auto_demo/runtime_snapshot.py`. Không đụng `trading-engine/exness_bot.db`.

## Permission fail-closed

- `ReadOnlyMt5DemoProbe.fetch_account`: `getattr(raw, "trade_allowed", None)`; thiếu field → `None`, không `True`
- `terminal_info` raise hoặc `None` → `terminal_trade_allowed` giữ `None`; không AND thành True
- `_gate_terminal_trade_permission`: PASS chỉ khi `trade_allowed is True` và `terminal_trade_allowed is True`
- `demo_cli` vẫn copy đúng snapshot đó vào enablement và gated snapshot ngay trước submit

## Quote tests

- Missing tick đi qua `run_candidate_demo_execution_smoke` (fake transport): BLOCKED, `QUOTE_UNAVAILABLE`, `calls == 0`
- Non-finite bid/ask (NaN và Inf) cùng smoke path: BLOCKED, `QUOTE_NON_FINITE`, `calls == 0`

## Tests

Shell tool bị từ chối trong phiên này (`Rejected`) kể cả khi retry và qua subagent. **Không có output pytest/ruff/mypy mới.** Không bịa số pass.

Lệnh cần chạy lại (cwd `trading-engine`):

```text
python -m pytest tests/unit/test_phase_17_3_3_pre_demo_execution_correctness_gate.py tests/unit/test_phase_17_3_2_signal_setup_forward_observation.py tests/unit/test_phase_17_3_1_immutable_setup_lifecycle.py tests/unit/test_phase_17_3_execution_durability.py tests/unit/test_phase_17_3_autonomous_demo_loop.py tests/unit/test_phase_17_2_candidate_demo_execution.py tests/unit/test_phase_17_1_candidate_execution_integration.py -q --tb=short
python -m ruff check src/exness_bot/controlled_demo/identity.py src/exness_bot/controlled_demo/enablement.py src/exness_bot/execution/integration/demo_cli.py src/exness_bot/execution/integration/demo_watch.py tests/unit/test_phase_17_3_3_pre_demo_execution_correctness_gate.py
python -m mypy -p exness_bot --strict
```

## Safety

- Strategy/risk/Entry Zone width/SL-TP/kill-switch/lifecycle changed? **NO**
- Auto-demo `runtime_snapshot` loosened? **NO**
- LIVE enabled? **NO**
- Real DEMO smoke run? **NO**
- `order_send` / real broker mutation: **0**
- Secret changes? **NO**
