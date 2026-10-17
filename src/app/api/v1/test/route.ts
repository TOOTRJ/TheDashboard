import type { NextRequest } from "next/server";
import { getSupabaseAdmin } from "@/lib/supabase/admin";
import { withApiHandler, responses, getRequestMeta, validateLimit, readJsonObject, logApiFailure } from "@/lib/api";

// GET /api/v1/test - Retrieve test events
async function handleGet(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const limit = validateLimit(searchParams);
  getRequestMeta(request);

  const { data, error } = await getSupabaseAdmin()
    .from("test_events")
    .select("id,payload,source,created_at")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error || !Array.isArray(data)) {
    logApiFailure("DATABASE_READ");
    return responses.serverError("Failed to fetch events");
  }

  return responses.success(data);
}

// POST /api/v1/test - Create a test event
async function handlePost(request: NextRequest) {
  const body = await readJsonObject(request);
  const meta = getRequestMeta(request);

  const { data, error } = await getSupabaseAdmin()
    .from("test_events")
    .insert({
      payload: body,
      source: meta.source,
    })
    .select("id,payload,source,created_at")
    .single();

  if (error) {
    logApiFailure("DATABASE_WRITE");
    if (error.code === "23505") return responses.conflict();
    return responses.serverError("Failed to create event");
  }
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    logApiFailure("DATABASE_WRITE");
    return responses.serverError("Failed to create event");
  }

  return responses.created(data);
}

export const GET = withApiHandler(handleGet);
export const POST = withApiHandler(handlePost);
