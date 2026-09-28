"""Проверка работающего сервера перед демо: python scripts/demo_smoke.py.

Проверяет реальные HTTP endpoint, UTF-8, три ожидаемых примера и fairness.
Не отправляет реальные данные кандидатов.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("QADAM_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
PASSWORD = os.environ.get("QADAM_DEMO_PASSWORD", "")


def request(path: str, payload: dict | None = None) -> dict | list:
    headers = {"Accept": "application/json"}
    if PASSWORD:
        token = base64.b64encode(f"demo:{PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    raw = urllib.request.Request(BASE + path, data=data, headers=headers)
    with urllib.request.urlopen(raw, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    try:
        health = None
        for attempt in range(30):
            try:
                health = request("/health")
                break
            except (urllib.error.URLError, http.client.RemoteDisconnected):
                if attempt == 29:
                    raise
                time.sleep(1)
        assert isinstance(health, dict) and health["model_trained"]
        examples = request("/examples")
        assert isinstance(examples, list) and len(examples) == 3
        queue = request("/demo/candidates")
        assert isinstance(queue, list) and len(queue) == 3
        print(f"OK health: {health['extract_backend']}, model {health['model_version']}")
        print(f"OK synthetic queue: {len(queue)} cases")
        for example in examples:
            result = request("/analyze", {"text": example["text"]})
            assert isinstance(result, dict)
            assert result["level"] == example["expected_level"], (
                f"{example['key']}: expected {example['expected_level']}, got {result['level']}")
            assert result["provenance"]["model_version"] == health["model_version"]
            print(f"OK {example['key']}: {result['level']}, "
                  f"{result['decision_support']['route']}, "
                  f"ATOLA {result['atola_coverage']:.0%}")
        fairness = request("/counterfactual", {"text": examples[0]["text"]})
        assert isinstance(fairness, dict) and "abs_delta" in fairness
        print(f"OK counterfactual: delta={fairness['abs_delta']:.4f}")
        return 0
    except (AssertionError, urllib.error.URLError,
            http.client.RemoteDisconnected, KeyError, ValueError) as error:
        print(f"DEMO CHECK FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
