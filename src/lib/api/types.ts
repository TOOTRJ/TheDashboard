// Standard API response wrapper
export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: ApiError;
  meta?: ResponseMeta;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

export interface ResponseMeta {
  timestamp: string;
  requestId?: string;
}

// Base type for paginated responses
export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  meta: ResponseMeta & {
    page: number;
    limit: number;
    total?: number;
  };
}

// Test events table type
export interface TestEvent {
  id: string;
  payload: Record<string, unknown>;
  source: string;
  created_at: string;
}

// Market sentiment types
export interface MarketSentiment {
  id: string;
  score: number;
  sentiment: "bullish" | "bearish" | "neutral";
  summary: string;
  key_factors: string[];
  date: string;
  source: string;
  created_at: string;
}

export interface SentimentPayload {
  score: number;
  sentiment: "bullish" | "bearish" | "neutral";
  summary: string;
  key_factors: string[];
  date?: string;
}
