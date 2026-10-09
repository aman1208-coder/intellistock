export interface Warehouse {
  id: number;
  name: string;
  location: string;
  total_capacity: number;
  available_capacity: number;
}

export interface Product {
  id: number;
  name: string;
  sku?: string;
  stock_quantity: number;
  reorder_threshold: number;
  warehouse_id: number;
  category?: string;
  unit_price?: number;
  supplier_id?: number;
}

export interface CreateProductInput {
  name: string;
  sku: string;
  category: string;
  unit_price: number;
  stock_quantity: number;
  reorder_threshold: number;
  warehouse_id: number;
  supplier_id?: number;
}

export interface BankerResources {
  capacity: number;
  dock_bays: number;
  equipment: number;
}

export interface BankerRequest {
  warehouse_id: number;
  process_id: string;
  total_resources: BankerResources;
  available_resources: BankerResources;
  max_claim: BankerResources;
  request_vector: BankerResources;
}

export interface BankerResponse {
  warehouse_id: number;
  process_id: string;
  allocated: boolean;
  available_resources: BankerResources;
  safe_sequence: string[];
}

export interface ForecastDay {
  date: string;
  predicted_demand: number;
}

export interface DemandForecast {
  product_id: number;
  sku: string;
  product_name: string;
  model: string;
  history_days: number;
  horizon_days: number;
  current_stock: number;
  average_daily_demand: number;
  demand_std_dev: number;
  lead_time_days: number;
  service_level: number;
  safety_stock: number;
  reorder_point: number;
  recommended_order_quantity: number;
  forecast_total_demand: number;
  should_reorder: boolean;
  daily_forecast: ForecastDay[];
}

export interface InventoryTransaction {
  id: number;
  product_id: number;
  warehouse_id: number;
  type: 'SALE' | 'PURCHASE';
  quantity: number;
  timestamp: string;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly payload: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface PriorityJob {
  id: string;
  job_type: string;
  priority: 1 | 2 | 3;
  product_id?: number | null;
}

export interface ChatbotItem {
  product_id?: number;
  name?: string;
  warehouse_id?: number;
  stock_quantity?: number;
  reorder_threshold?: number;
  total_capacity?: number;
  available_capacity?: number;
  suggested_qty?: number;
  reason?: string;
  status?: string;
  location?: string;
}

export interface ChatbotResponse {
  answer: string;
  kind: string;
  items?: ChatbotItem[] | Record<string, unknown>;
}

export interface RecommendationItem {
  product_id: number;
  product_name: string;
  co_occurrence_count: number;
  score: number;
}

export interface RecommendationResponse {
  product_id: number;
  product_name: string;
  recommendations: RecommendationItem[];
}

export const TOKEN_STORAGE_KEY = 'intellistock_token';

export function getToken(): string {
  if (typeof window === 'undefined') {
    return '';
  }

  return localStorage.getItem(TOKEN_STORAGE_KEY) ?? '';
}

export function setToken(token: string) {
  if (typeof window === 'undefined') {
    return;
  }

  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken() {
  if (typeof window === 'undefined') {
    return;
  }

  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function login(username: string, password: string): Promise<{ access_token: string }> {
  const payload = await fetchJson<{ access_token: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });

  setToken(payload.access_token);
  return payload;
}

export async function register(email: string, username: string, password: string): Promise<{ id: number } | unknown> {
  return fetchJson('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, username, password }),
  });
}

export async function askChatbot(question: string): Promise<ChatbotResponse> {
  return fetchJson<ChatbotResponse>('/api/ai/chatbot', {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}

export async function fetchProductRecommendations(productId: number): Promise<RecommendationResponse> {
  return fetchJson<RecommendationResponse>(`/api/ai/recommendations/${productId}`);
}

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

async function readError(response: Response): Promise<{ message: string; payload: unknown }> {
  const raw = await response.text();

  if (!raw) {
    return { message: `Request failed with status ${response.status}`, payload: null };
  }

  let payload: unknown = raw;
  try {
    payload = JSON.parse(raw) as unknown;
  } catch {
    return { message: raw, payload };
  }

  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = payload.detail;
    if (typeof detail === 'string') {
      return { message: detail, payload };
    }

    if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
      return { message: detail.message, payload };
    }

    if (Array.isArray(detail)) {
      const detailText = detail
        .map((entry) => (
          typeof entry === 'string' ? entry : typeof entry === 'object' && entry && 'msg' in entry && typeof entry.msg === 'string' ? entry.msg : ''
        ))
        .filter(Boolean)
        .join('; ');
      if (detailText) {
        return { message: detailText, payload };
      }
    }
  }

  if (payload && typeof payload === 'object') {
    if ('message' in payload && typeof payload.message === 'string' && payload.message.trim()) {
      return { message: payload.message, payload };
    }
    if ('error' in payload && typeof payload.error === 'string') {
      return { message: payload.error, payload };
    }
  }

  return { message: raw, payload };
}

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options?.headers ?? {}),
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    if (response.status === 401 && getToken()) {
      clearToken();
      window.dispatchEvent(new Event('intellistock:logout'));
    }

    const error = await readError(response);
    throw new ApiError(error.message || `Request failed with status ${response.status}`, response.status, error.payload);
  }

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function createProduct(data: CreateProductInput): Promise<Product> {
  return fetchJson<Product>('/api/products', {
    method: 'POST',
    body: JSON.stringify({
      ...data,
      supplier_id: data.supplier_id ?? 1,
    }),
  });
}

export async function adjustStock(
  productId: number,
  warehouseId: number,
  type: 'PURCHASE' | 'SALE',
  quantity: number,
): Promise<Record<string, unknown>> {
  return fetchJson<Record<string, unknown>>('/api/transactions', {
    method: 'POST',
    body: JSON.stringify({
      product_id: productId,
      warehouse_id: warehouseId,
      type,
      quantity,
    }),
  });
}

export async function deleteProduct(productId: number): Promise<boolean> {
  await fetchJson<void>(`/api/products/${productId}`, {
    method: 'DELETE',
  });
  return true;
}
