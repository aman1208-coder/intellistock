import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { BankerRequest, BankerResponse, PriorityJob, Product, Warehouse } from './api';
import { ApiError, fetchJson } from './api';
import Chatbot from './Chatbot';
import Insights from './Insights';
import { ForecastPanel, TransactionsPanel } from './LiveDataPanels';
import ProductsTable from './ProductsTable';

type NavItem = [string, string];

type QueueKind = 'inventory_check' | 'routine_audit';

const navItems: NavItem[] = [
  ['overview', 'Overview'],
  ['forecast', 'Demand forecast'],
  ['sync', 'Live transactions'],
  ['banker', "Banker's lab"],
  ['scheduler', 'Priority queue'],
];

type ToastKind = 'success' | 'warning' | 'danger' | 'info';

type ToastItem = {
  id: number;
  title: string;
  detail: string;
  kind: ToastKind;
};

type BankerResult = {
  status: 'approved' | 'rejected';
  detail: string;
  safe_sequence?: string[];
};

function BankerLab({
  warehouses,
  autoUnsafeKey,
  onWarehousesReload,
  onToast,
}: {
  warehouses: Warehouse[];
  autoUnsafeKey?: number;
  onWarehousesReload: () => Promise<Warehouse[]>;
  onToast?: (title: string, detail: string, kind: ToastKind) => void;
}) {
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<number>(warehouses[0]?.id ?? 0);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BankerResult | null>(null);
  const lastAutoUnsafeKey = useRef(0);

  useEffect(() => {
    if (warehouses.length > 0 && !warehouses.some((warehouse) => warehouse.id === selectedWarehouseId)) {
      setSelectedWarehouseId(warehouses[0].id);
    }
  }, [selectedWarehouseId, warehouses]);

  useEffect(() => {
    if (!autoUnsafeKey || lastAutoUnsafeKey.current === autoUnsafeKey) {
      return;
    }

    if (!warehouses.length) {
      return;
    }

    lastAutoUnsafeKey.current = autoUnsafeKey;
    setSelectedWarehouseId(warehouses[0].id);
    void runAllocationCheck({ unsafe: true, warehouseId: warehouses[0].id });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoUnsafeKey, warehouses]);

  const warehouse = warehouses.find((item) => item.id === selectedWarehouseId) ?? warehouses[0];

  const runAllocationCheck = async (options?: { unsafe?: boolean; warehouseId?: number }) => {
    const targetWarehouse = warehouses.find((item) => item.id === options?.warehouseId) ?? warehouse;
    if (!targetWarehouse) {
      return;
    }

    const unsafe = Boolean(options?.unsafe);
    setLoading(true);
    setResult(null);

    try {
      await fetchJson(`/api/inventory/reset-warehouse-state/${targetWarehouse.id}`, { method: 'POST' });
      const latest = await onWarehousesReload();
      const current = latest.find((item) => item.id === targetWarehouse.id) ?? targetWarehouse;
      const payload: BankerRequest = {
        warehouse_id: current.id,
        process_id: `process-${Date.now()}`,
        total_resources: { capacity: current.total_capacity, dock_bays: 12, equipment: 9 },
        available_resources: { capacity: current.available_capacity, dock_bays: 5, equipment: 4 },
        max_claim: {
          capacity: Math.min(current.total_capacity, 30),
          dock_bays: unsafe ? 7 : 5,
          equipment: unsafe ? 6 : 4,
        },
        request_vector: { capacity: 4, dock_bays: 2, equipment: 2 },
      };
      const data = await fetchJson<BankerResponse>('/api/inventory/allocate-warehouse-slot', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      setResult({
        status: 'approved',
        detail: 'Request approved with a safe execution order.',
        safe_sequence: data.safe_sequence,
      });
      try {
        await onWarehousesReload();
      } catch {
        onToast?.('Capacity refresh failed', 'Allocation succeeded, but warehouse capacity could not be refreshed.', 'warning');
      }
      onToast?.(
        'Allocation approved',
        'Safe sequence verified for the next allocation.',
        'success',
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to reach the API service.';
      const detail = error instanceof ApiError && error.payload && typeof error.payload === 'object' && 'detail' in error.payload
        ? error.payload.detail
        : undefined;
      const responseDetail = detail && typeof detail === 'object' && !Array.isArray(detail) ? detail : undefined;
      const safeSequence = responseDetail && 'safe_sequence' in responseDetail && Array.isArray(responseDetail.safe_sequence)
        ? responseDetail.safe_sequence as string[]
        : undefined;
      const serverMessage = responseDetail && 'message' in responseDetail && typeof responseDetail.message === 'string'
        ? responseDetail.message
        : message;
      setResult({
        status: 'rejected',
        detail: serverMessage,
        safe_sequence: safeSequence,
      });
      onToast?.(error instanceof ApiError ? 'Banker check rejected' : 'Banker check failed', serverMessage, 'danger');
    } finally {
      setLoading(false);
    }
  };

  const resetDemoState = async () => {
    if (!warehouse) {
      return;
    }
    setLoading(true);
    try {
      await fetchJson(`/api/inventory/reset-warehouse-state/${warehouse.id}`, { method: 'POST' });
      await onWarehousesReload();
      setResult(null);
      onToast?.('Demo state reset', `${warehouse.name} resources are ready for another check.`, 'success');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to reset warehouse resources.';
      setResult({ status: 'rejected', detail: message });
      onToast?.('Reset failed', message, 'danger');
    } finally {
      setLoading(false);
    }
  };


  return (
    <motion.section
      className="glass-panel"
      id="banker"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">Banker&apos;s algorithm</span>
          <h2>Resource safety lab</h2>
        </div>
      </div>

      <div className="banker-controls">
        {warehouse ? (
          <label>
            Warehouse
            <select value={warehouse.id} onChange={(event) => setSelectedWarehouseId(Number(event.target.value))}>
              {warehouses.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        ) : <span>No warehouse data loaded.</span>}

        <div className="button-row">
          <button type="button" className="primary" onClick={() => void runAllocationCheck()} disabled={loading || !warehouse}>
            {loading ? 'Testing safety...' : 'Run Bankers check'}
          </button>
          <button type="button" onClick={() => void resetDemoState()} disabled={loading || !warehouse}>
            Reset demo state
          </button>
        </div>
      </div>
      <div className="banker-caption">Each run starts from a fresh resource state.</div>

      <div className="resource-summary">
        <div>
          <span>Capacity</span>
          <strong>{warehouse ? `${warehouse.available_capacity}/${warehouse.total_capacity}` : '—'}</strong>
        </div>
        <div>
          <span>Dock bays</span>
          <strong>5 / 12</strong>
        </div>
        <div>
          <span>Equipment</span>
          <strong>4 / 9</strong>
        </div>
      </div>

      {result ? (
        <motion.div
          className={`result-banner ${result.status === 'approved' ? 'success' : 'danger'}`}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 350, damping: 25 }}
        >
          <span className="result-label">{result.status === 'approved' ? 'Safe sequence verified' : 'Deadlock risk warning'}</span>
          <p>{result.detail ?? 'Allocation state updated.'}</p>
          {result.safe_sequence ? (
            <motion.strong
              initial={{ opacity: 0, scale: 0.97, x: -8 }}
              animate={{ opacity: 1, scale: 1, x: 0 }}
              transition={{ type: 'spring', stiffness: 320, damping: 26 }}
              style={{ willChange: 'transform, opacity' }}
            >
              {result.safe_sequence.length ? result.safe_sequence.join(' → ') : 'Safe sequence: none'}
            </motion.strong>
          ) : null}
        </motion.div>
      ) : (
        <motion.div
          className="result-banner idle"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 350, damping: 25 }}
        >
          <span className="result-label">Waiting for approval</span>
          <p>Run a request to validate whether the next allocation preserves a safe state.</p>
        </motion.div>
      )}
    </motion.section>
  );
}

