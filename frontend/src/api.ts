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
  status: string;
  safe_sequence?: string[];
  detail?: string;
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

export async function askChatbot(question: string): Promise<ChatbotResponse> {
  return fetchJson<ChatbotResponse>('/api/ai/chatbot', {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}

export async function fetchProductRecommendations(productId: number): Promise<RecommendationResponse> {
  return fetchJson<RecommendationResponse>(`/api/ai/recommendations/${productId}`);
}

export const API_BASE_URL = 'http://localhost:8000';

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}
