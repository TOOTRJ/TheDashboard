import { type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public folder files
     * - auth/callback (OAuth callback - needs to set cookies first)
     * - api/ (API routes use API key auth, not session auth)
     */
    "/((?!_next/static|_next/image|favicon.ico|auth/callback|api/|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
