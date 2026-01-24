import { createClient } from "@supabase/supabase-js";

// Admin client with service role for API routes (bypasses RLS)
// Use this ONLY in server-side API routes, never expose to client
export const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);
