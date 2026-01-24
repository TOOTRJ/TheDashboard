import { NextRequest } from "next/server";
import { validateApiKey } from "./auth";
import * as responses from "./responses";

type HandlerFn = (request: NextRequest) => Promise<Response>;

interface HandlerOptions {
  /** Whether to require API key authentication (default: true) */
  requireAuth?: boolean;
}

/**
 * Wraps route handlers with common functionality:
 * - API key authentication
 * - Error catching and standardized error responses
 *
 * Usage:
 * ```ts
 * async function handleGet(request: NextRequest) {
 *   // Your logic here
 *   return responses.success(data);
 * }
 *
 * export const GET = withApiHandler(handleGet);
 * ```
 */
export function withApiHandler(
  handler: HandlerFn,
  options: HandlerOptions = {}
): HandlerFn {
  const { requireAuth = true } = options;

  return async (request: NextRequest) => {
    // Auth check
    if (requireAuth && !validateApiKey(request)) {
      return responses.unauthorized();
    }

    try {
      return await handler(request);
    } catch (error) {
      console.error("API Error:", error);
      return responses.serverError();
    }
  };
}
