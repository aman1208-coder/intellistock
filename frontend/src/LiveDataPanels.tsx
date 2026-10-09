import { useEffect, useState } from 'react';
import { fetchJson, type DemandForecast, type InventoryTransaction, type Product } from './api';

export function ForecastPanel({ products }: { products: Product[] }) {
  const [productId, setProductId] = useState(products[0]?.id ?? 0);
  const [forecast, setForecast] = useState<DemandForecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (products.length && !products.some((product) => product.id === productId)) {
      setProductId(products[0].id);
    }
  }, [productId, products]);

  useEffect(() => {
    if (!productId) {
      return;
    }
    let active = true;
    setLoading(true);
    setError('');
    fetchJson<DemandForecast>(`/api/ai/forecast/${productId}?horizon_days=14`)
      .then((result) => {
        if (active) setForecast(result);
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : 'Unable to load the forecast.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [productId]);

  const maximumDemand = Math.max(...(forecast?.daily_forecast.map((day) => day.predicted_demand) ?? [0]), 1);

  return (
    <section className="glass-panel forecast-panel" id="forecast">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Demand planning</span>
          <h2>14-day forecast</h2>
        </div>
        <label>
          Product
          <select aria-label="Forecast product" value={productId} onChange={(event) => setProductId(Number(event.target.value))} disabled={!products.length}>
            {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
          </select>
        </label>
      </div>

      {error ? <p className="api-error-inline" role="alert">Forecast unavailable: {error}</p> : null}
      {!products.length && !error ? <p className="empty-state">No products are available for forecasting.</p> : null}
      {loading && !forecast ? <p className="empty-state">Loading forecast…</p> : null}
      {forecast ? (
        <>
          <div className="forecast-metrics">
            <div><span>Average daily demand</span><strong>{forecast.average_daily_demand.toFixed(1)}</strong></div>
            <div><span>Safety stock</span><strong>{forecast.safety_stock.toFixed(1)}</strong></div>
            <div><span>Reorder point</span><strong>{forecast.reorder_point.toFixed(1)}</strong></div>
          </div>
          <div className="forecast-chart" role="img" aria-label={`Daily demand forecast for ${forecast.product_name}`}>
            {forecast.daily_forecast.map((day) => (
              <div className="forecast-day" key={day.date} title={`${day.date}: ${day.predicted_demand.toFixed(1)} units`}>
                <span className="forecast-bar-track">
                  <span style={{ height: `${Math.max(5, (day.predicted_demand / maximumDemand) * 100)}%` }} />
                </span>
                <small>{day.date.slice(5)}</small>
              </div>
            ))}
          </div>
          <p className="forecast-footnote">{forecast.model} · {forecast.history_days} history days · {forecast.forecast_total_demand.toFixed(1)} forecast units</p>
        </>
      ) : null}
    </section>
  );
}

export function TransactionsPanel({ products, refreshKey }: { products: Product[]; refreshKey: number }) {
  const [productFilter, setProductFilter] = useState('all');
  const [transactions, setTransactions] = useState<InventoryTransaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ limit: '20' });
    if (productFilter !== 'all') query.set('product_id', productFilter);
    setLoading(true);
    setError('');
    fetchJson<InventoryTransaction[]>(`/api/transactions?${query}`)
      .then((result) => {
        if (active) setTransactions(result);
      })
      .catch((requestError) => {
        if (active) {
          setTransactions([]);
          setError(requestError instanceof Error ? requestError.message : 'Unable to load transactions.');
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [productFilter, refreshKey]);

  return (
    <section className="glass-panel transactions-panel" id="sync">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Inventory activity</span>
          <h2>Live transactions</h2>
        </div>
        <label>
          Product filter
          <select aria-label="Transaction product filter" value={productFilter} onChange={(event) => setProductFilter(event.target.value)}>
            <option value="all">All products</option>
            {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
          </select>
        </label>
      </div>
      {error ? <p className="api-error-inline" role="alert">Transactions unavailable: {error}</p> : null}
      {loading && !transactions.length ? <p className="empty-state">Loading transactions…</p> : null}
      {!loading && !error && !transactions.length ? <p className="empty-state">No transactions match this filter.</p> : null}
      {transactions.length ? (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Time</th><th>Product</th><th>Type</th><th>Quantity</th></tr></thead>
            <tbody>
              {transactions.map((transaction) => (
                <tr key={transaction.id}>
                  <td>{new Date(transaction.timestamp).toLocaleString()}</td>
                  <td>{products.find((product) => product.id === transaction.product_id)?.name ?? `Product ${transaction.product_id}`}</td>
                  <td>{transaction.type}</td>
                  <td>{transaction.quantity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}