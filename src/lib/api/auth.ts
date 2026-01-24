import { NextRequest } from "next/server";

/**
 * Validates the API key from the request headers
 */
export function validateApiKey(request: NextRequest): boolean {
  const apiKey = request.headers.get("x-api-key");
  return apiKey === process.env.API_SECRET_KEY;
}

/**
 * Extracts metadata from the request for logging/tracking
 */
export function getRequestMeta(request: NextRequest) {
  return {
    source: request.headers.get("x-source") || "unknown",
    userAgent: request.headers.get("user-agent") || "unknown",
  };
}
