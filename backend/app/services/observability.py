from __future__ import annotations

import platform
import os
import statistics
import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.db.session import active_database

HISTORY_MAX_SAMPLES = 900
HISTORY_SAMPLE_INTERVAL_SECONDS = 2.0


X86_64_SYSCALL_NAMES = {
    0: "read", 1: "write", 2: "open", 3: "close", 4: "stat", 5: "fstat",
    8: "lseek", 9: "mmap", 10: "mprotect", 11: "munmap", 12: "brk",
    16: "ioctl", 17: "pread64", 18: "pwrite64", 19: "readv", 20: "writev",
    21: "access", 22: "pipe", 32: "dup", 33: "dup2", 35: "nanosleep",
    39: "getpid", 41: "socket", 42: "connect", 43: "accept", 44: "sendto",
    45: "recvfrom", 46: "sendmsg", 47: "recvmsg", 49: "bind", 50: "listen",
    56: "clone", 57: "fork", 58: "vfork", 59: "execve", 60: "exit",
    62: "kill", 72: "fcntl", 80: "chdir", 89: "readlink", 96: "gettimeofday",
    158: "arch_prctl", 202: "futex", 217: "getdents64", 218: "set_tid_address",
    228: "clock_gettime", 231: "exit_group", 257: "openat", 262: "newfstatat",
    267: "readlinkat", 273: "set_robust_list", 291: "epoll_create1", 292: "dup3",
    293: "pipe2", 302: "prlimit64", 318: "getrandom", 332: "statx", 435: "clone3",
}


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
        self._process: Any | None = None
        self._cpu_primed = False

    def probe_load_attempt(self) -> list[str]:
        return ["app-middleware", "psutil", "pg-stat-activity"]

    def sample(self) -> dict[str, Any]:
        """Return best-effort host process metrics without making psutil mandatory."""
        try:
            import psutil

            if self._process is None:
                self._process = psutil.Process(os.getpid())
            if not self._cpu_primed:
                self._process.cpu_percent(interval=None)
                self._cpu_primed = True
                process_percent = None
            else:
                process_percent = self._process.cpu_percent(interval=None)
            return {"cpu": {"process_percent": process_percent, "rss_bytes": self._process.memory_info().rss}}
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
        self.security_events_total = 0
        self.security_data_received = False
        self.network_data_received = False
        self.history_samples = RingBuffer(max_items=HISTORY_MAX_SAMPLES)
        self.request_counts: dict[str, int] = {}
        self._last_history_sample_monotonic: float | None = None
        self._last_syscall_total: int | None = None
        self._last_syscall_sample_monotonic: float | None = None
        self._last_security_events_total = 0
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
            self.request_counts[route_key] = self.request_counts.get(route_key, 0) + 1

    def record_db_latency(self, latency_ms: float) -> None:
        with self._lock:
            self.db_latencies_ms.append(max(0.0, latency_ms))
            if latency_ms >= settings.slow_query_ms:
                self.metrics["slow_query_count"] = int(self.metrics.get("slow_query_count", 0)) + 1

    def ingest(self, payload: dict[str, Any]) -> None:
        with self._lock:
            requested_collector = payload.get("collector", "ebpf")
            self.collector = "ebpf" if requested_collector == "ebpf" else "fallback"
            if self.collector == "ebpf":
                if "security_events" in payload:
                    self.security_data_received = True
                network = payload.get("network")
                if isinstance(network, dict) and any(
                    network.get(key) is not None
                    for key in (
                        "retransmits",
                        "resets",
                        "connection_failures",
                        "connection_rate",
                        "tcp_rtt_p95_ms",
                    )
                ):
                    self.network_data_received = True
            for key in ("cpu", "syscalls", "db_latency", "network"):
                if key in payload:
                    if key == "db_latency" and not payload[key].get("samples"):
                        continue
                    self.metrics[key] = payload[key]
            self.probes_loaded = list(payload.get("probes_loaded") or self.probes_loaded)
            if self.collector == "ebpf":
                for event in payload.get("security_events", []):
                    self.security_events.append(event)
                    self.security_events_total += 1
            self.last_update = utc_now()
            self._record_history_sample_locked()

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

    def _record_history_sample_locked(self, *, force: bool = False) -> None:
        self._refresh_collector_state()
        now_monotonic = time.monotonic()
        previous_sample = self._last_history_sample_monotonic
        if (
            not force
            and previous_sample is not None
            and now_monotonic - previous_sample < HISTORY_SAMPLE_INTERVAL_SECONDS
        ):
            return

        if self.collector == "fallback":
            self.metrics.update(self.fallback.sample())

        app_latencies = list(self.app_latencies_ms)
        db_latencies = list(self.db_latencies_ms)
        ingested_db = self.metrics.get("db_latency", {})
        db_samples = int(ingested_db.get("samples", 0) or 0)
        if db_samples > 0:
            db_p95: float | None = ingested_db.get("p95_ms")
        elif db_latencies:
            db_p95 = _percentile(db_latencies, 0.95)
        else:
            db_p95 = None

        syscall_rate: float | None = None
        syscall_counts = self.metrics.get("syscalls", {}).get("counts", {})
        if self.collector == "ebpf" and syscall_counts:
            current_total = sum(max(0, int(value)) for value in syscall_counts.values())
            previous_total = self._last_syscall_total
            previous_time = self._last_syscall_sample_monotonic
            if previous_total is not None and previous_time is not None:
                elapsed = now_monotonic - previous_time
                if elapsed > 0 and current_total >= previous_total:
                    syscall_rate = (current_total - previous_total) / elapsed
            self._last_syscall_total = current_total
            self._last_syscall_sample_monotonic = now_monotonic
        else:
            self._last_syscall_total = None
            self._last_syscall_sample_monotonic = None

        cpu_percent = self.metrics.get("cpu", {}).get("process_percent")
        network = self.metrics.get("network", {})
        retransmits = (
            max(0, int(network["retransmits"]))
            if self.collector == "ebpf" and network.get("retransmits") is not None
            else None
        )
        if self.collector == "ebpf":
            security_events_count: int | None = max(
                0, self.security_events_total - self._last_security_events_total
            )
            self._last_security_events_total = self.security_events_total
        else:
            security_events_count = None
            self._last_security_events_total = self.security_events_total

        self.history_samples.append({
            "timestamp": utc_now(),
            "app_request_p50_ms": _percentile(app_latencies, 0.50) if app_latencies else None,
            "app_request_p95_ms": _percentile(app_latencies, 0.95) if app_latencies else None,
            "syscalls_per_second": syscall_rate,
            "runq_p95_us": self.metrics.get("cpu", {}).get("runq_p95_us") if self.collector == "ebpf" else None,
            "db_latency_p95_ms": db_p95,
            "tcp_retransmits": retransmits,
            "cpu_percent": cpu_percent,
            "security_events_count": security_events_count,
        })
        self._last_history_sample_monotonic = now_monotonic

    def history_snapshot(self, minutes: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            self._record_history_sample_locked()
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            samples = self.history_samples.snapshot()
            return [
                sample for sample in samples
                if datetime.fromisoformat(sample["timestamp"]) >= cutoff
            ]

    @staticmethod
    def _count_breakdown(counts: Counter[str], *, limit: int | None = None) -> list[dict[str, Any]]:
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if limit is not None and len(ordered) > limit:
            kept = ordered[:limit - 1]
            other_count = sum(count for _, count in ordered[limit - 1:])
            ordered = kept + [("other", other_count)]
        total = sum(count for _, count in ordered)
        if total == 0:
            return []
        return [
            {"name": name, "count": count, "percentage": round(count * 100 / total, 2)}
            for name, count in ordered
        ]

    def breakdown(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_collector_state()
            syscall_counts = self.metrics.get("syscalls", {}).get("counts", {})
            syscall_names: Counter[str] = Counter()
            if self.collector == "ebpf" and platform.machine().casefold() in {"x86_64", "amd64"}:
                for raw_id, raw_count in syscall_counts.items():
                    try:
                        syscall_id, count = int(raw_id), max(0, int(raw_count))
                    except (TypeError, ValueError):
                        continue
                    if count:
                        syscall_names[X86_64_SYSCALL_NAMES.get(syscall_id, "other")] += count
            syscalls_by_name = self._count_breakdown(syscall_names, limit=9)

            events = self.security_events.snapshot()
            severity_counts = Counter(str(event.get("severity", "unknown")) for event in events)
            type_counts = Counter(str(event.get("type", "unknown")) for event in events)

            routes = self.metrics.get("routes", {})
            requests_by_route = []
            for route, count in self.request_counts.items():
                latencies = list(routes.get(route, ()))
                requests_by_route.append({
                    "route": route,
                    "count": count,
                    "p95_ms": _percentile(latencies, 0.95) if latencies else None,
                    "samples": len(latencies),
                })
            requests_by_route.sort(key=lambda item: (-item["count"], item["route"]))

            return {
                "collector": self.collector,
                "syscalls_by_name": syscalls_by_name,
                "security_by_severity": self._count_breakdown(severity_counts),
                "security_by_type": self._count_breakdown(type_counts, limit=100),
                "requests_by_route": requests_by_route,
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

    def has_security_event_data(self) -> bool:
        with self._lock:
            self._refresh_collector_state()
            return self.collector == "ebpf" and self.security_data_received

    def has_network_data(self) -> bool:
        with self._lock:
            self._refresh_collector_state()
            return self.collector == "ebpf" and self.network_data_received


observability_store = ObservabilityStore()
