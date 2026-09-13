import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).parent

spec = importlib.util.spec_from_file_location("ai_reviewer", BASE / "ai_reviewer.py")
assert spec and spec.loader
ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)


class AiReviewerTests(unittest.TestCase):
    def test_not_configured_without_key(self):
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            self.assertFalse(ai.configured())
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old

    def test_schema_has_fail_closed_verdicts(self):
        enum = ai.SCHEMA["properties"]["verdict"]["enum"]
        self.assertEqual(enum, ["PASS", "FIX_REQUIRED", "BLOCKED"])

    def test_build_input_includes_task_report_and_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collab = root / ".cursor" / "collab"
            collab.mkdir(parents=True)
            (collab / "current-task.md").write_text("TASK", encoding="utf-8")
            (collab / "cursor-report.md").write_text("REPORT", encoding="utf-8")
            text = ai.build_input(root, {"phase": "X"}, "DIFF", ["a.py"])
            self.assertIn("TASK", text)
            self.assertIn("REPORT", text)
            self.assertIn("DIFF", text)
            self.assertIn("a.py", text)


if __name__ == "__main__":
    unittest.main()
