import { NextRequest } from "next/server";
import { supabaseAdmin } from "@/lib/supabase/admin";
import { withApiHandler, responses, getRequestMeta } from "@/lib/api";

// GET /api/v1/test - Retrieve test events
async function handleGet(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const limit = Math.min(parseInt(searchParams.get("limit") || "50"), 100);

  const { data, error } = await supabaseAdmin
    .from("test_events")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    console.error("Supabase error:", error);
    return responses.serverError("Failed to fetch events");
  }

  return responses.success(data);
}

// POST /api/v1/test - Create a test event
async function handlePost(request: NextRequest) {
  const body = await request.json().catch(() => null);

  if (!body || typeof body !== "object") {
    return responses.badRequest("Request body must be a valid JSON object");
  }

  const meta = getRequestMeta(request);

  const { data, error } = await supabaseAdmin
    .from("test_events")
    .insert({
      payload: body,
      source: meta.source,
    })
    .select()
    .single();

  if (error) {
    console.error("Supabase error:", error);
    return responses.serverError("Failed to create event");
  }

  return responses.created(data);
}

export const GET = withApiHandler(handleGet);
export const POST = withApiHandler(handlePost);
