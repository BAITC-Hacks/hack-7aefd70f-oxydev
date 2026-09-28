from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from qadam.api.main import app


class DemoWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.environment = patch.dict(os.environ, {
            "QADAM_DEMO_DB": str(Path(self.temporary.name) / "reviews.sqlite3"),
            "QADAM_DEMO_PASSWORD": "",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = TestClient(app)
        self.example_id = self.client.get("/examples").json()[0]["id"]

    def test_confirm_and_override_are_append_only(self) -> None:
        with patch("qadam.api.main._analyze", return_value={
            "decision_support": {"route": "priority_interview"},
        }):
            confirm = self.client.post("/demo/reviews", json={
                "example_id": self.example_id,
                "selected_route": "priority_interview",
                "reason": "",
            })
            invalid_override = self.client.post("/demo/reviews", json={
                "example_id": self.example_id,
                "selected_route": "manual_review",
                "reason": "short",
            })
            override = self.client.post("/demo/reviews", json={
                "example_id": self.example_id,
                "selected_route": "manual_review",
                "reason": "Нужно уточнить личный вклад кандидата",
            })
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.json()["action"], "confirm")
        self.assertEqual(invalid_override.status_code, 422)
        self.assertEqual(override.status_code, 200)
        self.assertEqual(override.json()["action"], "override")
        history = self.client.get(
            f"/demo/candidates/{self.example_id}/reviews").json()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["action"], "override")
        self.assertNotIn("text", history[0])
        queue = self.client.get("/demo/candidates").json()
        self.assertEqual(len(queue), 3)
        self.assertEqual(queue[0]["latest_review"]["action"], "override")

    def test_unlisted_candidate_cannot_enter_demo_journal(self) -> None:
        response = self.client.post("/demo/reviews", json={
            "example_id": "real-person-id",
            "selected_route": "priority_interview",
            "reason": "",
        })
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
