import { createClient as createDataClient } from "@supabase/supabase-js";
import { createClient as createBrowserClient } from "@/lib/supabase/client";
import { sessionIdentity } from "@/lib/auth/session-guard";
import type { NesteggRequestScope } from "./session-scope";

/** Verify current identity, then bind data requests to that login's original token. */
export async function getNesteggDataClient(scope: NesteggRequestScope) {
  if (!scope.isCurrent()) return null;
  const browser = createBrowserClient();
  const { data: { user } } = await browser.auth.getUser();
  if (!scope.isCurrent() || user?.id !== scope.ownerId) return null;
  const { data: { session } } = await browser.auth.getSession();
  if (!scope.isCurrent() || session?.user.id !== scope.ownerId
    || sessionIdentity(session.access_token) !== scope.sessionId) return null;
  const token = session.access_token;
  // This client owns no persisted Auth state, listeners or token-refresh configuration.
  return createDataClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    accessToken: async () => {
      if (!scope.isCurrent()) throw new Error("Nestegg request session retired");
      return token;
    },
  });
}
