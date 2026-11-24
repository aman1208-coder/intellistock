import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import {
  fetchJson,
  fetchObservabilityMetrics,
  fetchObservabilityStatus,
  fetchSecurityEvents,
  type ObservabilityMetrics,
  type ObservabilityStatus,
  type Product,
  type SecurityEvent,
} from './api';

export default function Observability({ products }: { products: Product[] }) {
  const [status, setStatus] = useState<ObservabilityStatus | null>(null);
  const [metrics, setMetrics] = useState<ObservabilityMetrics | null>(null);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadHighlight, setLoadHighlight] = useState(false);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const [nextStatus, nextMetrics, nextEvents] = await Promise.all([
          fetchObservabilityStatus(),
          fetchObservabilityMetrics(),
          fetchSecurityEvents(30),
        ]);
        if (active) {
          setStatus(nextStatus);
          setMetrics(nextMetrics);
          setEvents(nextEvents);
        }
      } catch {
        // The dashboard keeps its last successful snapshot if the API is briefly unavailable.
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

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
      await new Promise((resolve) => window.setTimeout(resolve, 500));
      setMetrics(await fetchObservabilityMetrics());
    } finally {
      setLoading(false);
      window.setTimeout(() => setLoadHighlight(false), 1800);
    }
  };

  const db = metrics?.db_latency;
  const network = metrics?.network;

  return (
    <motion.section
      className={`glass-panel observability-panel ${loadHighlight ? 'load-highlight' : ''}`}
      id="observability"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
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
          <strong>{db ? `${db.p50_ms.toFixed(1)} / ${db.p95_ms.toFixed(1)} / ${db.p99_ms.toFixed(1)} ms` : 'Waiting...'}</strong>
          <small>{db?.slow_query_count ?? 0} slow queries above {db?.threshold_ms ?? 200} ms</small>
        </div>
        <div className="metric-card">
          <span>CPU and syscalls</span>
          <strong>{metrics?.cpu?.process_percent != null ? `${String(metrics.cpu.process_percent)}% CPU` : 'Fallback active'}</strong>
          <small>{Object.keys(metrics?.syscalls ?? {}).length} syscall series</small>
        </div>
        <div className="metric-card">
          <span>TCP network</span>
          <strong>{network?.retransmits ?? 0} retransmits</strong>
          <small>{network?.resets ?? 0} resets · {network?.connection_failures ?? 0} failures</small>
        </div>
        <div className="metric-card">
          <span>App latency p95</span>
          <strong>{metrics ? `${metrics.app_latency.p95_ms.toFixed(1)} ms` : 'Waiting...'}</strong>
          <small>{metrics?.app_latency.samples ?? 0} request samples</small>
        </div>
      </div>

      <div className="observability-actions">
        <button type="button" className="primary" onClick={() => void runLoad()} disabled={loading || !products.length}>
          {loading ? 'Running load...' : 'Run load + watch metrics'}
        </button>
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
    </motion.section>
  );
}
