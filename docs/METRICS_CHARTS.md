# Observability charts

The panel polls authenticated observability endpoints every three seconds and keeps a bounded rolling history in memory. It does not save metrics in browser storage. Charts use inline SVG, show accessible summaries and text legends, and can be downloaded as SVG for reports.

| Chart | Data source | What it means | Healthy vs. unhealthy picture | Viva talking points |
|---|---|---|---|---|
| Latency over time | Backend request latency samples; DB query timing when sampled; eBPF scheduler run-queue p95 | App/DB latency is milliseconds; scheduler microseconds are converted to milliseconds for the shared axis | Stable low app latency is healthy; spikes indicate slower responses. DB and run-queue lines are omitted when unavailable rather than plotted as zero. | The app line works in SQLite fallback. DB and run-queue require actual samples; scheduler data requires eBPF. |
| Syscalls per second | Difference between successive eBPF syscall counters | Estimated host/collector syscall rate between samples | A steady baseline with visible activity during load is expected; unexpected sustained spikes merit investigation. | Requires eBPF; fallback explicitly shows “Unavailable in fallback mode (needs eBPF).” |
| Syscalls by type | eBPF syscall counters, mapped through a small x86_64 name table with unknown IDs grouped as `other` | Relative distribution of observed syscall calls | A donut appears only after nonzero syscall counts are received; no-data is shown otherwise. | Only common x86_64 IDs have names; this is not a complete syscall taxonomy. Requires eBPF. |
| Security events by severity | Recent bounded security-event buffer | Distribution of observed events by severity | No events means “No data yet”; it does not mean the host is proven safe. | Requires eBPF event ingestion; demo events should be harmless and use a test file documented in the eBPF guide. |
| Security events by type | Recent bounded security-event buffer | Recent observed event categories such as sensitive-file access and process execution | A donut appears when event records are present; otherwise the chart reports no data. | Requires eBPF ingestion and configured probes. The panel displays event details received from the collector. |
| Requests by route | In-process bounded route counters and recent route latency samples | Top routes by requests since API startup, with p95 from up to the latest 100 route samples | During polling, observability routes accumulate counts. High p95 or a large route count can indicate load; counts reset at backend restart. | This is available in fallback and works with SQLite. Cardinality is bounded by the backend. |
| TCP retransmits over time | eBPF TCP retransmit tracepoint counter | Cumulative retransmits observed by the collector | A flat line means no new retransmits were observed during the window; missing data is shown explicitly. | Requires eBPF and a supported kernel/tracepoint. No retransmits does not imply all network traffic is healthy. |

## Reproduce a fallback demo

1. Follow the SQLite-only backend setup in [README.md](../README.md), seed the demo data, then start the backend and frontend.
2. Sign in and open **Observability**. Confirm the badge says **Fallback collector** and the database is `sqlite`.
3. App latency and requests-by-route should populate as the panel polls. eBPF-only syscall, TCP, and security charts should say they are unavailable in fallback mode.
4. Select **Run load + watch metrics**. It sends eight safe demo transactions and refreshes the panel; watch app latency and route counts update. SQLite does not demonstrate PostgreSQL row-lock semantics.

## Reproduce an eBPF demo

The eBPF-only series have not been verified as part of this chart implementation on this host. Use the setup and exact WSL2/Linux commands in [EBPF_INTEGRATION.md](./EBPF_INTEGRATION.md). Configure the same non-placeholder ingest secret for the backend and collector without committing it. Once the status reports the eBPF collector, run a short safe load and the harmless sensitive-file test described in that guide. A chart is considered populated only when data is actually ingested; the UI does not synthesize samples.
