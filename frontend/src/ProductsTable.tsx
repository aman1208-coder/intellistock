import { AnimatePresence, motion } from 'framer-motion';
import { Fragment, useMemo, useState } from 'react';
import {
  adjustStock,
  createProduct,
  deleteProduct,
  fetchProductRecommendations,
  type Product,
  type RecommendationItem,
  type Warehouse,
} from './api';

const emptyAddForm = {
  name: '',
  sku: '',
  category: '',
  unit_price: '24.99',
  stock_quantity: '25',
  reorder_threshold: '8',
  warehouse_id: '1',
};

export default function ProductsTable({
  products,
  warehouses,
  onRefresh,
  onToast,
}: {
  products: Product[];
  warehouses: Warehouse[];
  onRefresh?: () => Promise<void> | void;
  onToast?: (title: string, detail: string, kind: 'success' | 'warning' | 'danger' | 'info') => void;
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [recommendations, setRecommendations] = useState<Record<number, RecommendationItem[]>>({});
  const [recommendationErrors, setRecommendationErrors] = useState<Record<number, string>>({});
  const [loadingId, setLoadingId] = useState<number | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showAdjustModal, setShowAdjustModal] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [addForm, setAddForm] = useState(emptyAddForm);
  const [adjustForm, setAdjustForm] = useState({ type: 'PURCHASE' as 'PURCHASE' | 'SALE', quantity: '10' });
  const [isCreating, setIsCreating] = useState(false);
  const [isAdjusting, setIsAdjusting] = useState(false);

  const warehouseMap = useMemo(
    () => Object.fromEntries((warehouses || []).map((warehouse) => [warehouse.id, warehouse])),
    [warehouses],
  );

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
    setRecommendationErrors((current) => ({ ...current, [productId]: '' }));
    try {
      const response = await fetchProductRecommendations(productId);
      setRecommendations((current) => ({
        ...current,
        [productId]: response.recommendations ?? [],
      }));
    } catch (error) {
      setRecommendations((current) => ({
        ...current,
        [productId]: [],
      }));
      setRecommendationErrors((current) => ({
        ...current,
        [productId]: error instanceof Error ? error.message : 'Unable to load recommendations.',
      }));
    } finally {
      setLoadingId(null);
    }
  };

  const handleCreateProduct = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsCreating(true);

    try {
      const payload = {
        name: addForm.name.trim(),
        sku: addForm.sku.trim(),
        category: addForm.category.trim(),
        unit_price: Number(addForm.unit_price),
        stock_quantity: Number(addForm.stock_quantity),
        reorder_threshold: Number(addForm.reorder_threshold),
        warehouse_id: Number(addForm.warehouse_id),
        supplier_id: 1,
      };

      if (!payload.name || !payload.sku || !payload.category || payload.unit_price <= 0) {
        throw new Error('Complete the product details before creating the record.');
      }

      await createProduct(payload);
      onToast?.('Product created', `${payload.name} was added to the live inventory feed.`, 'success');
      setAddForm(emptyAddForm);
      setShowAddModal(false);
      await onRefresh?.();
    } catch (error) {
      onToast?.('Add product failed', error instanceof Error ? error.message : 'Unable to create the product.', 'danger');
    } finally {
      setIsCreating(false);
    }
  };

  const handleAdjustStock = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedProduct) {
      return;
    }

    const quantity = Number(adjustForm.quantity);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      onToast?.('Invalid quantity', 'Enter a positive integer for the stock update.', 'warning');
      return;
    }

    setIsAdjusting(true);
    try {
      await adjustStock(selectedProduct.id, selectedProduct.warehouse_id, adjustForm.type, quantity);
      onToast?.(
        adjustForm.type === 'PURCHASE' ? 'Restock recorded' : 'Sale recorded',
        `${adjustForm.type === 'PURCHASE' ? 'Added' : 'Deducted'} ${quantity} units from ${selectedProduct.name}.`,
        'success',
      );
      setShowAdjustModal(false);
      setSelectedProduct(null);
      setAdjustForm({ type: 'PURCHASE', quantity: '10' });
      await onRefresh?.();
    } catch (error) {
      onToast?.('Stock adjustment failed', error instanceof Error ? error.message : 'Inventory update was rejected.', 'danger');
    } finally {
      setIsAdjusting(false);
    }
  };

  const handleDeleteProduct = async (product: Product) => {
    if (!window.confirm(`Delete ${product.name} from inventory?`)) {
      return;
    }

    try {
      await deleteProduct(product.id);
      onToast?.('Product removed', `${product.name} was deleted from the catalogue.`, 'info');
      if (expandedId === product.id) {
        setExpandedId(null);
      }
      await onRefresh?.();
    } catch (error) {
      onToast?.('Delete failed', error instanceof Error ? error.message : 'Unable to delete this product.', 'danger');
    }
  };

  return (
    <section className="glass-panel products-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Inventory overview</span>
          <h2>Products</h2>
        </div>

        <motion.button
          type="button"
          className="primary product-add-button"
          onClick={() => setShowAddModal(true)}
          whileHover={{ scale: 1.025, rotateX: -2, rotateY: 3 }}
          transition={{ type: 'spring', stiffness: 400, damping: 20 }}
          style={{ perspective: 1000, transformStyle: 'preserve-3d' }}
        >
          + Add Product
        </motion.button>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Warehouse</th>
              <th>Stock</th>
              <th>Threshold</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => {
              const warehouse = warehouseMap[product.warehouse_id];
              const stockPercent = Math.min(100, Math.max(0, (product.stock_quantity / Math.max(product.reorder_threshold || 1, 1)) * 100));

              return (
                <Fragment key={product.id}>
                  <tr>
                    <td>
                      <div className="product-cell">
                        <strong>{product.name}</strong>
                        <small>{product.sku ?? 'SKU pending'}</small>
                      </div>
                    </td>
                    <td>{warehouse ? warehouse.name : `Warehouse ${product.warehouse_id}`}</td>
                    <td>
                      <div className="stock-wrap">
                        <span>{product.stock_quantity}</span>
                        <div className="stock-meter">
                          <span style={{ width: `${stockPercent}%` }} />
                        </div>
                      </div>
                    </td>
                    <td>{product.reorder_threshold}</td>
                    <td>
                      <div className="product-actions">
                        <button type="button" className="secondary-action" onClick={() => void viewInsights(product.id)}>
                          {expandedId === product.id ? 'Hide insights' : 'View Insights'}
                        </button>
                        <button
                          type="button"
                          className="secondary-action"
                          onClick={() => {
                            setSelectedProduct(product);
                            setShowAdjustModal(true);
                          }}
                        >
                          ⚡ Adjust Stock
                        </button>
                        <button type="button" className="danger-action" onClick={() => void handleDeleteProduct(product)}>
                          🗑️
                        </button>
                      </div>
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
                            ) : recommendationErrors[product.id] ? (
                              <span role="alert">Recommendations unavailable: {recommendationErrors[product.id]}</span>
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
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <AnimatePresence>
        {showAddModal ? (
          <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowAddModal(false)}
          >
            <motion.div
              className="modal-card"
              initial={{ opacity: 0, scale: 0.85, rotateX: 12 }}
              animate={{ opacity: 1, scale: 1, rotateX: 0 }}
              exit={{ opacity: 0, scale: 0.9, rotateX: 10 }}
              transition={{ type: 'spring', stiffness: 280, damping: 22 }}
              style={{ perspective: 1200, transformStyle: 'preserve-3d' }}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="modal-header">
                <div>
                  <span className="eyebrow">New inventory item</span>
                  <h3>Add product</h3>
                </div>
                <button type="button" className="close-button" onClick={() => setShowAddModal(false)}>
                  ✕
                </button>
              </div>

              <form className="modal-form" onSubmit={handleCreateProduct}>
                <div className="field-grid">
                  <label>
                    Product name
                    <input value={addForm.name} onChange={(event) => setAddForm((current) => ({ ...current, name: event.target.value }))} />
                  </label>
                  <label>
                    SKU
                    <input value={addForm.sku} onChange={(event) => setAddForm((current) => ({ ...current, sku: event.target.value }))} />
                  </label>
                  <label>
                    Category
                    <input value={addForm.category} onChange={(event) => setAddForm((current) => ({ ...current, category: event.target.value }))} />
                  </label>
                  <label>
                    Unit price
                    <input type="number" step="0.01" value={addForm.unit_price} onChange={(event) => setAddForm((current) => ({ ...current, unit_price: event.target.value }))} />
                  </label>
                  <label>
                    Initial stock
                    <input type="number" min="0" value={addForm.stock_quantity} onChange={(event) => setAddForm((current) => ({ ...current, stock_quantity: event.target.value }))} />
                  </label>
                  <label>
                    Reorder threshold
                    <input type="number" min="0" value={addForm.reorder_threshold} onChange={(event) => setAddForm((current) => ({ ...current, reorder_threshold: event.target.value }))} />
                  </label>
                  <label className="full-span">
                    Warehouse
                    <select value={addForm.warehouse_id} onChange={(event) => setAddForm((current) => ({ ...current, warehouse_id: event.target.value }))}>
                      {(warehouses || []).map((warehouse) => (
                        <option key={warehouse.id} value={warehouse.id}>
                          {warehouse.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="modal-actions">
                  <button type="button" className="ghost-button" onClick={() => setShowAddModal(false)}>
                    Cancel
                  </button>
                  <button type="submit" className="primary" disabled={isCreating}>
                    {isCreating ? 'Creating...' : 'Create product'}
                  </button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {showAdjustModal && selectedProduct ? (
          <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowAdjustModal(false)}
          >
            <motion.div
              className="modal-card"
              initial={{ opacity: 0, scale: 0.9, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: 8 }}
              transition={{ type: 'spring', stiffness: 260, damping: 22 }}
              onClick={(event) => event.stopPropagation()}
            >
              <div className="modal-header">
                <div>
                  <span className="eyebrow">Stock control</span>
                  <h3>⚡ Adjust Stock</h3>
                </div>
                <button type="button" className="close-button" onClick={() => setShowAdjustModal(false)}>
                  ✕
                </button>
              </div>

              <form className="modal-form" onSubmit={handleAdjustStock}>
                <div className="toggle-row">
                  <button
                    type="button"
                    className={adjustForm.type === 'PURCHASE' ? 'primary' : 'ghost-button'}
                    onClick={() => setAdjustForm((current) => ({ ...current, type: 'PURCHASE' }))}
                  >
                    Restock (Purchase)
                  </button>
                  <button
                    type="button"
                    className={adjustForm.type === 'SALE' ? 'primary' : 'ghost-button'}
                    onClick={() => setAdjustForm((current) => ({ ...current, type: 'SALE' }))}
                  >
                    Record Sale
                  </button>
                </div>

                <label>
                  Quantity
                  <input
                    type="number"
                    min="1"
                    value={adjustForm.quantity}
                    onChange={(event) => setAdjustForm((current) => ({ ...current, quantity: event.target.value }))}
                  />
                </label>

                <div className="adjust-summary">
                  <strong>{selectedProduct.name}</strong>
                  <span>
                    Current on-hand stock: {selectedProduct.stock_quantity} · Warehouse {selectedProduct.warehouse_id}
                  </span>
                </div>

                <div className="modal-actions">
                  <button type="button" className="ghost-button" onClick={() => setShowAdjustModal(false)}>
                    Cancel
                  </button>
                  <button type="submit" className="primary" disabled={isAdjusting}>
                    {isAdjusting ? 'Updating...' : 'Submit adjustment'}
                  </button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </section>
  );
}