function ConcurrencyLab({
  products,
  initialMode = 'safe',
  flashKey,
  onModeChange,
  onSaleComplete,
  onToast,
}: {
  products: Product[];
  initialMode?: 'safe' | 'unsafe';
  flashKey?: number;
  onModeChange?: (mode: 'safe' | 'unsafe') => void;
  onSaleComplete?: () => Promise<void>;
  onToast?: (title: string, detail: string, kind: ToastKind) => void;
}) {
  const [mode, setMode] = useState<'safe' | 'unsafe'>(initialMode);
  const [selectedProductId, setSelectedProductId] = useState(0);
  const [quantity, setQuantity] = useState('1');
  const [requests, setRequests] = useState<{ id: number; status: number; latency: number; error?: string }[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState('');
  const lastFlashKey = useRef(0);
  const runBatchRef = useRef<(nextMode: 'safe' | 'unsafe') => Promise<void>>(async () => undefined);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    if (products.length && !products.some((product) => product.id === selectedProductId)) {
      const preferred = products.find((product) => product.stock_quantity > 0 && product.stock_quantity <= product.reorder_threshold);
      setSelectedProductId(preferred?.id ?? products.find((product) => product.stock_quantity > 0)?.id ?? products[0].id);
    }
  }, [products, selectedProductId]);

  const runBatch = async (nextMode: 'safe' | 'unsafe') => {
    if (isRunning) {
      return;
    }
    const saleQuantity = Number(quantity);
    if (!selectedProductId || !Number.isInteger(saleQuantity) || saleQuantity < 1) {
      setError('Select a product and enter a positive whole-number quantity.');
      return;
    }

    setIsRunning(true);
    setMode(nextMode);
    onModeChange?.(nextMode);
    setError('');
    const results = await Promise.all(
      Array.from({ length: 8 }, async (_, index) => {
        const startedAt = performance.now();
        try {
          await fetchJson(`/api/inventory/transact-${nextMode}`, {
            method: 'POST',
            body: JSON.stringify({ product_id: selectedProductId, quantity: saleQuantity }),
          });
          return { id: index + 1, status: 201, latency: performance.now() - startedAt };
        } catch (requestError) {
          return {
            id: index + 1,
            status: requestError instanceof ApiError ? requestError.status : 0,
            latency: performance.now() - startedAt,
            error: requestError instanceof Error ? requestError.message : 'Request failed.',
          };
        }
      }),
    );
    setRequests(results);
    setIsRunning(false);
    const accepted = results.filter((result) => result.status === 201).length;
    onToast?.(
      nextMode === 'safe' ? 'Safe sale batch complete' : 'Unsafe sale batch complete',
      `${accepted} of 8 sales committed; each row shows its HTTP status and measured latency.`,
      accepted ? 'success' : 'warning',
    );
    if (accepted) {
      try {
        await onSaleComplete?.();
      } catch {
        setError('Sales completed, but inventory refresh failed.');
      }
    }
  };
  runBatchRef.current = runBatch;

  useEffect(() => {
    if (!flashKey || lastFlashKey.current === flashKey) {
      return;
    }
    lastFlashKey.current = flashKey;
    void runBatchRef.current('safe');
  }, [flashKey]);

  const maxLatency = Math.max(...requests.map((request) => request.latency), 1);

  return (
    <motion.section
      className="glass-panel"
      id="scheduler"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">Concurrency lab</span>
          <h2>8-thread waterfall</h2>
        </div>
      </div>

      <div className="mode-toggle">
        <button
          type="button"
          className={mode === 'safe' ? 'primary' : ''}
          disabled={isRunning || !products.length}
          onClick={() => void runBatch('safe')}
        >
          {isRunning && mode === 'safe' ? 'Running safe batch…' : 'Safe mode'}
        </button>
        <button
          type="button"
          className={mode === 'unsafe' ? 'primary' : ''}
          disabled={isRunning || !products.length}
          onClick={() => void runBatch('unsafe')}
        >
          {isRunning && mode === 'unsafe' ? 'Running unsafe batch…' : 'Unsafe mode'}
        </button>
      </div>

      <div className="scheduler-controls concurrency-controls">
        <label>
          Product
          <select value={selectedProductId} onChange={(event) => setSelectedProductId(Number(event.target.value))} disabled={isRunning}>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name} · {product.stock_quantity} in stock
              </option>
            ))}
          </select>
        </label>
        <label>
          Units per request
          <input type="number" min="1" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} disabled={isRunning} />
        </label>
      </div>
      <p className="banker-caption">SQLite ignores row-level SELECT FOR UPDATE, so the safe/unsafe race comparison is meaningful only on PostgreSQL.</p>
      {error && <p className="api-error-inline" role="alert">{error}</p>}

      <div className="timeline-wrap">
        {requests.map((request) => (
          <div
            key={request.id}
            className="timeline-row"
          >
            <span className="thread-label">Request {String(request.id).padStart(2, '0')}</span>
            <div className="timeline-track">
              <div className={`timeline-bar ${request.status === 201 ? 'ok' : 'protected'}`} style={{ width: `${Math.max(5, request.latency / maxLatency * 100)}%` }} />
            </div>
            <span className="latency-pill">{request.latency.toFixed(0)} ms</span>
            <span className={`status-badge ${request.status === 201 ? 'ok' : 'protected'}`}>{request.status || 'Network error'}</span>
          </div>
        ))}
      </div>
    </motion.section>
  );
}

