#!/usr/bin/env python3
"""Optional BCC sidecar for IntelliStock's FastAPI worker."""
from __future__ import annotations

import json
import ctypes
import os
import platform
import re
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
struct candidate_t { u64 first_seen_ns; u64 last_seen_ns; };
BPF_ARRAY(target_tgid, u32, 1);
BPF_HASH(backend_candidates, u32, struct candidate_t, 128);
BPF_HASH(tracked_processes, u32, u8, 4096);
BPF_HASH(tracked_tasks, u32, u8, 8192);
BPF_HASH(syscall_started, u64, u64);
BPF_HASH(syscall_counts, u64, u64);
BPF_HISTOGRAM(syscall_latency_us);
BPF_HASH(wakeup_ns, u32, u64);
BPF_HISTOGRAM(runq_latency_us);
BPF_ARRAY(tcp_retransmits, u64, 1);
BPF_PERF_OUTPUT(security_events);

static inline u32 configured_tgid() {
    u32 zero = 0;
    u32 *target = target_tgid.lookup(&zero);
    return target ? *target : 0;
}

static inline int is_tracked_process(u32 tgid) {
    u32 target = configured_tgid();
    if (target && target == tgid) return 1;
    u8 *tracked = tracked_processes.lookup(&tgid);
    return tracked != 0;
}

TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
    u64 id = bpf_get_current_pid_tgid();
    u32 tgid = id >> 32;
    u32 tid = (u32)id;
    char comm[16] = {};
    bpf_get_current_comm(&comm, sizeof(comm));
    int backend_candidate = __builtin_memcmp(comm, BACKEND_PROCESS_NAME, sizeof(BACKEND_PROCESS_NAME)) == 0;
    if (backend_candidate) {
        struct candidate_t candidate = {};
        struct candidate_t *previous = backend_candidates.lookup(&tgid);
        candidate.first_seen_ns = previous ? previous->first_seen_ns : bpf_ktime_get_ns();
        candidate.last_seen_ns = bpf_ktime_get_ns();
        backend_candidates.update(&tgid, &candidate);
    }
    if (!backend_candidate && !is_tracked_process(tgid)) return 0;
    u8 one = 1;
    tracked_processes.update(&tgid, &one);
    tracked_tasks.update(&tid, &one);
    u64 now = bpf_ktime_get_ns(); syscall_started.update(&id, &now);
    u64 key = args->id, zero = 0;
    u64 *count = syscall_counts.lookup_or_try_init(&key, &zero);
    if (count) __sync_fetch_and_add(count, 1);
    return 0;
}
TRACEPOINT_PROBE(raw_syscalls, sys_exit) {
    u64 id = bpf_get_current_pid_tgid();
    if (!is_tracked_process(id >> 32)) return 0;
    u64 *start = syscall_started.lookup(&id); if (!start) return 0;
    u64 delta = (bpf_ktime_get_ns() - *start) / 1000;
    syscall_latency_us.increment(bpf_log2l(delta + 1)); syscall_started.delete(&id);
    return 0;
}
TRACEPOINT_PROBE(sched, sched_wakeup) {
    u32 pid = args->pid;
    if (tracked_tasks.lookup(&pid)) { u64 now = bpf_ktime_get_ns(); wakeup_ns.update(&pid, &now); }
    return 0;
}
TRACEPOINT_PROBE(sched, sched_switch) {
    u32 pid = args->next_pid;
    if (tracked_tasks.lookup(&pid)) {
        u64 *start = wakeup_ns.lookup(&pid);
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
    u32 tgid = bpf_get_current_pid_tgid() >> 32;
    if (!is_tracked_process(tgid)) return 0;
    struct security_event_t event = {};
    event.pid = tgid; bpf_get_current_comm(&event.comm, sizeof(event.comm));
    __builtin_memcpy(&event.kind, "openat", 7);
    bpf_probe_read_user_str(&event.path, sizeof(event.path), (void *)args->filename);
    security_events.perf_submit(args, &event, sizeof(event));
    return 0;
}
TRACEPOINT_PROBE(sched, sched_process_exec) {
    u32 tgid = bpf_get_current_pid_tgid() >> 32;
    if (!is_tracked_process(tgid)) return 0;
    struct security_event_t event = {};
    event.pid = tgid; bpf_get_current_comm(&event.comm, sizeof(event.comm));
    __builtin_memcpy(&event.kind, "process_exec", 13);
    security_events.perf_submit(args, &event, sizeof(event));
    return 0;
}
TRACEPOINT_PROBE(sched, sched_process_fork) {
    u32 parent_tgid = bpf_get_current_pid_tgid() >> 32;
    if (!is_tracked_process(parent_tgid)) return 0;
    u32 child_pid = args->child_pid;
    u8 one = 1;
    tracked_processes.update(&child_pid, &one);
    tracked_tasks.update(&child_pid, &one);
    return 0;
}
TRACEPOINT_PROBE(sched, sched_process_exit) {
    u32 tid = args->pid;
    u32 tgid = bpf_get_current_pid_tgid() >> 32;
    char comm[16] = {};
    bpf_get_current_comm(&comm, sizeof(comm));
    if (__builtin_memcmp(comm, BACKEND_PROCESS_NAME, sizeof(BACKEND_PROCESS_NAME)) == 0) {
        backend_candidates.delete(&tgid);
    }
    tracked_tasks.delete(&tid);
    if (tid == tgid) tracked_processes.delete(&tgid);
    return 0;
}
"""


def _log2_percentile(histogram: dict[int, int], percentile: float) -> float | None:
    total = sum(histogram.values())
    if not total:
        return None
    target = max(1, int(total * percentile + 0.999))
    cumulative = 0
    for bucket, count in sorted(histogram.items()):
        cumulative += count
        if cumulative >= target:
            return float(max(0, (1 << bucket) - 1))
    return None


def _event_severity(kind: str, path: str, comm: str, sensitive_paths: tuple[str, ...]) -> tuple[str, str] | None:
    if kind == "process_exec":
        lowered = f"{path} {comm}".casefold()
        severity = "high" if comm.casefold() in {"sh", "bash", "dash", "zsh"} or any(
            shell in lowered for shell in ("/sh", "/bash", "/dash", "/zsh")
        ) else "medium"
        return severity, "Backend process executed a program"
    normalized = path.replace("\\", "/").casefold()
    if any(item.casefold() in normalized for item in sensitive_paths if item):
        # Never publish the filename: paths can disclose secrets or deployment layout.
        return "high", "Backend opened a configured sensitive path"
    return None


def main() -> int:
    backend_process_name = os.getenv("BACKEND_PROCESS_NAME", "uvicorn").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", backend_process_name):
        print("BACKEND_PROCESS_NAME must be 1-15 ASCII letters, digits, dots, underscores, or hyphens", file=sys.stderr)
        return 2
    try:
        pid_hint = int(os.getenv("BACKEND_PID", "0")) or None
    except ValueError:
        print("BACKEND_PID must be a positive kernel-visible TGID", file=sys.stderr)
        return 2
    if pid_hint is not None and pid_hint <= 0:
        print("BACKEND_PID must be a positive kernel-visible TGID", file=sys.stderr)
        return 2
    endpoint = os.getenv("OBSERVABILITY_INGEST_URL", "http://127.0.0.1:8000/api/observability/ingest")
    secret = os.getenv("OBSERVABILITY_INGEST_SECRET", "")
    if len(secret) < 32 or secret.lower().startswith(("replace-", "changeme", "example")):
        print("OBSERVABILITY_INGEST_SECRET must be a non-placeholder secret of at least 32 characters", file=sys.stderr)
        return 2
    sensitive_paths = tuple(item.strip() for item in os.getenv("SENSITIVE_PATHS", "/.env,/etc/passwd,/etc/shadow,/.ssh,intellistock.db").split(","))
    program = PROGRAM.replace("BACKEND_PROCESS_NAME", json.dumps(backend_process_name))
    try:
        bpf = BPF(text=program)
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
              "tcp:tcp_retransmit_skb", "syscalls:sys_enter_openat", "sched:sched_process_exec",
              "sched:sched_process_fork", "sched:sched_process_exit"]
    target_map = bpf["target_tgid"]
    target_map[ctypes.c_int(0)] = ctypes.c_uint(pid_hint or 0)
    target_pid = pid_hint
    candidate_first_seen: dict[int, int] = {}
    last_discovery_notice = 0.0
    print(
        f"eBPF probes loaded; resolving comm={backend_process_name!r} on {platform.release()}",
        flush=True,
    )
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            bpf.perf_buffer_poll(timeout=200)
            now_ns = time.monotonic_ns()
            candidates: list[tuple[int, int]] = []
            for candidate, timestamps in list(bpf["backend_candidates"].items()):
                kernel_tgid = int(candidate.value)
                last_seen = int(timestamps.last_seen_ns)
                first_seen = int(timestamps.first_seen_ns)
                if now_ns - last_seen > 5_000_000_000:
                    del bpf["backend_candidates"][candidate]
                    candidate_first_seen.pop(kernel_tgid, None)
                    continue
                candidate_first_seen.setdefault(kernel_tgid, first_seen)
                candidates.append((kernel_tgid, last_seen))

            active_ids = {candidate for candidate, _ in candidates}
            candidate_first_seen = {
                candidate: first_seen
                for candidate, first_seen in candidate_first_seen.items()
                if candidate in active_ids
            }
            if pid_hint in active_ids:
                resolved_pid = pid_hint
            elif candidates:
                resolved_pid = min(candidates, key=lambda item: candidate_first_seen[item[0]])[0]
            else:
                resolved_pid = pid_hint

            if resolved_pid != target_pid:
                target_pid = resolved_pid
                target_map[ctypes.c_int(0)] = ctypes.c_uint(target_pid or 0)
                if target_pid is not None:
                    print(
                        f"Tracking backend TGID {target_pid} (comm={backend_process_name!r})",
                        flush=True,
                    )
            elif target_pid is None and time.monotonic() - last_discovery_notice >= 10:
                print(
                    f"Waiting for a process with comm={backend_process_name!r}",
                    file=sys.stderr,
                    flush=True,
                )
                last_discovery_notice = time.monotonic()

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
