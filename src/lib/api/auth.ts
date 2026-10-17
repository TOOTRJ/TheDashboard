import type { NextRequest } from "next/server";
import { validateSource } from "./validation";

export function isApiKeyConfigured(): boolean {
  return typeof process.env.API_SECRET_KEY === "string" && process.env.API_SECRET_KEY.trim() !== "";
}

/**
 * Validates the API key from the request headers
 */
export function validateApiKey(request: NextRequest): boolean {
  const apiKey = request.headers.get("x-api-key");
  return isApiKeyConfigured() && apiKey === process.env.API_SECRET_KEY;
}

/**
 * Extracts metadata from the request for logging/tracking
 */
export function getRequestMeta(request: NextRequest) {
  return {
    source: validateSource(request.headers.get("x-source")),
    userAgent: request.headers.get("user-agent") || "unknown",
  };
}
