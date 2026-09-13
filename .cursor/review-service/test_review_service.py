import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("review_service.py")
spec = importlib.util.spec_from_file_location("review_service", MODULE_PATH)
assert spec and spec.loader
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class ReviewServiceTests(unittest.TestCase):
    def test_validate_event_accepts_review_request(self):
        event = {
            "event": "REVIEW_REQUESTED",
            "status": "IMPLEMENTED",
            "taskSha256": "a" * 64,
        }
        self.assertEqual(service.validate_event(event), (True, "ok"))

    def test_validate_event_rejects_bad_sha(self):
        event = {"event": "REVIEW_REQUESTED", "status": "IMPLEMENTED", "taskSha256": "bad"}
        self.assertEqual(service.validate_event(event)[0], False)

    def test_state_round_trip(self):
        original = service.STATE_FILE
        with tempfile.TemporaryDirectory() as tmp:
            service.STATE_FILE = Path(tmp) / "state.json"
            service.save_state({"abc": {"state": "RECEIVED"}})
            self.assertEqual(service.load_state()["abc"]["state"], "RECEIVED")
        service.STATE_FILE = original

    def test_forbidden_patterns_cover_live_mutation(self):
        samples = [
            "client.order_send(request)",
            "LIVE_KILL_SWITCH=false",
            "TRADING_ENV=live",
            "AUTO_DEMO_EXECUTION_ENABLED=true",
        ]
        for sample in samples:
            self.assertTrue(any(pattern.search(sample) for pattern in service.FORBIDDEN_CONTENT))

    def test_forbidden_files_cover_env(self):
        names = [".env", "trading-engine/.env.local", "secrets/key.txt", "credentials/token.json"]
        for name in names:
            self.assertTrue(any(pattern.search(name) for pattern in service.FORBIDDEN_DIFF))


if __name__ == "__main__":
    unittest.main()
