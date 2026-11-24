from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
for import_path in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.services.observability import ObservabilityStore, RingBuffer
from app.api.observability import _ingest_secret_is_configured, ingest
from app.api import observability as observability_api
from app.core.security import get_current_user
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

    def test_ingest_accepts_a_configured_random_secret(self) -> None:
        payload = ObservabilityIngest(collector="ebpf")
        secret = "r" * 48
        with patch("app.api.observability.settings.observability_ingest_secret", secret), patch(
            "app.api.observability.observability_store.ingest"
        ) as store_ingest:
            result = ingest(payload, secret)

        self.assertEqual(result, {"accepted": True})
        store_ingest.assert_called_once()

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


class ObservabilityHistoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = ObservabilityStore()
        patcher = patch.object(observability_api, "observability_store", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = FastAPI()
        self.app.include_router(observability_api.router)
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_history_and_breakdown_require_authentication(self) -> None:
        app = FastAPI()
        app.include_router(observability_api.router)
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/observability/history").status_code, 401)
            self.assertEqual(client.get("/api/observability/breakdown").status_code, 401)

    def test_history_minutes_are_bounded(self) -> None:
        for minutes in (1, 30):
            with self.subTest(minutes=minutes):
                self.assertEqual(self.client.get(f"/api/observability/history?minutes={minutes}").status_code, 200)
        for minutes in (0, 31):
            with self.subTest(minutes=minutes):
                self.assertEqual(self.client.get(f"/api/observability/history?minutes={minutes}").status_code, 422)

    def test_fallback_history_uses_null_for_unavailable_metrics(self) -> None:
        response = self.client.get("/api/observability/history?minutes=1")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)
        sample = response.json()[0]
        self.assertIsNone(sample["app_request_p50_ms"])
        self.assertIsNone(sample["app_request_p95_ms"])
        self.assertIsNone(sample["syscalls_per_second"])
        self.assertIsNone(sample["runq_p95_us"])
        self.assertIsNone(sample["db_latency_p95_ms"])
        self.assertIsNone(sample["tcp_retransmits"])
        self.assertIsNone(sample["cpu_percent"])
        self.assertIsNone(sample["security_events_count"])

    def test_history_length_is_capped_at_900_samples(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for index in range(905):
            self.store.history_samples.append({"timestamp": now, "app_request_p95_ms": float(index)})

        response = self.client.get("/api/observability/history?minutes=30")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 900)

    def test_breakdown_totals_match_source_counts(self) -> None:
        syscall_counts = {"0": 10, "1": 9, "2": 8, "3": 7, "4": 6, "5": 5, "8": 4, "9": 3, "257": 2, "9999": 1}
        events = [
            {"timestamp": "now", "pid": 1, "comm": "api", "type": "openat", "details": "sensitive access", "severity": "high"},
            {"timestamp": "now", "pid": 2, "comm": "sh", "type": "process_exec", "details": "program executed", "severity": "medium"},
        ]
        self.store.ingest({"collector": "ebpf", "syscalls": {"counts": syscall_counts}, "security_events": events})
        self.store.record_request("/api/products", 12.0)
        self.store.record_request("/api/products", 24.0)
        self.store.record_request("/api/transactions", 31.0)

        response = self.client.get("/api/observability/breakdown")

        self.assertEqual(response.status_code, 200, response.text)
        breakdown = response.json()
        self.assertEqual(sum(item["count"] for item in breakdown["syscalls_by_name"]), sum(syscall_counts.values()))
        self.assertEqual(len(breakdown["syscalls_by_name"]), 9)
        self.assertEqual(sum(item["count"] for item in breakdown["security_by_severity"]), len(events))
        self.assertEqual(sum(item["count"] for item in breakdown["security_by_type"]), len(events))
        self.assertEqual(sum(item["count"] for item in breakdown["requests_by_route"]), 3)
        self.assertIn("read", {item["name"] for item in breakdown["syscalls_by_name"]})
        self.assertIn("other", {item["name"] for item in breakdown["syscalls_by_name"]})


if __name__ == "__main__":
    unittest.main()
