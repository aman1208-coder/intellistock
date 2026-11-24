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

Start PostgreSQL and the API normally, as a regular user. Use a strong random ingest secret in `backend/.env`, for example `openssl rand -hex 32`; do not leave the example placeholder. Find the host PID of the Uvicorn worker (the collector must be able to see this same PID):

```bash
pgrep -af 'uvicorn app.main:app'
```

Then start the collector with privileges, using the PID printed above and the exact same secret as the backend:

```bash
sudo env BACKEND_PID=12345 \
  OBSERVABILITY_INGEST_SECRET='paste-the-generated-secret-here' \
  OBSERVABILITY_INGEST_URL='http://127.0.0.1:8000/api/observability/ingest' \
  SENSITIVE_PATHS='/.env,/etc/passwd,/etc/shadow,/.ssh,intellistock.db' \
  python3 ebpf/collector.py
```

The collector requires root or equivalent BPF/perf capabilities. It does not elevate or launch FastAPI. A successful startup prints the loaded probe list. Log in to the UI and check `/api/observability/status` to see `collector: "ebpf"` after the first successful ingest.

## Probes currently attached

- `raw_syscalls:sys_enter` / `sys_exit`: backend PID syscall counts and log2 latency histogram, aggregated in BPF hash/histogram maps.
- `sched:sched_wakeup` / `sched:sched_switch`: backend process run-queue latency histogram.
- `tcp:tcp_retransmit_skb`: host-wide TCP retransmit count. The kernel tracepoint does not associate this counter with the backend PID in this implementation.
- `syscalls:sys_enter_openat`: only backend PID events are copied to a perf buffer. User space checks configured sensitive path patterns and drops non-matches; emitted details omit the filename.
- `sched:sched_process_exec`: reports execs made by the monitored backend PID. It does not currently track child process ancestry.

The verifier checks BPF programs before loading. BPF maps aggregate high-rate counters and histograms in kernel space; only security candidates are sent through the perf buffer. App request/transaction timing remains available from the API fallback path.

## Limitations

Database p50/p95/p99 in this build come from measured app-side transaction duration, not a kernel/PostgreSQL execution probe. TCP reset counts, connection failures/rates by remote address, RTT, and child process ancestry are not implemented. The current openat filter matches the path string supplied by the process; relative paths may not resolve to configured absolute sensitive paths. A single missing kernel tracepoint can prevent this combined collector program from loading; the API then remains in fallback mode.

`docker-compose.ebpf.yml` is an optional development convenience and runs privileged with host PID and kernel mounts. Treat it as dev/demo only. Production should use a dedicated node agent with narrowly scoped `CAP_BPF`/`CAP_PERFMON`, a private transport, a narrow monitoring policy, and an explicit review of kernel support. Never expose ingest publicly or run FastAPI as root.
