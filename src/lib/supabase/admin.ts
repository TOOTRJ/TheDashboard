import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { ApiConfigurationError } from "@/lib/api/errors";

// Admin client with service role for API routes (bypasses RLS)
// Use this ONLY in server-side API routes, never expose to client
let cached: { url: string; key: string; client: SupabaseClient } | null = null;

export function getSupabaseAdmin() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url?.trim() || !key?.trim()) {
    cached = null;
    throw new ApiConfigurationError();
  }
  if (cached?.url === url && cached.key === key) return cached.client;
  try {
    const client = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } });
    if (!client || typeof client.from !== "function") throw new ApiConfigurationError();
    cached = { url, key, client };
    return client;
  } catch {
    cached = null;
    throw new ApiConfigurationError();
  }
}
