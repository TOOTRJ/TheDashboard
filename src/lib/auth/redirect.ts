/** Resolve a post-login path against the request origin, never a forwarded header. */
export function getSafeAuthRedirect(requestUrl: string, next: string | null): URL {
  const origin = new URL(requestUrl).origin;
  const fallback = new URL("/", origin);
  // URLSearchParams has already decoded this value. Decoding it again changes
  // legitimate paths and can turn encoded separators into redirect targets.
  if (!next || !next.startsWith("/") || next.startsWith("//")) return fallback;
  if (/[\\\u0000-\u0020\u007f]/.test(next)) return fallback;
  try {
    const target = new URL(next, origin);
    return target.origin === origin ? target : fallback;
  } catch {
    return fallback;
  }
}
