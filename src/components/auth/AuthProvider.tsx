"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { createClient } from "@/lib/supabase/client";
import { createSessionGuard, sessionIdentity } from "@/lib/auth/session-guard";
import type { User, Session } from "@supabase/supabase-js";

export type Profile = {
  id: string;
  email: string | null;
  full_name: string | null;
  avatar_url: string | null;
  created_at: string;
  updated_at: string;
};

interface AuthContextType {
  user: User | null;
  session: Session | null;
  profile: Profile | null;
  loading: boolean;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const supabase = useMemo(() => createClient(), []);
  const [guard] = useState(createSessionGuard);

  const fetchProfile = useCallback(
    async (ticket: { revision: number; userId: string | null }) => {
      if (!ticket.userId || !guard.isCurrent(ticket)) return;
      const { data, error } = await supabase
        .from("profiles")
        .select(
          "id, email, full_name, avatar_url, created_at, updated_at"
        )
        .eq("id", ticket.userId)
        .maybeSingle();
      if (!guard.isCurrent(ticket)) return;
      setProfile(error ? null : data as Profile | null);
    },
    [supabase, guard]
  );

  const refreshProfile = useCallback(async () => {
    await fetchProfile(guard.capture());
  }, [guard, fetchProfile]);

  useEffect(() => {
    guard.activate();
    const bootstrap = guard.capture();
    const applySession = (event: string, nextSession: Session | null) => {
      const ticket = guard.accept(event, nextSession?.user.id ?? null, sessionIdentity(nextSession?.access_token));
      if (!ticket) return;
      setSession(nextSession);
      setUser(nextSession?.user ?? null);
      setProfile((previous) => previous?.id === ticket.userId ? previous : null);
      setLoading(false);
      // The auth callback stays synchronous; profile I/O runs after it returns.
      if (ticket.userId) queueMicrotask(() => void fetchProfile(ticket).catch(() => {
        if (guard.isCurrent(ticket)) setProfile(null);
      }));
    };

    const init = async () => {
      const {
        data: { user: verifiedUser },
      } = await supabase.auth.getUser();

      if (!guard.isCurrent(bootstrap)) return;

      if (!verifiedUser) {
        applySession("BOOTSTRAP", null);
        return;
      }

      const {
        data: { session: nextSession },
      } = await supabase.auth.getSession();
      if (!guard.isCurrent(bootstrap)) return;
      applySession("BOOTSTRAP", nextSession?.user.id === verifiedUser.id ? nextSession : null);
    };

    void init().catch(() => {
      if (guard.isCurrent(bootstrap)) applySession("BOOTSTRAP", null);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      applySession(event, nextSession);
    });

    return () => {
      guard.dispose();
      subscription.unsubscribe();
    };
  }, [supabase, fetchProfile, guard]);

  const signOut = async () => {
    // Retire local authority before network I/O can delay or fail sign-out.
    guard.signOut();
    setSession(null);
    setUser(null);
    setProfile(null);
    setLoading(false);
    try {
      await supabase.auth.signOut();
    } finally {
      // Re-login may create a new session even if the old remote logout failed.
      // The guard continues rejecting focus/refresh events for the retired session.
      guard.finishSignOut();
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        profile,
        loading,
        signOut,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
