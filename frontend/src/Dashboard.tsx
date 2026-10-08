import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import type { BankerRequest, BankerResponse, PriorityJob, Product, Warehouse } from './api';
import { API_BASE_URL, fetchJson } from './api';
import Chatbot from './Chatbot';
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

const fallbackWarehouses: Warehouse[] = [
  { id: 1, name: 'North Hub', location: 'Chicago', total_capacity: 120, available_capacity: 80 },
  { id: 2, name: 'East Crossdock', location: 'Boston', total_capacity: 140, available_capacity: 95 },
  { id: 3, name: 'South Fulfillment', location: 'Atlanta', total_capacity: 110, available_capacity: 65 },
];

const fallbackProducts: Product[] = [
  { id: 101, name: 'Battery Pack', stock_quantity: 0, reorder_threshold: 12, warehouse_id: 1, category: 'Power' },
  { id: 102, name: 'Safety Gloves', stock_quantity: 8, reorder_threshold: 12, warehouse_id: 2, category: 'PPE' },
  { id: 103, name: 'Label Printer', stock_quantity: 16, reorder_threshold: 8, warehouse_id: 3, category: 'Office' },
];

const fallbackPriorityQueue: PriorityJob[] = [
  { id: 'job-urgent', job_type: 'inventory_check', priority: 1, product_id: 101 },
  { id: 'job-high', job_type: 'inventory_check', priority: 2, product_id: 102 },
  { id: 'job-routine', job_type: 'routine_audit', priority: 3 },
];

function Lab() {
  return (
    <motion.section
      className="glass-panel lab-panel"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">Operations lab</span>
          <h2>Warehouse orchestration</h2>
        </div>
      </div>
      <div className="overview-grid">
        {[
          { label: 'Available slots', value: '87', detail: 'Across active warehouses', accent: true },
          { label: 'Routine checks', value: '12', detail: 'Queued this cycle' },
          { label: 'Deadlock risk', value: 'Low', detail: 'Verified safe state' },
        ].map((metric) => (
          <motion.div
            key={metric.label}
            className={`metric-card ${metric.accent ? 'accent' : ''}`}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.detail}</small>
          </motion.div>
        ))}
      </div>
    </motion.section>
  );
}

