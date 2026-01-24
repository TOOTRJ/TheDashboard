import { NextResponse } from "next/server";
import type { ApiResponse } from "./types";

/**
 * Creates a standardized API response with timestamp
 */
function createResponse<T>(
  body: ApiResponse<T>,
  status: number
): NextResponse<ApiResponse<T>> {
  return NextResponse.json(
    {
      ...body,
      meta: {
        ...body.meta,
        timestamp: new Date().toISOString(),
      },
    },
    { status }
  );
}

/**
 * Success response (200 OK)
 */
export function success<T>(data: T, status = 200) {
  return createResponse({ success: true, data }, status);
}

/**
 * Created response (201 Created)
 */
export function created<T>(data: T) {
  return success(data, 201);
}

/**
 * Unauthorized response (401)
 */
export function unauthorized(message = "Invalid or missing API key") {
  return createResponse(
    {
      success: false,
      error: { code: "UNAUTHORIZED", message },
    },
    401
  );
}

/**
 * Bad request response (400)
 */
export function badRequest(message: string, details?: unknown) {
  return createResponse(
    {
      success: false,
      error: { code: "BAD_REQUEST", message, details },
    },
    400
  );
}

/**
 * Not found response (404)
 */
export function notFound(message = "Resource not found") {
  return createResponse(
    {
      success: false,
      error: { code: "NOT_FOUND", message },
    },
    404
  );
}

/**
 * Internal server error response (500)
 */
export function serverError(message = "Internal server error") {
  return createResponse(
    {
      success: false,
      error: { code: "INTERNAL_ERROR", message },
    },
    500
  );
}
