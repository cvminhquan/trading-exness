import importlib.util
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).parent

spec = importlib.util.spec_from_file_location("review_service_agent", BASE / "review_service_agent.py")
assert spec and spec.loader
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class AgentTransitionTests(unittest.TestCase):
    def test_pass_marks_task_done(self):
        original = agent.TASK_FILE
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / "task.md"
            task.write_text("# CURRENT TASK\n\nStatus: IMPLEMENTED\nPhase: X\n", encoding="utf-8")
            agent.TASK_FILE = task
            agent.apply_task_transition({"verdict": "PASS"})
            self.assertIn("Status: DONE", task.read_text(encoding="utf-8"))
        agent.TASK_FILE = original

    def test_fix_required_creates_scoped_ready_task(self):
        original = agent.TASK_FILE
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / "task.md"
            task.write_text("# CURRENT TASK\n\nStatus: IMPLEMENTED\nPhase: 17.3.2\n", encoding="utf-8")
            agent.TASK_FILE = task
            agent.apply_task_transition({"verdict": "FIX_REQUIRED", "fix_task": "Fix idempotency bug."})
            text = task.read_text(encoding="utf-8")
            self.assertIn("Status: READY", text)
            self.assertIn("Fix idempotency bug.", text)
            self.assertIn("broker mutation", text)
            self.assertRaises(RuntimeError, agent.apply_task_transition, {"verdict": "FIX_REQUIRED", "fix_task": "Call order_send() now."})
        agent.TASK_FILE = original


if __name__ == "__main__":
    unittest.main()

