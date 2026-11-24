#!/usr/bin/env python3
"""Optional BCC sidecar for the host PID of IntelliStock's FastAPI worker."""
from __future__ import annotations

import json
import ctypes
import os
import platform
import signal
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone

try:
    from bcc import BPF
except ImportError as exc:  # Friendly failure when run outside a configured Linux host.
    raise SystemExit("BCC Python bindings are unavailable; install python3-bpfcc on Linux.") from exc


PROGRAM = r"""
#include <uapi/linux/ptrace.h>
struct security_event_t { u32 pid; char comm[16]; char kind[16]; char path[128]; };
BPF_HASH(syscall_started, u64, u64);
BPF_HASH(syscall_counts, u64, u64);
BPF_HISTOGRAM(syscall_latency_us);
BPF_HASH(wakeup_ns, u32, u64);
BPF_HISTOGRAM(runq_latency_us);
BPF_ARRAY(tcp_retransmits, u64, 1);
BPF_PERF_OUTPUT(security_events);

TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
    u64 id = bpf_get_current_pid_tgid();
    if ((id >> 32) != TARGET_PID) return 0;
    u64 now = bpf_ktime_get_ns(); syscall_started.update(&id, &now);
    u64 key = args->id, zero = 0;
    u64 *count = syscall_counts.lookup_or_try_init(&key, &zero);
    if (count) __sync_fetch_and_add(count, 1);
    return 0;
}
TRACEPOINT_PROBE(raw_syscalls, sys_exit) {
    u64 id = bpf_get_current_pid_tgid();
    if ((id >> 32) != TARGET_PID) return 0;
    u64 *start = syscall_started.lookup(&id); if (!start) return 0;
    u64 delta = (bpf_ktime_get_ns() - *start) / 1000;
    syscall_latency_us.increment(bpf_log2l(delta + 1)); syscall_started.delete(&id);
    return 0;
}
TRACEPOINT_PROBE(sched, sched_wakeup) {
    if (args->pid == TARGET_PID) { u32 pid = args->pid; u64 now = bpf_ktime_get_ns(); wakeup_ns.update(&pid, &now); }
    return 0;
}
TRACEPOINT_PROBE(sched, sched_switch) {
    if (args->next_pid == TARGET_PID) {
        u32 pid = args->next_pid; u64 *start = wakeup_ns.lookup(&pid);
        if (start) { runq_latency_us.increment(bpf_log2l((bpf_ktime_get_ns() - *start) / 1000 + 1)); wakeup_ns.delete(&pid); }
    }
    return 0;
}
TRACEPOINT_PROBE(tcp, tcp_retransmit_skb) {
    int key = 0; u64 *count = tcp_retransmits.lookup(&key);
    if (count) __sync_fetch_and_add(count, 1);
    return 0;
}
TRACEPOINT_PROBE(syscalls, sys_enter_openat) {
    if ((bpf_get_current_pid_tgid() >> 32) != TARGET_PID) return 0;
    struct security_event_t event = {};
    event.pid = TARGET_PID; bpf_get_current_comm(&event.comm, sizeof(event.comm));
    __builtin_memcpy(&event.kind, "openat", 7);
    bpf_probe_read_user_str(&event.path, sizeof(event.path), (void *)args->filename);
    security_events.perf_submit(args, &event, sizeof(event));
    return 0;
}
TRACEPOINT_PROBE(sched, sched_process_exec) {
    if ((bpf_get_current_pid_tgid() >> 32) != TARGET_PID) return 0;
    struct security_event_t event = {};
    event.pid = TARGET_PID; bpf_get_current_comm(&event.comm, sizeof(event.comm));
    __builtin_memcpy(&event.kind, "process_exec", 13);
    security_events.perf_submit(args, &event, sizeof(event));
    return 0;
}
"""


def _log2_percentile(histogram: dict[int, int], percentile: float) -> float:
    total = sum(histogram.values())
    if not total:
        return 0.0
    target = max(1, int(total * percentile + 0.999))
    cumulative = 0
    for bucket, count in sorted(histogram.items()):
        cumulative += count
        if cumulative >= target:
            return float(max(0, (1 << bucket) - 1))
    return 0.0


