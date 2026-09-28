from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from qadam.api.main import app


class PilotWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {
            "QADAM_PILOT_DB": str(root / "pilot.sqlite3"),
            "QADAM_PILOT_MEDIA": str(root / "media"),
            "QADAM_DEMO_PASSWORD": "",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = TestClient(app)

    def create(self, mode: str = "text"):
        return self.client.post("/pilot/submissions", json={
            "language": "en", "mode": mode,
            "story": "I organized four meetings.",
            "scenario_choice": "Hear both sides",
            "rationale": "I would agree on one next step.",
            "consent": True,
        })

    def test_submission_enters_queue_and_review_is_append_only(self) -> None:
        created = self.create()
        self.assertEqual(created.status_code, 201)
        submission_id = created.json()["id"]
        self.assertTrue(submission_id.startswith("QDM-"))
        self.assertNotIn("consent", created.json())

        queue = self.client.get("/pilot/submissions").json()
        self.assertEqual([item["id"] for item in queue], [submission_id])
        review = self.client.post(f"/pilot/submissions/{submission_id}/reviews", json={
            "selected_route": "priority_interview",
            "reason": "The example includes a concrete outcome.",
            "evidence": "organized four meetings",
            "timecode": "",
        })
        self.assertEqual(review.status_code, 201)
        detail = self.client.get(f"/pilot/submissions/{submission_id}").json()
        self.assertEqual(detail["reviews"][0]["selected_route"], "priority_interview")
        self.assertEqual(detail["story"], "I organized four meetings.")

    def test_consent_and_priority_evidence_are_required(self) -> None:
        denied = self.client.post("/pilot/submissions", json={
            "language": "en", "mode": "text", "story": "Example",
            "scenario_choice": "A", "rationale": "Because", "consent": False,
        })
        self.assertEqual(denied.status_code, 422)
        submission_id = self.create().json()["id"]
        invalid = self.client.post(f"/pilot/submissions/{submission_id}/reviews", json={
            "selected_route": "priority_interview",
            "reason": "A sufficiently detailed reason.", "evidence": "short",
        })
        self.assertEqual(invalid.status_code, 422)

    def test_audio_upload_is_private_local_media(self) -> None:
        submission_id = self.create("audio").json()["id"]
        upload = self.client.post(
            f"/pilot/submissions/{submission_id}/media",
            content=b"fake-webm", headers={"content-type": "audio/webm"},
        )
        self.assertEqual(upload.status_code, 204)
        detail = self.client.get(f"/pilot/submissions/{submission_id}").json()
        self.assertTrue(detail["has_media"])
        media = self.client.get(f"/pilot/submissions/{submission_id}/media")
        self.assertEqual(media.content, b"fake-webm")
        self.assertEqual(media.headers["cache-control"], "no-store")
        deleted = self.client.delete(f"/pilot/submissions/{submission_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(f"/pilot/submissions/{submission_id}").status_code, 404)
        self.assertFalse((Path(self.temporary.name) / "media" / f"{submission_id}.bin").exists())


if __name__ == "__main__":
    unittest.main()
