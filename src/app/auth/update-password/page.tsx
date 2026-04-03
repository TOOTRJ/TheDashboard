"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Terminal, Zap, Lock, Eye, EyeOff, AlertCircle, Loader2 } from "lucide-react";

export default function UpdatePasswordPage() {
  const [password, setPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [checkingSession, setCheckingSession] = React.useState(true);
  const router = useRouter();
  const supabase = React.useMemo(() => createClient(), []);

  React.useEffect(() => {
    let cancelled = false;

    const run = async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (cancelled) return;
      if (!session) {
        router.replace("/login?error=recovery_session");
        return;
      }
      setCheckingSession(false);
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [router, supabase]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }

    setLoading(true);

    try {
      const { error: updateError } = await supabase.auth.updateUser({
        password,
      });

      if (updateError) {
        setError(updateError.message);
      } else {
        router.push("/");
        router.refresh();
      }
    } catch {
      setError("An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  if (checkingSession) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-[#00fff5]" aria-label="Loading" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
      <div className="aurora-bg" aria-hidden="true" />
      <div className="fixed inset-0 synthwave-grid pointer-events-none opacity-30" />
      <div className="fixed inset-0 bg-gradient-to-br from-[#00fff5]/5 via-transparent to-[#ff00ff]/5 pointer-events-none" />

      <div className="relative z-10 w-full max-w-md px-4">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center gap-3 mb-4">
            <Terminal className="h-10 w-10 text-[#00fff5]" />
            <h1 className="text-3xl font-bold tracking-tight">
              <span className="neon-text-cyan">NEXUS</span>
              <span className="text-[#ff00ff]"> TERMINAL</span>
            </h1>
          </div>
          <p className="text-muted-foreground text-sm">Set a new password for your account</p>
        </div>

        <div className="relative">
          <div className="absolute -inset-1 bg-gradient-to-r from-[#00fff5]/20 via-[#ff00ff]/20 to-[#00fff5]/20 rounded-2xl blur-xl opacity-50" />

          <div className="relative bg-card/90 backdrop-blur-xl border border-[#00fff5]/20 rounded-2xl p-8 shadow-2xl">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2">
              <div className="relative flex items-center justify-center h-12 w-12 rounded-full bg-card border-2 border-[#00fff5]/50">
                <Lock className="h-5 w-5 text-[#00fff5]" />
              </div>
            </div>

            <div className="mt-4">
              <h2 className="text-xl font-bold text-center mb-2">
                <span className="text-[#00fff5]">RESET</span> PASSWORD
              </h2>
              <div className="flex items-center gap-2 justify-center mb-6">
                <div className="h-px flex-1 bg-gradient-to-r from-transparent to-[#00fff5]/30" />
                <Zap className="h-3 w-3 text-[#00fff5]" />
                <div className="h-px flex-1 bg-gradient-to-l from-transparent to-[#00fff5]/30" />
              </div>

              {error && (
                <div className="mb-4 p-3 rounded-lg bg-[#ff3366]/10 border border-[#ff3366]/30 flex items-center gap-2 text-sm text-[#ff3366]">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="new-password" className="text-xs uppercase tracking-wider text-muted-foreground">
                    New password
                  </Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="new-password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="new-password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      minLength={6}
                      className="pl-10 pr-10 bg-background/50 border-[#00fff5]/20 focus:border-[#00fff5]/50 focus:ring-[#00fff5]/20"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirm-password" className="text-xs uppercase tracking-wider text-muted-foreground">
                    Confirm password
                  </Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="confirm-password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="new-password"
                      placeholder="••••••••"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      minLength={6}
                      className="pl-10 bg-background/50 border-[#00fff5]/20 focus:border-[#00fff5]/50 focus:ring-[#00fff5]/20"
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={loading}
                  className="w-full bg-gradient-to-r from-[#00fff5] to-[#00d4aa] hover:from-[#00fff5]/90 hover:to-[#00d4aa]/90 text-black font-bold py-5 transition-all duration-300 hover:shadow-lg hover:shadow-[#00fff5]/20"
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      UPDATING...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Zap className="h-4 w-4" />
                      SAVE NEW PASSWORD
                    </span>
                  )}
                </Button>
              </form>

              <div className="mt-6 text-center">
                <Link
                  href="/login"
                  className="text-sm text-[#00fff5] hover:text-[#00fff5]/80 font-medium transition-colors hover:underline"
                >
                  Back to login
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
