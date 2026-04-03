"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Terminal, Zap, Lock, Mail, Eye, EyeOff, AlertCircle, Loader2 } from "lucide-react";

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  );
}

export default function LoginPage() {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [googleLoading, setGoogleLoading] = React.useState(false);
  const [forgotOpen, setForgotOpen] = React.useState(false);
  const [resetEmail, setResetEmail] = React.useState("");
  const [resetLoading, setResetLoading] = React.useState(false);
  const [resetError, setResetError] = React.useState<string | null>(null);
  const [resetSent, setResetSent] = React.useState(false);
  const router = useRouter();
  const supabase = React.useMemo(() => createClient(), []);

  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const err = params.get("error");
    if (err === "recovery_session") {
      setError(
        "This password reset link is invalid or has expired. Request a new one with “Forgot password?” below."
      );
      router.replace("/login", { scroll: false });
    } else if (err === "auth_callback_error") {
      setError("Sign-in could not be completed. Try again or use another method.");
      router.replace("/login", { scroll: false });
    }
  }, [router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        setError(error.message);
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

  const handleGoogleLogin = async () => {
    setError(null);
    setGoogleLoading(true);

    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      });

      if (error) {
        setError(error.message);
        setGoogleLoading(false);
      }
      // If successful, the user will be redirected to Google
    } catch {
      setError("An unexpected error occurred");
      setGoogleLoading(false);
    }
  };

  const openForgotPassword = () => {
    setResetEmail(email.trim());
    setResetError(null);
    setResetSent(false);
    setForgotOpen(true);
  };

  const handlePasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setResetError(null);
    const trimmed = resetEmail.trim().toLowerCase();
    if (!trimmed) {
      setResetError("Enter your email address.");
      return;
    }

    setResetLoading(true);
    try {
      const callback = new URL("/auth/callback", window.location.origin);
      callback.searchParams.set("next", "/auth/update-password");

      const { error: resetErr } = await supabase.auth.resetPasswordForEmail(trimmed, {
        redirectTo: callback.toString(),
      });

      if (resetErr) {
        setResetError(resetErr.message);
      } else {
        setResetSent(true);
      }
    } catch {
      setResetError("An unexpected error occurred");
    } finally {
      setResetLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
      {/* Background effects */}
      <div className="aurora-bg" aria-hidden="true" />
      <div className="fixed inset-0 synthwave-grid pointer-events-none opacity-30" />
      <div className="fixed inset-0 bg-gradient-to-br from-[#00fff5]/5 via-transparent to-[#ff00ff]/5 pointer-events-none" />
      
      {/* Animated particles */}
      <div className="particles" aria-hidden="true">
        <div className="particle" style={{ left: '15%' }} />
        <div className="particle" style={{ left: '35%' }} />
        <div className="particle" style={{ left: '55%' }} />
        <div className="particle" style={{ left: '75%' }} />
        <div className="particle" style={{ left: '90%' }} />
      </div>
      
      {/* Top data stream line */}
      <div className="fixed top-0 left-0 right-0 h-[2px] z-50 overflow-hidden">
        <div className="h-full w-full bg-gradient-to-r from-transparent via-[#00fff5] to-transparent animate-[data-flow_3s_linear_infinite]" />
      </div>

      <div className="relative z-10 w-full max-w-md px-4">
        {/* Logo/Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center gap-3 mb-4">
            <div className="relative">
              <Terminal className="h-10 w-10 text-[#00fff5]" />
              <div className="absolute inset-0 h-10 w-10 text-[#00fff5] blur-md opacity-50">
                <Terminal className="h-10 w-10" />
              </div>
            </div>
            <h1 className="text-3xl font-bold tracking-tight">
              <span className="neon-text-cyan">NEXUS</span>
              <span className="text-[#ff00ff]"> TERMINAL</span>
            </h1>
          </div>
          <p className="text-muted-foreground text-sm">
            Access your trading command center
          </p>
        </div>

        {/* Login Card */}
        <div className="relative">
          {/* Glow effect */}
          <div className="absolute -inset-1 bg-gradient-to-r from-[#00fff5]/20 via-[#ff00ff]/20 to-[#00fff5]/20 rounded-2xl blur-xl opacity-50" />
          
          <div className="relative bg-card/90 backdrop-blur-xl border border-[#00fff5]/20 rounded-2xl p-8 shadow-2xl">
            {/* Header decoration */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2">
              <div className="relative flex items-center justify-center h-12 w-12 rounded-full bg-card border-2 border-[#00fff5]/50">
                <Lock className="h-5 w-5 text-[#00fff5]" />
                <div className="absolute inset-0 rounded-full border-2 border-[#00fff5]/30 animate-ping" />
              </div>
            </div>

            <div className="mt-4">
              <h2 className="text-xl font-bold text-center mb-2">
                <span className="text-[#00fff5]">SYSTEM</span> LOGIN
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

              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-xs uppercase tracking-wider text-muted-foreground">
                    Email Address
                  </Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      placeholder="trader@nexus.io"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="pl-10 bg-background/50 border-[#00fff5]/20 focus:border-[#00fff5]/50 focus:ring-[#00fff5]/20"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password" className="text-xs uppercase tracking-wider text-muted-foreground">
                    Password
                  </Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
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
                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      onClick={openForgotPassword}
                      className="text-xs text-[#00fff5] hover:text-[#00fff5]/80 font-medium transition-colors hover:underline"
                    >
                      Forgot password?
                    </button>
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={loading || googleLoading}
                  className="w-full bg-gradient-to-r from-[#00fff5] to-[#00d4aa] hover:from-[#00fff5]/90 hover:to-[#00d4aa]/90 text-black font-bold py-5 transition-all duration-300 hover:shadow-lg hover:shadow-[#00fff5]/20"
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      AUTHENTICATING...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Zap className="h-4 w-4" />
                      ACCESS TERMINAL
                    </span>
                  )}
                </Button>
              </form>

              {/* Divider */}
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-[#00fff5]/20" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">Or continue with</span>
                </div>
              </div>

              {/* Google Sign In */}
              <Button
                type="button"
                variant="outline"
                onClick={handleGoogleLogin}
                disabled={loading || googleLoading}
                className="w-full border-[#00fff5]/20 bg-background/50 hover:bg-[#00fff5]/10 hover:border-[#00fff5]/40 py-5 transition-all duration-300"
              >
                {googleLoading ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Connecting to Google...
                  </span>
                ) : (
                  <span className="flex items-center gap-3">
                    <GoogleIcon className="h-5 w-5" />
                    <span>Sign in with Google</span>
                  </span>
                )}
              </Button>

              <div className="mt-6 text-center">
                <p className="text-sm text-muted-foreground">
                  New to Nexus?{" "}
                  <Link
                    href="/signup"
                    className="text-[#00fff5] hover:text-[#00fff5]/80 font-medium transition-colors hover:underline"
                  >
                    Create Account
                  </Link>
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-xs text-muted-foreground">
            <span className="text-[#00fff5]/50">◆</span> Secure Connection Established <span className="text-[#00fff5]/50">◆</span>
          </p>
        </div>
      </div>

      <Dialog
        open={forgotOpen}
        onOpenChange={(open) => {
          setForgotOpen(open);
          if (!open) {
            setResetError(null);
            setResetSent(false);
          }
        }}
      >
        <DialogContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-[#00fff5]">Reset password</DialogTitle>
            <DialogDescription>
              {resetSent
                ? "Check your inbox for a link to choose a new password. If it doesn’t arrive in a few minutes, check spam or try again."
                : "We’ll email a secure link to set a new password. For your security, we don’t confirm whether that address is registered."}
            </DialogDescription>
          </DialogHeader>

          {!resetSent ? (
            <form onSubmit={handlePasswordReset} className="space-y-4">
              {resetError && (
                <div className="p-3 rounded-lg bg-[#ff3366]/10 border border-[#ff3366]/30 flex items-center gap-2 text-sm text-[#ff3366]">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  {resetError}
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="reset-email" className="text-xs uppercase tracking-wider text-muted-foreground">
                  Email
                </Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="reset-email"
                    type="email"
                    autoComplete="email"
                    placeholder="trader@nexus.io"
                    value={resetEmail}
                    onChange={(e) => setResetEmail(e.target.value)}
                    required
                    className="pl-10 bg-background/50 border-[#00fff5]/20 focus:border-[#00fff5]/50"
                  />
                </div>
              </div>
              <DialogFooter className="gap-2 sm:gap-0">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setForgotOpen(false)}
                  className="border-[#00fff5]/20"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={resetLoading}
                  className="bg-gradient-to-r from-[#00fff5] to-[#00d4aa] text-black font-semibold hover:from-[#00fff5]/90 hover:to-[#00d4aa]/90"
                >
                  {resetLoading ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Sending…
                    </span>
                  ) : (
                    "Send reset link"
                  )}
                </Button>
              </DialogFooter>
            </form>
          ) : (
            <DialogFooter>
              <Button
                type="button"
                onClick={() => setForgotOpen(false)}
                className="w-full bg-gradient-to-r from-[#00fff5] to-[#00d4aa] text-black font-semibold"
              >
                Done
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
