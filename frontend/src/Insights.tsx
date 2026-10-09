import type { Product, Warehouse } from './api';

function getCategoryPalette(index: number) {
  const palette = ['#a78bfa', '#c084fc', '#f472b6', '#60a5fa', '#34d399', '#fbbf24'];
  return palette[index % palette.length];
}

export default function Insights({ products, warehouses }: { products: Product[]; warehouses: Warehouse[] }) {
  const totals = products.reduce(
    (accumulator, product) => {
      accumulator.units += product.stock_quantity;
      if (product.stock_quantity <= (product.reorder_threshold ?? 0)) {
        accumulator.lowStock += 1;
      }
      accumulator.categoryMap[(product.category ?? 'General').toLowerCase()] =
        (accumulator.categoryMap[(product.category ?? 'General').toLowerCase()] ?? 0) + 1;
      return accumulator;
    },
    {
      units: 0,
      lowStock: 0,
      categoryMap: {} as Record<string, number>,
    },
  );

  const categoryEntries = Object.entries(totals.categoryMap);
  const totalCategories = categoryEntries.length || 1;
  const donutGradient = `conic-gradient(${categoryEntries
    .map(([category, count], index) => `${getCategoryPalette(index)} ${(index / totalCategories) * 100}% ${((index + 1) / totalCategories) * 100}%`)
    .join(', ') || '#a78bfa 0% 100%'})`;

  const capacityEntries = warehouses.map((warehouse) => ({
    ...warehouse,
    utilization: warehouse.total_capacity === 0 ? 0 : (warehouse.total_capacity - warehouse.available_capacity) / warehouse.total_capacity,
  }));

  return (
    <section className="glass-panel insights-panel" id="overview">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Operational view</span>
          <h2>Inventory insights</h2>
        </div>
      </div>

      <div className="insights-grid">
        <div className="kpi-grid">
          <div className="kpi-card subtle">
            <span>Total units</span>
            <strong>{totals.units}</strong>
            <small>Across all active SKUs</small>
          </div>
          <div className="kpi-card highlight">
            <span>Low stock</span>
            <strong>{totals.lowStock}</strong>
            <small>Products below threshold</small>
          </div>
          <div className="kpi-card">
            <span>Warehouses</span>
            <strong>{warehouses.length}</strong>
            <small>Live fulfillment nodes</small>
          </div>
          <div className="kpi-card">
            <span>Categories</span>
            <strong>{totalCategories}</strong>
            <small>Inventory segments</small>
          </div>
        </div>

        <div className="donut-card">
          <div className="donut-chart" style={{ background: donutGradient }}>
            <div className="donut-core">
              <strong>{products.length}</strong>
              <span>Products</span>
            </div>
          </div>
          <div className="legend">
            {categoryEntries.map(([category, count], index) => (
              <div key={category} className="legend-item">
                <span className="swatch" style={{ background: getCategoryPalette(index) }} />
                <span>{category}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="capacity-card">
          <div className="card-header">
            <span>Warehouse capacity</span>
          </div>
          <div className="capacity-list">
            {capacityEntries.map((warehouse) => (
              <div key={warehouse.id} className="capacity-row">
                <div className="capacity-label-row">
                  <strong>{warehouse.name}</strong>
                  <span>{warehouse.total_capacity - warehouse.available_capacity}/{warehouse.total_capacity}</span>
                </div>
                <div className="capacity-track">
                  <span style={{ width: `${Math.max(8, warehouse.utilization * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="category-card-list">
          {categoryEntries.map(([category, count], index) => (
            <div key={category} className="category-card-item">
              <div className="category-topline">
                <span className="swatch" style={{ background: getCategoryPalette(index) }} />
                <strong>{category}</strong>
              </div>
              <div className="category-meta">
                <span>{count} products</span>
                <em>{Math.min(100, (count / Math.max(products.length, 1)) * 100).toFixed(0)}%</em>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