def _event_severity(kind: str, path: str, comm: str, sensitive_paths: tuple[str, ...]) -> tuple[str, str] | None:
    if kind == "process_exec":
        lowered = f"{path} {comm}".casefold()
        severity = "high" if any(shell in lowered for shell in ("/sh", "/bash", "/dash")) else "medium"
        return severity, "Backend process executed a program"
    normalized = path.replace("\\", "/").casefold()
    if any(item.casefold() in normalized for item in sensitive_paths if item):
        # Never publish the filename: paths can disclose secrets or deployment layout.
        return "high", "Backend opened a configured sensitive path"
    return None


def main() -> int:
    target_pid = int(os.getenv("BACKEND_PID", "0"))
    if target_pid <= 0:
        print("Set BACKEND_PID to the host PID of the FastAPI worker", file=sys.stderr)
        return 2
    endpoint = os.getenv("OBSERVABILITY_INGEST_URL", "http://127.0.0.1:8000/api/observability/ingest")
    secret = os.getenv("OBSERVABILITY_INGEST_SECRET", "")
    if len(secret) < 32 or secret.lower().startswith(("replace-", "changeme", "example")):
        print("OBSERVABILITY_INGEST_SECRET must be a non-placeholder secret of at least 32 characters", file=sys.stderr)
        return 2
    sensitive_paths = tuple(item.strip() for item in os.getenv("SENSITIVE_PATHS", "/.env,/etc/passwd,/etc/shadow,/.ssh,intellistock.db").split(","))
    try:
        bpf = BPF(text=PROGRAM.replace("TARGET_PID", str(target_pid)))
    except Exception as exc:
        print(f"Unable to load eBPF probes on kernel {platform.release()}: {exc}", file=sys.stderr)
        return 3

    events: deque[dict[str, object]] = deque(maxlen=100)

    def on_security_event(_cpu, data, _size):
        raw = bpf["security_events"].event(data)
        kind = raw.kind.decode(errors="replace").rstrip("\0")
        path = raw.path.decode(errors="replace").rstrip("\0")
        comm = raw.comm.decode(errors="replace").rstrip("\0")[:16]
        classified = _event_severity(kind, path, comm, sensitive_paths)
        if classified:
            severity, details = classified
            events.append({"timestamp": datetime.now(timezone.utc).isoformat(), "pid": int(raw.pid),
                           "comm": comm,
                           "type": kind, "details": details, "severity": severity})

    bpf["security_events"].open_perf_buffer(on_security_event, page_cnt=8)
    loaded = ["raw_syscalls:sys_enter", "raw_syscalls:sys_exit", "sched:sched_wakeup", "sched:sched_switch",
              "tcp:tcp_retransmit_skb", "syscalls:sys_enter_openat", "sched:sched_process_exec"]
    print(f"eBPF probes loaded for backend PID {target_pid} on {platform.release()}", flush=True)
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            bpf.perf_buffer_poll(timeout=200)
            counts = {str(key.value): int(value.value) for key, value in bpf["syscall_counts"].items()}
            syscall_hist = {int(key.value): int(value.value) for key, value in bpf["syscall_latency_us"].items()}
            runq_hist = {int(key.value): int(value.value) for key, value in bpf["runq_latency_us"].items()}
            retransmits = int(bpf["tcp_retransmits"][ctypes.c_int(0)].value)
            payload = {"collector": "ebpf", "probes_loaded": loaded,
                       "cpu": {"process_percent": None, "runq_p95_us": _log2_percentile(runq_hist, .95)},
                       "syscalls": {"counts": counts, "latency_histogram_log2_us": syscall_hist,
                                    "p95_us": _log2_percentile(syscall_hist, .95)},
                       "db_latency": {}, "network": {"retransmits": retransmits},
                       "security_events": list(events)}
            request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={
                "Content-Type": "application/json", "X-Ingest-Secret": secret}, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=3):
                    events.clear()
            except (urllib.error.URLError, TimeoutError) as exc:
                print(f"Metrics publish failed: {exc}", file=sys.stderr, flush=True)
            time.sleep(1.8)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"Probe polling failed: {exc}", file=sys.stderr, flush=True)
            time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
