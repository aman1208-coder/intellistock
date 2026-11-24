#!/usr/bin/env python3
"""Print kernel-visible TGIDs for processes with a selected comm name.

Some WSL2 setups expose different PID values to userspace and BPF helpers.
Run this briefly as root to discover the TGID expected by collector.py.
"""
from __future__ import annotations

import argparse
import json
import re
import time

try:
    from bcc import BPF
except ImportError as exc:
    raise SystemExit("BCC Python bindings are unavailable; install python3-bpfcc on Linux.") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comm", default="uvicorn", help="process comm name (maximum 15 characters)")
    parser.add_argument("--duration", type=float, default=3.0, help="seconds to observe (default: 3)")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", args.comm):
        parser.error("--comm must be 1-15 ASCII letters, digits, dots, underscores, or hyphens")
    if not 0.1 <= args.duration <= 30:
        parser.error("--duration must be between 0.1 and 30 seconds")

    program = r"""
BPF_HASH(observed_tgids, u32, u64);
TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
    char comm[16] = {};
    bpf_get_current_comm(&comm, sizeof(comm));
    if (__builtin_memcmp(comm, TARGET_COMM, sizeof(TARGET_COMM)) != 0) return 0;
    u64 id = bpf_get_current_pid_tgid();
    u32 tgid = id >> 32;
    u64 zero = 0;
    u64 *count = observed_tgids.lookup_or_try_init(&tgid, &zero);
    if (count) __sync_fetch_and_add(count, 1);
    return 0;
}
""".replace("TARGET_COMM", json.dumps(args.comm))

    try:
        bpf = BPF(text=program)
    except Exception as exc:
        raise SystemExit(f"Unable to attach the raw syscall probe: {exc}") from None
    time.sleep(args.duration)
    observations = sorted(
        (int(tgid.value), int(count.value))
        for tgid, count in bpf["observed_tgids"].items()
    )
    if not observations:
        print(f"No syscalls from comm={args.comm!r} observed in {args.duration:g}s")
        return 1
    print("kernel_tgid syscall_count")
    for tgid, count in observations:
        print(f"{tgid} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
