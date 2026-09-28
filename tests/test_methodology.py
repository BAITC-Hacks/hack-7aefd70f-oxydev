from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from qadam.api.main import app


class MethodologyTests(unittest.TestCase):
    def test_provisional_framework_is_complete_and_honest(self) -> None:
        with patch.dict(os.environ, {"QADAM_DEMO_PASSWORD": ""}):
            response = TestClient(app).get("/methodology")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], "qef-0.1.0")
        self.assertEqual(len(payload["competencies"]), 9)
        self.assertIn("Not approved by inVision U", payload["notice"])
        modes = {item["id"]: item["decision_mode"] for item in payload["competencies"]}
        self.assertEqual(modes["values"], "human_only")
        self.assertEqual(modes["wounded_leadership"], "human_only_optional")
        self.assertEqual(modes["leadership"], "experimental_model_plus_human")


if __name__ == "__main__":
    unittest.main()
