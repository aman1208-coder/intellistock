import { AnimatePresence, motion } from 'framer-motion';
import { useState } from 'react';
import { fetchProductRecommendations, type Product, type RecommendationItem } from './api';

export default function ProductsTable({ products }: { products: Product[] }) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [recommendations, setRecommendations] = useState<Record<number, RecommendationItem[]>>({});
  const [loadingId, setLoadingId] = useState<number | null>(null);

  const viewInsights = async (productId: number) => {
    if (expandedId === productId && recommendations[productId]) {
      setExpandedId(null);
      return;
    }

    setExpandedId(productId);
    if (recommendations[productId]) {
      return;
    }

    setLoadingId(productId);
    try {
      const response = await fetchProductRecommendations(productId);
      setRecommendations((current) => ({
        ...current,
        [productId]: response.recommendations ?? [],
      }));
    } catch {
      setRecommendations((current) => ({
        ...current,
        [productId]: [],
      }));
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <section className="glass-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Inventory overview</span>
          <h2>Products</h2>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Warehouse</th>
              <th>Stock</th>
              <th>Threshold</th>
              <th>Insights</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => (
              <>
                <tr key={product.id}>
                  <td>{product.name}</td>
                  <td>{product.warehouse_id}</td>
                  <td>{product.stock_quantity}</td>
                  <td>{product.reorder_threshold}</td>
                  <td>
                    <button type="button" onClick={() => void viewInsights(product.id)}>
                      {expandedId === product.id ? 'Hide insights' : 'View Insights'}
                    </button>
                  </td>
                </tr>
                <AnimatePresence initial={false}>
                  {expandedId === product.id && (
                    <motion.tr
                      key={`${product.id}-insights`}
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      <td colSpan={5}>
                        <div className="insights-card">
                          {loadingId === product.id ? (
                            <span>Loading related items...</span>
                          ) : (recommendations[product.id]?.length ?? 0) > 0 ? (
                            <ul>
                              {recommendations[product.id].map((item) => (
                                <li key={item.product_id}>
                                  {item.product_name} · {item.co_occurrence_count} co-purchases · score {item.score}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span>No correlated items detected for this product.</span>
                          )}
                        </div>
                      </td>
                    </motion.tr>
                  )}
                </AnimatePresence>
              </>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
