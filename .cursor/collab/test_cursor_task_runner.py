from __future__ import annotations

import importlib.util
from pathlib import Path
import time
import unittest

MODULE_PATH = Path(__file__).with_name("cursor-task-runner.py")
spec = importlib.util.spec_from_file_location("cursor_task_runner", MODULE_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class CursorTaskRunnerTests(unittest.TestCase):
    def test_exact_ready_is_triggerable(self) -> None:
        status, phase = runner.parse_task("# CURRENT TASK\nStatus: READY\nPhase: X\n")
        self.assertEqual(status, "READY")
        self.assertEqual(phase, "X")

    def test_non_ready_statuses_do_not_equal_ready(self) -> None:
        for status in ["IMPLEMENTED", "DONE", "BLOCKED", "FIX_REQUIRED"]:
            parsed, _ = runner.parse_task(f"Status: {status}\nPhase: X\n")
            self.assertNotEqual(parsed, "READY")

    def test_success_sha_is_deduplicated(self) -> None:
        ok, reason = runner.should_trigger({"last_success_sha": "abc"}, "abc", 60)
        self.assertFalse(ok)
        self.assertEqual(reason, "dedup_success")
    def test_recent_attempt_is_cooled_down(self) -> None:
        state = {"last_attempt_sha": "abc", "last_attempt_epoch": time.time()}
        ok, reason = runner.should_trigger(state, "abc", 60)
        self.assertFalse(ok)
        self.assertEqual(reason, "cooldown")

    def test_changed_ready_task_can_trigger(self) -> None:
        state = {"last_success_sha": "old", "last_attempt_sha": "old", "last_attempt_epoch": time.time()}
        ok, reason = runner.should_trigger(state, "new", 60)
        self.assertTrue(ok)
        self.assertEqual(reason, "ready")

    def test_prompt_contains_safety_and_stop_contract(self) -> None:
        prompt = runner.build_prompt()
        self.assertIn("git status", prompt)
        self.assertIn("git diff", prompt)
        self.assertIn("IMPLEMENTED", prompt)
        self.assertIn("phase", prompt)
        self.assertIn("order_send", prompt)


if __name__ == "__main__":
    unittest.main()
