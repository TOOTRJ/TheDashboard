/** UI lifecycle identity only; decoding a claim never authenticates or authorizes it. */
export function sessionIdentity(accessToken: string | undefined): string | null {
  if (!accessToken) return null;
  try {
    const payload = JSON.parse(atob(accessToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (typeof payload.session_id === "string" && payload.session_id) return `session:${payload.session_id}`;
  } catch { /* Non-JWT/test tokens can still be compared for exact reestablishment. */ }
  return `token:${accessToken}`;
}

/** Owns async session/profile work; retiring a session invalidates every old result. */
export function createSessionGuard() {
  let revision = 0;
  let active = true;
  let userId: string | null = null;
  let locallySignedOut = false;
  let signingOut = false;
  let identity: string | null = null;
  const retiredSessions = new Set<string>();
  return {
    activate() { active = true; revision += 1; },
    dispose() { active = false; revision += 1; },
    capture() { return { revision, userId }; },
    isCurrent(ticket: { revision: number; userId: string | null }) {
      return active && revision === ticket.revision && userId === ticket.userId;
    },
    accept(event: string, nextUserId: string | null, nextIdentity: string | null = null) {
      if (!active || (nextUserId !== null && (signingOut ||
        (nextIdentity !== null && retiredSessions.has(nextIdentity)) ||
        (locallySignedOut && event !== "SIGNED_IN")))) return null;
      if (event === "SIGNED_IN") locallySignedOut = false;
      if (event === "SIGNED_OUT") {
        locallySignedOut = true;
        if (identity) retiredSessions.add(identity);
      }
      userId = nextUserId;
      identity = nextIdentity;
      revision += 1;
      return { revision, userId };
    },
    signOut() {
      signingOut = true;
      locallySignedOut = true;
      if (identity) retiredSessions.add(identity);
      identity = null;
      userId = null;
      revision += 1;
    },
    finishSignOut() { signingOut = false; },
  };
}
