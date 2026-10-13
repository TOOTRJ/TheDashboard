import type { NextRequest } from "next/server";
import { getSupabaseAdmin } from "@/lib/supabase/admin";
import { withApiHandler, responses, getRequestMeta, readJsonObject, validateSentiment, logApiFailure } from "@/lib/api";

// POST /api/v1/sentiment - Receive daily global integration sentiment.
async function handlePost(request: NextRequest) {
  const payload = validateSentiment(await readJsonObject(request));
  const meta = getRequestMeta(request);

  const { data, error } = await getSupabaseAdmin()
    .from("market_sentiment")
    .insert({
      score: payload.score,
      sentiment: payload.sentiment,
      summary: payload.summary,
      key_factors: payload.key_factors,
      date: payload.date ?? new Date().toISOString().split("T")[0],
      source: meta.source,
    })
    .select("id,score,sentiment,summary,key_factors,date,source,created_at")
    .single();

  if (error) {
    logApiFailure("DATABASE_WRITE");
    // The table's constraint provenance is unresolved; never guess a date cause.
    if (error.code === "23505") return responses.conflict();
    return responses.serverError("Failed to save sentiment data");
  }
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    logApiFailure("DATABASE_WRITE");
    return responses.serverError("Failed to save sentiment data");
  }

  return responses.created(data);
}

export const POST = withApiHandler(handlePost);
