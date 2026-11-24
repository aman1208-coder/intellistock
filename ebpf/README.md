# Optional Linux eBPF collector

The FastAPI process stays unprivileged and uses fallback telemetry by default. The separate BCC collector attaches probes only after loading succeeds; it reports `collector: "ebpf"` to the API after authenticated ingest. If BCC import, verifier/load, or permissions fail, the collector exits with an error and the API continues in fallback mode.

## WSL2 / Ubuntu setup

eBPF requires a Linux kernel with BPF and the relevant tracepoints enabled (Linux 5.8+ is the target; BTF is preferred). WSL2 kernels differ, so check before installing:

```bash
uname -r
grep -E 'CONFIG_BPF=|CONFIG_BPF_SYSCALL=|CONFIG_DEBUG_INFO_BTF=' /proc/config.gz 2>/dev/null || true
sudo bpftool feature probe kernel
sudo cat /sys/kernel/tracing/available_events | grep -E 'raw_syscalls:sys_(enter|exit)|sched:sched_(switch|wakeup|process_exec)|tcp:tcp_retransmit_skb|syscalls:sys_enter_openat'
```

Install BCC and build tools:

```bash
sudo apt update
sudo apt install -y bpfcc-tools python3-bpfcc linux-headers-$(uname -r) clang bpftool
```

Some WSL kernels do not have matching Ubuntu kernel headers/packages or expose TCP tracepoints. In that case, use a supported Ubuntu VM/host kernel. Docker Desktop on Windows does not grant a Windows kernel eBPF access.

## Run directly on Linux/WSL2

Start PostgreSQL or the SQLite demo API normally, as a regular user. Configure a strong random `OBSERVABILITY_INGEST_SECRET` for both the API and collector; do not leave the example placeholder. By default, the collector detects the backend's kernel-visible TGID from syscall events where the process `comm` is `uvicorn`:

```bash
sudo env BACKEND_PROCESS_NAME=uvicorn \
  OBSERVABILITY_INGEST_SECRET="$OBSERVABILITY_INGEST_SECRET" \
  OBSERVABILITY_INGEST_URL='http://127.0.0.1:8000/api/observability/ingest' \
  SENSITIVE_PATHS='/.env,/etc/passwd,/etc/shadow,/.ssh,intellistock.db' \
  python3 ebpf/collector.py
```

Set `BACKEND_PROCESS_NAME` if the API has a different Linux process name. `BACKEND_PID` is an optional kernel-visible TGID hint; automatic discovery and restart re-resolution work without it. `find_kernel_tgid.py` remains available as a debugging tool. The collector tracks child processes so exec and openat events from backend-launched children can be observed. It requires root or equivalent BPF/perf capabilities; it does not elevate or launch FastAPI. A successful startup prints the loaded probes and the TGID it resolves. Log in to the UI and check `/api/observability/status` for `collector: "ebpf"` after the first successful ingest.

## Probes currently attached

- `raw_syscalls:sys_enter` / `sys_exit`: configured backend process syscall counts and log2 latency histogram, aggregated in BPF hash/histogram maps. `BACKEND_PROCESS_NAME` matches the Linux `comm` value, limited to 15 characters.
- `sched:sched_wakeup` / `sched:sched_switch`: run-queue latency histogram for tracked backend tasks. An empty histogram is reported as unavailable, not `0 µs`.
- `tcp:tcp_retransmit_skb`: host-wide TCP retransmit count. The kernel tracepoint does not associate this counter with the backend PID in this implementation.
- `syscalls:sys_enter_openat`: tracked backend and descendant process events are copied to a perf buffer. User space checks configured sensitive path patterns and drops non-matches; emitted details omit the filename.
- `sched:sched_process_exec`, `sched:sched_process_fork`, `sched:sched_process_exit`: reports tracked executions, tracks child processes, and removes exited tasks. The process-name match also re-resolves the backend after a restart.

The verifier checks BPF programs before loading. BPF maps aggregate high-rate counters and histograms in kernel space; only security candidates are sent through the perf buffer. App request/transaction timing remains available from the API fallback path.

## Limitations

Database p50/p95/p99 in this build come from measured app-side transaction duration, not a kernel/PostgreSQL execution probe. TCP reset counts, connection failures/rates by remote address, and RTT are not implemented. Child processes are tracked recursively through fork/exit tracepoints, but the API does not expose a full process tree. The current openat filter matches the path string supplied by the process; relative paths may not resolve to configured absolute sensitive paths. A single missing kernel tracepoint can prevent this combined collector program from loading; the API then remains in fallback mode.

### WSL2 end-to-end verification (2026-11-24)

Verified on `6.6.114.1-microsoft-standard-WSL2`, with API and BCC collector both running inside WSL2, a temporary SQLite database, and temporary credentials outside the repository. The collector automatically resolved backend TGID `1475`; after restarting the API, it resolved TGID `1852` without using the helper or setting `BACKEND_PID`. Authenticated status showed `collector: "ebpf"`, database `sqlite`, and nine loaded tracepoints. Syscall counts and latency reached the API; the dashboard displayed syscall IDs and app request latency.

