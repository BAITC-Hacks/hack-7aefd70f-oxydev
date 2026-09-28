from __future__ import annotations

import base64
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from qadam.api.main import app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_and_examples(self) -> None:
        with patch.dict(os.environ, {"QADAM_DEMO_PASSWORD": ""}):
            health = self.client.get("/health")
            examples = self.client.get("/examples")
        self.assertEqual(health.status_code, 200)
        self.assertIn("model_trained", health.json())
        self.assertEqual(examples.status_code, 200)
        self.assertGreaterEqual(len(examples.json()), 3)

    def test_analyze_contract_and_empty_input(self) -> None:
        with patch.dict(os.environ, {"QADAM_DEMO_PASSWORD": ""}):
            empty = self.client.post("/analyze", json={"text": "  "})
            with patch("qadam.api.main._analyze", return_value={"level": "strong"}):
                valid = self.client.post("/analyze", json={"text": " пример "})
        self.assertEqual(empty.status_code, 422)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["level"], "strong")
        self.assertEqual(valid.headers["cache-control"], "no-store")

    def test_demo_password_protects_ui_and_api(self) -> None:
        with patch.dict(os.environ, {"QADAM_DEMO_PASSWORD": "a-long-test-password"}):
            self.assertEqual(self.client.get("/examples").status_code, 401)
            self.assertEqual(self.client.get("/").status_code, 401)
            self.assertEqual(self.client.get("/health").status_code, 200)
            token = base64.b64encode(b"demo:a-long-test-password").decode("ascii")
            response = self.client.get(
                "/examples", headers={"Authorization": f"Basic {token}"})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
