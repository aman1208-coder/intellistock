from __future__ import annotations

import platform
import os
import statistics
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.db.session import active_database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RingBuffer:
    def __init__(self, max_items: int = 1000) -> None:
        self._items: deque[Any] = deque(maxlen=max_items)

    def append(self, item: Any) -> None:
        self._items.append(item)

    def snapshot(self, limit: int | None = None) -> list[Any]:
        items = list(self._items)
        if limit is not None:
            items = items[-limit:]
        return items

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


class FallbackCollector:
    name = "fallback"

    def __init__(self) -> None:
        self.available = True

    def probe_load_attempt(self) -> list[str]:
        return ["app-middleware", "psutil", "pg-stat-activity"]

    def sample(self) -> dict[str, Any]:
        """Return best-effort host process metrics without making psutil mandatory."""
        try:
            import psutil

            process = psutil.Process(os.getpid())
            return {"cpu": {"process_percent": process.cpu_percent(), "rss_bytes": process.memory_info().rss}}
        except (ImportError, OSError, RuntimeError):
            return {"cpu": {}}


class EbpfCollector:
    name = "ebpf"

    def __init__(self) -> None:
        # Probe loading happens in ebpf/collector.py, never in the API process.
        # Ingest switches the store to ebpf only after the sidecar reports success.
        self.available = False

    def probe_load_attempt(self) -> list[str]:
        return ["sched-switch", "raw-syscalls", "tcp-network", "openat-security"]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


class ObservabilityStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.app_latencies_ms: deque[float] = deque(maxlen=1000)
        self.db_latencies_ms: deque[float] = deque(maxlen=1000)
        self.security_events = RingBuffer(max_items=1000)
        self.metrics: dict[str, Any] = {}
        self.probes_loaded: list[str] = []
        self.last_update: str | None = None
        self.ebpf = EbpfCollector()
        self.fallback = FallbackCollector()
        self.collector = "ebpf" if self.ebpf.available else "fallback"
        if self.collector == "fallback":
            self.probes_loaded = self.fallback.probe_load_attempt()
        import logging
        logging.getLogger(__name__).info("Observability collector active: %s", self.collector)

    def record_request(self, route: str, latency_ms: float) -> None:
        with self._lock:
            self.app_latencies_ms.append(max(0.0, latency_ms))
            route_key = route or "unknown"
            route_metrics = self.metrics.setdefault("routes", {})
            if route_key not in route_metrics and len(route_metrics) >= 99:
                route_key = "__other__"
            bucket = route_metrics.setdefault(route_key, deque(maxlen=100))
            bucket.append(max(0.0, latency_ms))

    def record_db_latency(self, latency_ms: float) -> None:
        with self._lock:
            self.db_latencies_ms.append(max(0.0, latency_ms))
            if latency_ms >= settings.slow_query_ms:
                self.metrics["slow_query_count"] = int(self.metrics.get("slow_query_count", 0)) + 1

    def ingest(self, payload: dict[str, Any]) -> None:
        with self._lock:
            requested_collector = payload.get("collector", "ebpf")
            self.collector = "ebpf" if requested_collector == "ebpf" else "fallback"
            for key in ("cpu", "syscalls", "db_latency", "network"):
                if key in payload:
                    if key == "db_latency" and not payload[key].get("samples"):
                        continue
                    self.metrics[key] = payload[key]
            self.probes_loaded = list(payload.get("probes_loaded") or self.probes_loaded)
            for event in payload.get("security_events", []):
                self.security_events.append(event)
            self.last_update = utc_now()

    def _refresh_collector_state(self) -> None:
        if self.collector != "ebpf" or not self.last_update:
            return
        try:
            updated = datetime.fromisoformat(self.last_update)
        except ValueError:
            updated = datetime.min.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - updated > timedelta(seconds=10):
            self.collector = "fallback"
            for key in ("cpu", "syscalls", "db_latency", "network"):
                self.metrics.pop(key, None)
            self.probes_loaded = self.fallback.probe_load_attempt()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_collector_state()
            if self.collector == "fallback" and "cpu" not in self.metrics:
                self.metrics.update(self.fallback.sample())
            ingested_db = dict(self.metrics.get("db_latency", {}))
            latencies = list(self.db_latencies_ms)
            db_latency = {
                "p50_ms": ingested_db.get("p50_ms", _percentile(latencies, 0.50)),
                "p95_ms": ingested_db.get("p95_ms", _percentile(latencies, 0.95)),
                "p99_ms": ingested_db.get("p99_ms", _percentile(latencies, 0.99)),
                "slow_query_count": ingested_db.get("slow_query_count", int(self.metrics.get("slow_query_count", 0))),
                "threshold_ms": settings.slow_query_ms,
                "samples": ingested_db.get("samples", len(latencies)),
                "available": bool(ingested_db.get("samples", len(latencies))),
            }
            app_latencies = list(self.app_latencies_ms)
            return {
                "collector": self.collector,
                "timestamp": utc_now(),
                "cpu": dict(self.metrics.get("cpu", {})),
                "syscalls": dict(self.metrics.get("syscalls", {})),
                "db_latency": db_latency,
                "network": dict(self.metrics.get("network", {})),
                "app_latency": {
                    "p50_ms": _percentile(app_latencies, 0.50),
                    "p95_ms": _percentile(app_latencies, 0.95),
                    "p99_ms": _percentile(app_latencies, 0.99),
                    "samples": len(app_latencies),
                    "routes": {
                        route: {
                            "p95_ms": _percentile(list(values), 0.95),
                            "samples": len(values),
                        }
                        for route, values in self.metrics.get("routes", {}).items()
                    },
                },
                "last_update": self.last_update,
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_collector_state()
            return {
                "collector": self.collector,
                "active_database": active_database,
                "kernel_version": platform.release(),
                "probes_loaded": list(self.probes_loaded),
                "last_update": self.last_update,
                "enabled": settings.observability_enabled,
            }


observability_store = ObservabilityStore()