function PrioritySchedulerPanel({
  products,
  onQueueCountChange,
  demoQueueKey,
  onToast,
}: {
  products: Product[];
  onQueueCountChange?: (count: number) => void;
  demoQueueKey?: number;
  onToast?: (title: string, detail: string, kind: ToastKind) => void;
}) {
  const [jobs, setJobs] = useState<PriorityJob[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<number>(products[0]?.id ?? 0);
  const [message, setMessage] = useState('Loading priority queue…');
  const lastDemoQueueKey = useRef(0);

  useEffect(() => {
    if (products.length > 0 && !products.some((product) => product.id === selectedProductId)) {
      setSelectedProductId(products[0].id);
    }
  }, [selectedProductId, products]);

  useEffect(() => {
    const loadJobs = async () => {
      try {
        const data = await fetchJson<PriorityJob[]>('/api/inventory/priority-queue');
        setJobs(data);
        onQueueCountChange?.(data.length);
        setMessage(data.length ? 'Jobs are ordered by live backend priority.' : 'No jobs are currently queued.');
      } catch (error) {
        setJobs([]);
        onQueueCountChange?.(0);
        setMessage(`Unable to load the priority queue: ${error instanceof Error ? error.message : 'API unavailable.'}`);
      }
    };

    void loadJobs();
  }, [onQueueCountChange]);

  const sortedJobs = useMemo(
    () => [...jobs].sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id)),
    [jobs],
  );

  useEffect(() => {
    onQueueCountChange?.(sortedJobs.length);
  }, [onQueueCountChange, sortedJobs.length]);

  useEffect(() => {
    if (!demoQueueKey || lastDemoQueueKey.current === demoQueueKey || !selectedProductId) {
      return;
    }
    lastDemoQueueKey.current = demoQueueKey;

    const runDemo = async () => {
      try {
        await Promise.all([
          fetchJson('/api/inventory/queue-job', { method: 'POST', body: JSON.stringify({ job_type: 'routine_audit' }) }),
          fetchJson('/api/inventory/queue-job', { method: 'POST', body: JSON.stringify({ job_type: 'routine_audit' }) }),
          fetchJson('/api/inventory/queue-job', { method: 'POST', body: JSON.stringify({ job_type: 'inventory_check', product_id: selectedProductId }) }),
        ]);
        const updated = await fetchJson<PriorityJob[]>('/api/inventory/priority-queue');
        setJobs(updated);
        onQueueCountChange?.(updated.length);
        setMessage('Emergency stockout was added to the live priority queue.');
        onToast?.('Emergency stockout queued', 'The backend queued two audits and one urgent inventory check.', 'success');
      } catch (error) {
        setMessage(`Queue demo failed: ${error instanceof Error ? error.message : 'API unavailable.'}`);
        onToast?.('Queue demo failed', error instanceof Error ? error.message : 'API unavailable.', 'danger');
      }
    };
    void runDemo();
  }, [demoQueueKey, onQueueCountChange, onToast, selectedProductId]);

  const queueJob = async (kind: QueueKind) => {
    const productId = selectedProductId || products[0]?.id;
    if (kind === 'inventory_check' && !productId) {
      setMessage('Select a product before queuing an inventory check.');
      return;
    }
    const payload =
      kind === 'inventory_check'
        ? { job_type: 'inventory_check', product_id: productId }
        : { job_type: 'routine_audit' };

    try {
      await fetchJson<PriorityJob>('/api/inventory/queue-job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const nextJobs = await fetchJson<PriorityJob[]>('/api/inventory/priority-queue');
      setJobs(nextJobs);
      onQueueCountChange?.(nextJobs.length);
      setMessage(
        kind === 'inventory_check'
          ? 'Emergency stockout queued and promoted to the head of the scheduler.'
          : 'Routine audit queued behind urgent replenishment tasks.',
      );
      onToast?.(
        kind === 'inventory_check' ? 'Emergency job dispatched' : 'Routine audit queued',
        kind === 'inventory_check'
          ? 'Critical stockout job was pushed to the front of the scheduler.'
          : 'A routine audit was queued behind urgent replenishment work.',
        kind === 'inventory_check' ? 'warning' : 'info',
      );
    } catch (error) {
      setMessage(`Unable to queue job: ${error instanceof Error ? error.message : 'API unavailable.'}`);
      onToast?.('Queue job failed', error instanceof Error ? error.message : 'API unavailable.', 'danger');
    }
  };

  return (
    <motion.section
      className="glass-panel"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">Priority scheduler</span>
          <h2>Job queue</h2>
        </div>
      </div>

      <div className="scheduler-controls">
        <label>
          Product
          <select value={selectedProductId} onChange={(event) => setSelectedProductId(Number(event.target.value))}>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </select>
        </label>

        <div className="button-row">
          <button type="button" className="primary" onClick={() => void queueJob('inventory_check')} disabled={!products.length}>
            Queue urgent stockout
          </button>
          <button type="button" onClick={() => void queueJob('routine_audit')}>
            Queue routine audit
          </button>
        </div>
      </div>

      <div className="queue-banner">{message}</div>

      <AnimatePresence mode="popLayout">
        <ul className="queue-list">
          {sortedJobs.map((job) => (
            <motion.li
              key={job.id}
              layout="position"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ type: 'spring', stiffness: 350, damping: 28 }}
              className="queue-item"
              style={{ willChange: 'transform, opacity' }}
            >
              <div>
                <span className={`priority-badge priority-${job.priority}`}>
                  Priority {job.priority}
                </span>
                <strong>
                  {job.priority === 1
                    ? 'Urgent Stockout'
                    : job.priority === 2
                      ? 'High Low-Stock'
                      : 'Routine Audit'}
                </strong>
              </div>
              <small>
                {job.job_type === 'inventory_check' ? 'Inventory check' : 'Routine audit'}
                {job.product_id ? ` · SKU ${job.product_id}` : ''}
              </small>
            </motion.li>
          ))}
        </ul>
      </AnimatePresence>
    </motion.section>
  );
}

