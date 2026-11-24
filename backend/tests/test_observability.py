from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
for import_path in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.services.observability import ObservabilityStore, RingBuffer
from app.api.observability import _ingest_secret_is_configured, ingest
from app.schemas.observability import ObservabilityIngest
from app.schemas.user import LoginRequest


class ObservabilityTests(unittest.TestCase):
    def test_ring_buffer_keeps_only_latest_entries(self) -> None:
        buffer = RingBuffer(max_items=2)
        for item in (1, 2, 3):
            buffer.append(item)
        self.assertEqual(buffer.snapshot(), [2, 3])

    def test_slow_query_counter_uses_configured_threshold(self) -> None:
        store = ObservabilityStore()
        with patch("app.services.observability.settings.slow_query_ms", 50):
            store.record_db_latency(49)
            store.record_db_latency(50)
        self.assertEqual(store.snapshot()["db_latency"]["slow_query_count"], 1)

    def test_collector_falls_back_when_bcc_is_not_available(self) -> None:
        with patch("app.services.observability.platform.system", return_value="Windows"), patch(
            "app.services.observability.settings.ebpf_collector_enabled", True
        ):
            store = ObservabilityStore()
        self.assertEqual(store.collector, "fallback")

    def test_ingest_rejects_missing_secret(self) -> None:
        payload = ObservabilityIngest(collector="ebpf")
        with patch("app.api.observability.settings.observability_ingest_secret", "a" * 32):
            with self.assertRaises(HTTPException) as raised:
                ingest(payload, None)
        self.assertEqual(raised.exception.status_code, 401)

    def test_ingest_placeholder_secret_is_not_accepted_as_configuration(self) -> None:
        payload = ObservabilityIngest(collector="ebpf")
        with patch("app.api.observability.settings.observability_ingest_secret", "replace-with-a-long-random-ingest-secret"):
            with self.assertRaises(HTTPException) as raised:
                ingest(payload, "replace-with-a-long-random-ingest-secret")
        self.assertEqual(raised.exception.status_code, 503)
        self.assertFalse(_ingest_secret_is_configured("short"))

    def test_ingest_schema_rejects_invalid_security_severity(self) -> None:
        with self.assertRaises(ValueError):
            ObservabilityIngest.model_validate({"security_events": [{
                "timestamp": "now", "pid": 1, "comm": "api", "type": "open",
                "details": "path", "severity": "urgent",
            }]})

    def test_expired_ebpf_ingest_returns_to_fallback(self) -> None:
        store = ObservabilityStore()
        store.ingest({"collector": "ebpf", "probes_loaded": ["test"], "db_latency": {"samples": 1}})
        store.last_update = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
        self.assertEqual(store.status()["collector"], "fallback")
        self.assertNotIn("test", store.status()["probes_loaded"])

    def test_empty_ebpf_db_payload_does_not_hide_app_measured_latency(self) -> None:
        store = ObservabilityStore()
        store.record_db_latency(30)
        store.ingest({"collector": "ebpf", "db_latency": {"samples": 0}})
        self.assertEqual(store.snapshot()["db_latency"]["samples"], 1)

    def test_route_metric_cardinality_is_bounded(self) -> None:
        store = ObservabilityStore()
        for index in range(500):
            store.record_request(f"/random/{index}", 1)
        self.assertLessEqual(len(store.metrics["routes"]), 100)

    def test_ingest_schema_bounds_security_event_count(self) -> None:
        with self.assertRaises(ValueError):
            ObservabilityIngest.model_validate({"security_events": [
                {"timestamp": "now", "pid": 1, "comm": "api", "type": "open",
                 "details": "event", "severity": "low"}
                for _ in range(101)
            ]})

    def test_login_schema_bounds_username_and_bcrypt_password_length(self) -> None:
        with self.assertRaises(ValueError):
            LoginRequest(username="u" * 256, password="valid-password")
        with self.assertRaises(ValueError):
            LoginRequest(username="admin", password="é" * 37)


if __name__ == "__main__":
    unittest.main()
