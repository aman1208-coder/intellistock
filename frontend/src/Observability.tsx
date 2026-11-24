import { motion, useReducedMotion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import {
  fetchJson,
  fetchObservabilityBreakdown,
  fetchObservabilityHistory,
  fetchObservabilityMetrics,
  fetchObservabilityStatus,
  fetchSecurityEvents,
  type ObservabilityBreakdown,
  type ObservabilityHistorySample,
  type ObservabilityMetrics,
  type ObservabilityStatus,
  type Product,
  type SecurityEvent,
} from './api';
import BarChart from './charts/BarChart';
import DonutChart from './charts/DonutChart';
import LineChart, { type LineSeries } from './charts/LineChart';

export default function Observability({ products, canManage }: { products: Product[]; canManage: boolean }) {
  const reduceMotion = useReducedMotion();
  const [status, setStatus] = useState<ObservabilityStatus | null>(null);
  const [metrics, setMetrics] = useState<ObservabilityMetrics | null>(null);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [history, setHistory] = useState<ObservabilityHistorySample[]>([]);
  const [breakdown, setBreakdown] = useState<ObservabilityBreakdown | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadHighlight, setLoadHighlight] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const [nextStatus, nextMetrics, nextEvents, nextHistory, nextBreakdown] = await Promise.all([
          fetchObservabilityStatus(),
          fetchObservabilityMetrics(),
          fetchSecurityEvents(30),
          fetchObservabilityHistory(10),
          fetchObservabilityBreakdown(),
        ]);
        if (active) {
          setStatus(nextStatus);
          setMetrics(nextMetrics);
          setEvents(nextEvents);
          setHistory(nextHistory);
          setBreakdown(nextBreakdown);
        }
      } catch {
        // Keep the last complete snapshot if the API is briefly unavailable.
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refreshTick]);

  const runLoad = async () => {
    if (!products.length) return;
    setLoading(true);
    setLoadHighlight(true);
    try {
      await Promise.all(
        Array.from({ length: 8 }, () =>
          fetchJson('/api/inventory/transact-safe', {
            method: 'POST',
            body: JSON.stringify({ product_id: products[0].id, quantity: 1 }),
          }).catch(() => null),
        ),
      );
      await new Promise((resolve) => window.setTimeout(resolve, 2200));
      setRefreshTick((tick) => tick + 1);
    } finally {
      setLoading(false);
      window.setTimeout(() => setLoadHighlight(false), 1800);
    }
  };

  const db = metrics?.db_latency;
  const network = metrics?.network;
  const syscallIds = Object.keys(metrics?.syscalls.counts ?? {}).length;
  const schedulerP95 = metrics?.cpu.runq_p95_us;
  const cpuSummary = metrics?.cpu.process_percent != null
    ? `${metrics.cpu.process_percent.toFixed(1)}% CPU`
    : schedulerP95 != null
      ? `Run queue p95 ${schedulerP95.toFixed(1)} µs`
      : status?.collector === 'ebpf'
        ? 'No run-queue samples'
        : 'CPU unavailable';
  const needsEbpfMessage = status?.collector === 'fallback'
    ? 'Unavailable in fallback mode (needs eBPF)'
    : 'No data yet';

  const latencySeries = useMemo<LineSeries[]>(() => [
    {
      key: 'app', label: 'App request p95', color: '#60d7ff',
      values: history.map((sample) => sample.app_request_p95_ms),
    },
    {
      key: 'db', label: history.some((sample) => sample.db_latency_p95_ms != null) ? 'DB p95' : 'DB p95 (no samples)', color: '#ffc36b',
      values: history.map((sample) => sample.db_latency_p95_ms),
    },
    {
      key: 'runq',
      label: status?.collector === 'fallback'
        ? 'Run queue p95 (needs eBPF)'
        : history.some((sample) => sample.runq_p95_us != null)
          ? 'Run queue p95 (µs → ms)'
          : 'Run queue p95 (no samples)',
      color: '#b99cff',
      values: history.map((sample) => sample.runq_p95_us == null ? null : sample.runq_p95_us / 1000),
    },
  ], [history, status?.collector]);

  const syscallRateSeries = useMemo<LineSeries[]>(() => [{
    key: 'syscalls', label: 'Syscalls / second', color: '#65e6ae',
    values: history.map((sample) => sample.syscalls_per_second),
  }], [history]);

  const retransmitSeries = useMemo<LineSeries[]>(() => [{
    key: 'retransmits', label: 'TCP retransmits', color: '#ff8298',
    values: history.map((sample) => sample.tcp_retransmits),
  }], [history]);

  return (
    <motion.section
      className={`glass-panel observability-panel ${loadHighlight ? 'load-highlight' : ''}`}
      id="observability"
      initial={reduceMotion ? false : { opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24 }}
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">Kernel and application telemetry</span>
          <h2>Observability</h2>
        </div>
        <span className={`collector-badge ${status?.collector ?? 'fallback'}`}>
          {status?.collector === 'ebpf' ? 'eBPF active' : 'Fallback collector'}
        </span>
      </div>

      <div className="fallback-notice">
        Active database: {status?.active_database ?? 'checking…'}
      </div>

      {status?.collector === 'fallback' && (
        <div className="fallback-notice">
          eBPF is not available here, so IntelliStock is using psutil and app-level timing.
        </div>
      )}

      <div className="observability-grid">
        <div className="metric-card">
          <span>DB latency p50 / p95 / p99</span>
          <strong>{db && db.samples > 0 ? `${db.p50_ms.toFixed(1)} / ${db.p95_ms.toFixed(1)} / ${db.p99_ms.toFixed(1)} ms` : 'No DB samples'}</strong>
          <small>{db && db.samples > 0 ? `${db.slow_query_count} slow queries above ${db.threshold_ms} ms` : 'Database query timing unavailable in this collector snapshot'}</small>
        </div>
        <div className="metric-card">
          <span>CPU / scheduler</span>
          <strong>{cpuSummary}</strong>
          <small>{syscallIds} syscall IDs · syscall p95 {metrics?.syscalls.p95_us != null ? `${metrics.syscalls.p95_us.toFixed(1)} µs` : 'unavailable'}</small>
        </div>
        <div className="metric-card">
          <span>TCP network</span>
          <strong>{metrics?.collector === 'ebpf' && network?.retransmits != null ? `${network.retransmits} retransmits` : 'Retransmits unavailable'}</strong>
          <small>{metrics?.collector === 'ebpf' ? 'Resets and connection failures unavailable' : 'Network counters unavailable in fallback mode'}</small>
        </div>
        <div className="metric-card">
          <span>App latency p95</span>
          <strong>{metrics?.app_latency.samples ? `${metrics.app_latency.p95_ms.toFixed(1)} ms` : 'No request samples'}</strong>
          <small>{metrics?.app_latency.samples ?? 0} request samples</small>
        </div>
      </div>

      <div className="observability-actions">
        {canManage ? (
          <button type="button" className="primary" onClick={() => void runLoad()} disabled={loading || !products.length}>
            {loading ? 'Running load...' : 'Run load + watch metrics'}
          </button>
        ) : (
          <p role="note">Load generation is available to admins and warehouse managers only.</p>
        )}
      </div>

      <div className="security-events">
        <h3>Live security events</h3>
        {events.length === 0 ? (
          <p>No security events in the current snapshot.</p>
        ) : (
          <div className="security-table">
            {events.map((event, index) => (
              <div className="security-row" key={`${event.timestamp}-${index}`}>
                <span className={`severity severity-${event.severity}`}>{event.severity}</span>
                <strong>{event.type}</strong>
                <span>{event.comm} [{event.pid}]</span>
                <span>{event.details}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="observability-charts" aria-label="Live observability charts">
        <LineChart
          title="Latency over time"
          description="Rolling 10-minute window · y-axis in ms; run-queue µs converted to ms."
          samples={history}
          series={latencySeries}
          valueSuffix="ms"
          area
          emptyMessage="No data yet"
          filename="intellistock-latency.svg"
        />
        <LineChart
          title="Syscalls per second"
          description="Rate derived from successive eBPF syscall counters."
          samples={history}
          series={syscallRateSeries}
          valueSuffix="calls/s"
          area
          emptyMessage={needsEbpfMessage}
          filename="intellistock-syscalls-per-second.svg"
        />
        <DonutChart
          title="Syscalls by type"
          description="Top eight x86_64 syscall names; remaining calls are grouped as other."
          segments={breakdown?.syscalls_by_name ?? []}
          emptyMessage={needsEbpfMessage}
          filename="intellistock-syscalls-by-type.svg"
        />
        <DonutChart
          title="Security events by severity"
          description="Severity counts from the bounded recent event buffer."
          segments={breakdown?.security_by_severity ?? []}
          emptyMessage={needsEbpfMessage}
          filename="intellistock-security-by-severity.svg"
        />
        <DonutChart
          title="Security events by type"
          description="Recent security-event types, including openat and process execution."
          segments={breakdown?.security_by_type ?? []}
          emptyMessage={needsEbpfMessage}
          filename="intellistock-security-by-type.svg"
        />
        <BarChart
          title="Requests by route"
          description="Request totals since API startup; p95 uses the latest 100 route samples."
          routes={breakdown?.requests_by_route ?? []}
          emptyMessage="No data yet"
          filename="intellistock-requests-by-route.svg"
        />
        <LineChart
          title="TCP retransmits over time"
          description="Host-wide cumulative retransmit counter from the TCP tracepoint."
          samples={history}
          series={retransmitSeries}
          valueSuffix="retransmits"
          emptyMessage={needsEbpfMessage}
          filename="intellistock-tcp-retransmits.svg"
        />
      </div>
    </motion.section>
  );
}
