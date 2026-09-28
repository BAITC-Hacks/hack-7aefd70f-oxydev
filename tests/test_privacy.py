from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qadam.api import main as api
from qadam.core import extract as extraction


class PrivacyTests(unittest.TestCase):
    def test_api_disables_extraction_cache(self) -> None:
        marker = object()
        with (
            patch.object(api, "extract", return_value=marker) as mocked_extract,
            patch.object(api, "model", return_value=object()),
            patch.object(api, "explain", return_value={"ok": True}),
        ):
            result = api._analyze("пример ответа")
            self.assertTrue(result["ok"])
            self.assertIn("provenance", result)
        mocked_extract.assert_called_once_with("пример ответа", use_cache=False)

    def test_no_cache_means_no_disk_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory) / "extract"
            with patch.object(extraction, "CACHE_DIR", cache_dir):
                result = extraction.extract(
                    "Я организовал встречу и распределил роли.",
                    backend="heuristic",
                    use_cache=False,
                )
            self.assertEqual(result.backend, "heuristic")
            self.assertFalse(cache_dir.exists())


if __name__ == "__main__":
    unittest.main()