export default function Dashboard({ onLogout, username }: { onLogout: () => void; username: string }) {
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [priorityQueueCount, setPriorityQueueCount] = useState<number>(0);
  const [apiError, setApiError] = useState('');
  const [demoMode, setDemoMode] = useState<'safe' | 'unsafe'>('safe');
  const [flashKey, setFlashKey] = useState(0);
  const [bankerAutoKey, setBankerAutoKey] = useState(0);
  const [queueDemoKey, setQueueDemoKey] = useState(0);
  const [transactionRefreshKey, setTransactionRefreshKey] = useState(0);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const refreshWarehouses = async (): Promise<Warehouse[]> => {
    const warehouseList = await fetchJson<Warehouse[]>('/api/warehouses');
    setWarehouses(warehouseList);
    return warehouseList;
  };

  const refreshInventory = async () => {
    try {
      const [warehouseList, productList] = await Promise.all([
        fetchJson<Warehouse[]>('/api/warehouses'),
        fetchJson<Product[]>('/api/products'),
      ]);
      setWarehouses(warehouseList);
      setProducts(productList);
      setApiError('');
    } catch (error) {
      setWarehouses([]);
      setProducts([]);
      setApiError(`Unable to load inventory: ${error instanceof Error ? error.message : 'API unavailable.'}`);
    }
  };

  const refreshAfterInventoryChange = async () => {
    await refreshInventory();
    setTransactionRefreshKey((key) => key + 1);
  };

  // Stable identity: child effects list onToast as a dependency, so a new function each render caused an endless toast/API loop.
  const pushToast = useCallback((title: string, detail: string, kind: ToastKind = 'info') => {
    const toast = { id: Date.now() + Math.random(), title, detail, kind };
    setToasts((current) => [...current, toast].slice(-4));
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== toast.id));
    }, 3500);
  }, []);

  useEffect(() => {
    void refreshInventory();
  }, []);

  const handleDemoOne = () => {
    setDemoMode('safe');
    setFlashKey((current) => current + 1);
  };

  const handleDemoTwo = () => {
    setDemoMode('unsafe');
    setBankerAutoKey((current) => current + 1);
  };

  const handleDemoThree = () => {
    setQueueDemoKey((current) => current + 1);
  };

  return (
    <motion.div
      className="dashboard-shell"
      initial={{ opacity: 1, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      transition={{ duration: 0.28 }}
    >
      <motion.header
        className="topbar glass-panel"
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <div className="brand-wrap">
          <div className="brand-mark">I</div>
          <div>
            <span className="brand-tag">IntelliStock</span>
            <strong>Interactive OS control center</strong>
          </div>
        </div>

        <div className="header-actions">
          <motion.div
            className="user-pill"
            whileHover={{ scale: 1.02 }}
            transition={{ type: 'spring', stiffness: 300, damping: 18 }}
          >
            <span className="user-indicator" aria-label="Active user" />
            <span>👤 {username}</span>
          </motion.div>

          <button type="button" className="logout-button" onClick={onLogout}>
            Sign out
          </button>
        </div>

        <nav className="nav" aria-label="Primary navigation">
          {navItems.map(([key, label]) => (
            <a key={key} href={`#${key}`}>
              {label}
            </a>
          ))}
        </nav>

      </motion.header>

      {apiError && <div className="api-error-banner" role="alert">{apiError}</div>}

      <motion.div className="system-hud glass-panel" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <div className="hud-row">
          <span className="hud-pill">● DBMS Concurrency: Row-Level Locking (with_for_update)</span>
          <span className="hud-pill">● OS Daemon: Banker's Deadlock &amp; Priority Queue Active</span>
          <span className="hud-pill">● AI Engine: 14-Day Demand Forecaster</span>
        </div>
        <div className="hud-right">
          <motion.span
            className="live-queue-beacon"
            animate={{ scale: [1, 1.25, 1], opacity: [0.6, 1, 0.6] }}
            transition={{ repeat: Infinity, duration: 2 }}
          />
          <span className="hud-live-badge">Live queue: {priorityQueueCount}</span>
        </div>
      </motion.div>

      <motion.section className="viva-demo-bar glass-panel" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <div className="section-heading demo-heading">
          <div>
            <span className="eyebrow">Viva demo mode</span>
            <h2>Scenario playback</h2>
          </div>
        </div>
        <div className="demo-actions">
          <motion.button
            type="button"
            className="demo-button"
            onClick={handleDemoOne}
            whileHover={{ scale: 1.025, rotateX: -2, rotateY: 3 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
            style={{ perspective: 1000, transformStyle: 'preserve-3d' }}
          >
            Demo 1: Flash Sale Race Condition
          </motion.button>
          <motion.button
            type="button"
            className="demo-button"
            onClick={handleDemoTwo}
            whileHover={{ scale: 1.025, rotateX: -2, rotateY: 3 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
            style={{ perspective: 1000, transformStyle: 'preserve-3d' }}
          >
            Demo 2: Warehouse Deadlock Risk
          </motion.button>
          <motion.button
            type="button"
            className="demo-button"
            onClick={handleDemoThree}
            whileHover={{ scale: 1.025, rotateX: -2, rotateY: 3 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
            style={{ perspective: 1000, transformStyle: 'preserve-3d' }}
          >
            Demo 3: Emergency Stockout Preemption
          </motion.button>
        </div>
      </motion.section>

      <Insights products={products} warehouses={warehouses} />
      <ForecastPanel products={products} />
      <TransactionsPanel products={products} refreshKey={transactionRefreshKey} />
      <BankerLab warehouses={warehouses} autoUnsafeKey={bankerAutoKey} onWarehousesReload={refreshWarehouses} onToast={pushToast} />
      <ConcurrencyLab products={products} initialMode={demoMode} flashKey={flashKey} onModeChange={setDemoMode} onSaleComplete={refreshAfterInventoryChange} onToast={pushToast} />
      <PrioritySchedulerPanel
        products={products}
        onQueueCountChange={setPriorityQueueCount}
        demoQueueKey={queueDemoKey}
        onToast={pushToast}
      />
      <ProductsTable
        products={products}
        warehouses={warehouses}
        onRefresh={refreshAfterInventoryChange}
        onToast={pushToast}
      />
      <Chatbot products={products} />

      <AnimatePresence>
        {toasts.length > 0 ? (
          <motion.div className="toast-stack" initial={false}>
            {toasts.map((toast) => (
              <motion.div
                key={toast.id}
                className={`toast-item ${toast.kind}`}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
              >
                <strong>{toast.title}</strong>
                <span>{toast.detail}</span>
              </motion.div>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  );
}