| Probe | WSL2 result |
| --- | --- |
| `raw_syscalls:sys_enter` / `sys_exit` | **[Working end to end]** API metrics reported 70 syscall IDs and a syscall p95 of 4,095 µs in the dashboard snapshot. |
| `sched:sched_wakeup` / `sched:sched_switch` | **[Working end to end]** API metrics reported run-queue p95 of 31 µs, including during a 12-second four-worker CPU load. The p95 did not change during that short load, so a load-induced increase was not observed. |
| `tcp:tcp_retransmit_skb` | **[Working end to end]** Twelve connections to a closed localhost port were refused and did not increment retransmits. A timed connection to TEST-NET `192.0.2.1:65000` changed the counter from 0 to 3. This is a system-wide counter. |
| `syscalls:sys_enter_openat` | **[Working end to end]** Opening only `/home/itsmj/.intellistock_test_sensitive`, a harmless disposable file included in test-only `SENSITIVE_PATHS`, produced a high-severity event. The API event contained generic details and no path. No real `.env` file was opened. |
| `sched:sched_process_exec` plus fork/exit tracking | **[Working end to end]** A tracked process spawned `/bin/sh`; a `process_exec` event with `comm: sh` appeared in the API. |

No probe failed to load on this WSL2 kernel. BCC compiles and attaches the probes as one program, so a missing tracepoint or load failure aborts collector startup rather than returning individual failed-probe records.

The dashboard rendered live eBPF mode with `eBPF active`, `Active database: sqlite`, run-queue and syscall latency, a changing retransmit count (3 after the retransmit trigger), app p95 latency and the openat/exec event rows. DB latency showed `No DB samples`; process CPU percentage is not provided by the eBPF collector; TCP resets and connection-failure counts remain unavailable. The scheduler p95 was populated but did not rise during the short CPU-load run. These results verify this WSL2 host, not other Linux kernels or production load.

Reproduce from the repository root in WSL2 with the API already running there and the same strong temporary ingest secret configured for the API and collector. `BACKEND_PID` is unnecessary for the normal auto-detection path:

```bash
uname -r
sudo bpftool feature probe kernel
sudo env BACKEND_PROCESS_NAME=uvicorn \
  OBSERVABILITY_INGEST_SECRET="$OBSERVABILITY_INGEST_SECRET" \
  OBSERVABILITY_INGEST_URL='http://127.0.0.1:8000/api/observability/ingest' \
  python3 ebpf/collector.py
```

Run these controlled checks while the collector and API are active. The CPU loop burns four workers for 12 seconds; `runq_p95_us` should be present in authenticated metrics, though the short test did not raise the p95 on this WSL2 run:

```bash
pids=()
for _ in 1 2 3 4; do (while :; do :; done) & pids+=("$!"); done
sleep 12
kill "${pids[@]}"
```

The TCP probe counts retransmits, not failed connects. A localhost refusal is a control; the TEST-NET attempt induced retransmits on this host:

```bash
python3 - <<'PY'
import socket
for address in (("127.0.0.1", 65534), ("192.0.2.1", 65000)):
    sock = socket.socket()
    sock.settimeout(4)
    try:
        print(address, sock.connect_ex(address))
    finally:
        sock.close()
PY
```

For openat and exec, add the fixture's exact path to test-only `SENSITIVE_PATHS`, create only a harmless file, then run this from the same WSL user. The test process adopts the configured `uvicorn` comm so the collector tracks it, opens the fixture, and spawns a child shell:

```bash
fixture="$HOME/.intellistock_test_sensitive"
printf 'harmless eBPF fixture\n' > "$fixture"
chmod 600 "$fixture"
python3 - <<'PY'
import ctypes, os, subprocess
ctypes.CDLL(None).prctl(15, b"uvicorn", 0, 0, 0)
with open(os.path.expanduser("~/.intellistock_test_sensitive")) as handle:
    handle.read()
subprocess.run(["/bin/sh", "-c", "true"], check=True)
PY
rm -f "$fixture"
```

Check authenticated `GET /api/observability/metrics` for the run-queue p95 and retransmit count, and `GET /api/observability/security-events` for `openat` and `process_exec`. The event details should be generic and must not contain the fixture path. Do not read a real `.env` or other credential file. The helper `python3 ebpf/find_kernel_tgid.py --comm uvicorn --duration 3` remains useful when diagnosing name matching.

After login, check authenticated `GET /api/observability/status` and `GET /api/observability/metrics`, then run both `/api/inventory/transact-safe` and `/api/inventory/transact-unsafe` against seeded products and check for advancing syscall counts and app-side DB samples. Do not use a real secret or a real `.env` file for a security-event demonstration.

`docker-compose.ebpf.yml` is an optional development convenience and runs privileged with host PID and kernel mounts. Treat it as dev/demo only. Production should use a dedicated node agent with narrowly scoped `CAP_BPF`/`CAP_PERFMON`, a private transport, a narrow monitoring policy, and an explicit review of kernel support. Never expose ingest publicly or run FastAPI as root.