function BankerLab({ warehouses }: { warehouses: Warehouse[] }) {
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<number>(warehouses[0]?.id ?? fallbackWarehouses[0].id);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BankerResponse | null>(null);

  useEffect(() => {
    if (warehouses.length > 0 && !warehouses.some((warehouse) => warehouse.id === selectedWarehouseId)) {
      setSelectedWarehouseId(warehouses[0].id);
    }
  }, [selectedWarehouseId, warehouses]);

  const warehouse = warehouses.find((item) => item.id === selectedWarehouseId) ?? warehouses[0] ?? fallbackWarehouses[0];

  const runAllocationCheck = async () => {
    if (!warehouse) {
      return;
    }

    const payload: BankerRequest = {
      warehouse_id: warehouse.id,
      process_id: `process-${Date.now()}`,
      total_resources: {
        capacity: warehouse.total_capacity,
        dock_bays: 12,
        equipment: 9,
      },
      available_resources: {
        capacity: warehouse.available_capacity,
        dock_bays: 5,
        equipment: 4,
      },
      max_claim: {
        capacity: Math.min(warehouse.total_capacity, 30),
        dock_bays: 7,
        equipment: 6,
      },
      request_vector: {
        capacity: 4,
        dock_bays: 2,
        equipment: 2,
      },
    };

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/inventory/allocate-warehouse-slot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;

      if (!response.ok) {
        const detail = data?.detail;
        const detailMessage =
          typeof detail === 'string'
            ? detail
            : detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string'
              ? detail.message
              : 'Deadlock risk detected — request would leave the warehouse unsafe.';
        const safeSequence =
          detail && typeof detail === 'object' && 'safe_sequence' in detail && Array.isArray(detail.safe_sequence)
            ? detail.safe_sequence
            : Array.isArray(data.safe_sequence)
              ? (data.safe_sequence as string[])
              : undefined;

        setResult({
          status: 'rejected',
          detail: detailMessage,
          safe_sequence: safeSequence,
        });
        return;
      }

      setResult({
        status: 'approved',
        detail: 'Request approved with a safe execution order.',
        safe_sequence: Array.isArray(data.safe_sequence) ? (data.safe_sequence as string[]) : undefined,
      });
    } catch (error) {
      setResult({
        status: 'rejected',
        detail: `Offline fallback: ${error instanceof Error ? error.message : 'Unable to reach the API service.'}`,
      });
    } finally {
      setLoading(false);
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
          <span className="eyebrow">Banker&apos;s algorithm</span>
          <h2>Resource safety lab</h2>
        </div>
      </div>

      <div className="banker-controls">
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

        <button type="button" onClick={runAllocationCheck} disabled={loading}>
          {loading ? 'Testing safety...' : 'Run Bankers check'}
        </button>
      </div>

      <div className="resource-summary">
        <div>
          <span>Capacity</span>
          <strong>{warehouse.available_capacity}/{warehouse.total_capacity}</strong>
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
          {result.safe_sequence && result.safe_sequence.length > 0 ? (
            <motion.strong
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.08, duration: 0.2 }}
            >
              {result.safe_sequence.join(' → ')}
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

function ConcurrencyLab() {
  const [mode, setMode] = useState<'safe' | 'unsafe'>('safe');

  const threads = Array.from({ length: 8 }, (_, index) => {
    const safeBusy = 32 + index * 10;
    const unsafeBusy = 26 + index * 14;

    if (mode === 'safe') {
      return {
        id: `thread-${index + 1}`,
        label: `Thread ${String(index + 1).padStart(2, '0')}`,
        width: index < 5 ? 62 + index * 6 : 42 + index * 4,
        latency: 120 + index * 45,
        status: index < 5 ? '[LOCK ACQUIRED: 200 OK]' : '[LOCK PROTECTED: 409]',
        statusClass: index < 5 ? 'ok' : 'protected',
      };
    }

    return {
      id: `race-${index + 1}`,
      label: `Thread ${String(index + 1).padStart(2, '0')}`,
      width: unsafeBusy,
      latency: 180 + index * 50,
      status: '[RACE COLLISION: 409]',
      statusClass: 'race',
    };
  });

  return (
    <motion.section
      className="glass-panel"
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
        <button type="button" className={mode === 'safe' ? 'primary' : ''} onClick={() => setMode('safe')}>
          Safe mode
        </button>
        <button type="button" className={mode === 'unsafe' ? 'primary' : ''} onClick={() => setMode('unsafe')}>
          Unsafe mode
        </button>
      </div>

      <div className="timeline-wrap">
        {threads.map((thread, index) => (
          <div key={thread.id} className="timeline-row">
            <span className="thread-label">{thread.label}</span>
            <div className="timeline-track">
              <motion.div
                className={`timeline-bar ${thread.statusClass}`}
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(thread.width, 100)}%` }}
                transition={{ duration: 0.7, delay: index * 0.06 }}
              />
            </div>
            <span className="latency-pill">{thread.latency} ms</span>
            <span className={`status-badge ${thread.statusClass}`}>{thread.status}</span>
          </div>
        ))}
      </div>
    </motion.section>
  );
}

function PrioritySchedulerPanel({ products }: { products: Product[] }) {
  const [jobs, setJobs] = useState<PriorityJob[]>(fallbackPriorityQueue);
  const [selectedProductId, setSelectedProductId] = useState<number>(products[0]?.id ?? fallbackProducts[0].id);
  const [message, setMessage] = useState('Emergency stockouts are prioritized ahead of routine inventory tasks.');

  useEffect(() => {
    if (products.length > 0 && !products.some((product) => product.id === selectedProductId)) {
      setSelectedProductId(products[0].id);
    }
  }, [selectedProductId, products]);

  useEffect(() => {
    const loadJobs = async () => {
      try {
        const data = await fetchJson<PriorityJob[]>('/api/inventory/priority-queue');
        if (data.length > 0) {
          setJobs(data);
        }
      } catch {
        setJobs(fallbackPriorityQueue);
      }
    };

    void loadJobs();
  }, []);

  const sortedJobs = useMemo(
    () => [...jobs].sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id)),
    [jobs],
  );

  const queueJob = async (kind: QueueKind) => {
    const productId = selectedProductId ?? products[0]?.id ?? fallbackProducts[0].id;
    const payload =
      kind === 'inventory_check'
        ? { job_type: 'inventory_check', product_id: productId }
        : { job_type: 'routine_audit' };

    const offlineJob: PriorityJob = {
      id: `${kind}-${Date.now()}`,
      job_type: kind,
      priority: kind === 'inventory_check' ? 1 : 3,
      product_id: kind === 'inventory_check' ? productId : undefined,
    };

    try {
      const created = await fetchJson<PriorityJob>('/api/inventory/queue-job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      setJobs((current) => [created, ...current]);
      setMessage(
        kind === 'inventory_check'
          ? 'Emergency stockout queued and promoted to the head of the scheduler.'
          : 'Routine audit queued behind urgent replenishment tasks.',
      );
    } catch {
      setJobs((current) => [offlineJob, ...current]);
      setMessage(
        kind === 'inventory_check'
          ? 'Offline demo queue: emergency stockout promoted ahead of routine work.'
          : 'Offline demo queue: routine audit sits behind urgent replenishment work.',
      );
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
            {products.length > 0 ? (
              products.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name}
                </option>
              ))
            ) : (
              fallbackProducts.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name}
                </option>
              ))
            )}
          </select>
        </label>

        <div className="button-row">
          <button type="button" className="primary" onClick={() => void queueJob('inventory_check')}>
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
              layout
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              className="queue-item"
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

export default function Dashboard() {
  const [warehouses, setWarehouses] = useState<Warehouse[]>(fallbackWarehouses);
  const [products, setProducts] = useState<Product[]>(fallbackProducts);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [warehouseList, productList] = await Promise.all([
          fetchJson<Warehouse[]>('/api/warehouses'),
          fetchJson<Product[]>('/api/products'),
        ]);

        if (warehouseList.length > 0) {
          setWarehouses(warehouseList);
        }
        if (productList.length > 0) {
          setProducts(productList);
        }
      } catch {
        setWarehouses(fallbackWarehouses);
        setProducts(fallbackProducts);
      }
    };

    void loadData();
  }, []);

  return (
    <motion.div
      className="dashboard-shell"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
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

        <nav className="nav" aria-label="Primary navigation">
          {navItems.map(([key, label]) => (
            <a key={key} href={`#${key}`}>
              {label}
            </a>
          ))}
        </nav>
      </motion.header>

      <Lab />
      <BankerLab warehouses={warehouses} />
      <ConcurrencyLab />
      <PrioritySchedulerPanel products={products} />
      <ProductsTable products={products} />
      <Chatbot products={products} />
    </motion.div>
  );
}
