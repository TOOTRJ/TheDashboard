import { NextRequest } from "next/server";
import { supabaseAdmin } from "@/lib/supabase/admin";
import {
  withApiHandler,
  responses,
  getRequestMeta,
  type SentimentPayload,
} from "@/lib/api";

const VALID_SENTIMENTS = ["bullish", "bearish", "neutral"] as const;

/**
 * Validates the sentiment payload structure
 */
function validatePayload(
  body: unknown
): { valid: true; data: SentimentPayload } | { valid: false; error: string } {
  if (!body || typeof body !== "object") {
    return { valid: false, error: "Request body must be a valid JSON object" };
  }

  const payload = body as Record<string, unknown>;

  // Validate score
  if (typeof payload.score !== "number") {
    return { valid: false, error: "score must be a number" };
  }
  if (payload.score < 0 || payload.score > 100) {
    return { valid: false, error: "score must be between 0 and 100" };
  }

  // Validate sentiment
  if (
    typeof payload.sentiment !== "string" ||
    !VALID_SENTIMENTS.includes(payload.sentiment as typeof VALID_SENTIMENTS[number])
  ) {
    return {
      valid: false,
      error: `sentiment must be one of: ${VALID_SENTIMENTS.join(", ")}`,
    };
  }

  // Validate summary
  if (typeof payload.summary !== "string" || payload.summary.trim() === "") {
    return { valid: false, error: "summary must be a non-empty string" };
  }

  // Validate key_factors
  if (!Array.isArray(payload.key_factors)) {
    return { valid: false, error: "key_factors must be an array" };
  }
  if (!payload.key_factors.every((f) => typeof f === "string")) {
    return { valid: false, error: "key_factors must be an array of strings" };
  }

  // Validate optional date
  if (payload.date !== undefined) {
    if (typeof payload.date !== "string") {
      return { valid: false, error: "date must be a string in YYYY-MM-DD format" };
    }
    // Basic date format validation
    if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.date)) {
      return { valid: false, error: "date must be in YYYY-MM-DD format" };
    }
  }

  return {
    valid: true,
    data: {
      score: payload.score,
      sentiment: payload.sentiment as SentimentPayload["sentiment"],
      summary: payload.summary,
      key_factors: payload.key_factors as string[],
      date: payload.date as string | undefined,
    },
  };
}

// POST /api/v1/sentiment - Receive daily market sentiment
async function handlePost(request: NextRequest) {
  const body = await request.json().catch(() => null);

  const validation = validatePayload(body);
  if (!validation.valid) {
    return responses.badRequest(validation.error);
  }

  const { data: payload } = validation;
  const meta = getRequestMeta(request);

  const { data, error } = await supabaseAdmin
    .from("market_sentiment")
    .insert({
      score: payload.score,
      sentiment: payload.sentiment,
      summary: payload.summary,
      key_factors: payload.key_factors,
      date: payload.date || new Date().toISOString().split("T")[0],
      source: meta.source,
    })
    .select()
    .single();

  if (error) {
    console.error("Supabase error:", error);

    // Handle unique constraint violation (duplicate date)
    if (error.code === "23505") {
      return responses.badRequest(
        "Sentiment for this date already exists. Only one entry per day is allowed."
      );
    }

    return responses.serverError("Failed to save sentiment data");
  }

  return responses.created(data);
}

export const POST = withApiHandler(handlePost);
