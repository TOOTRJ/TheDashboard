"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Terminal, Zap, Lock, Mail, Eye, EyeOff, AlertCircle, Loader2, User, CheckCircle } from "lucide-react";

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

export default function SignupPage() {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [googleLoading, setGoogleLoading] = React.useState(false);
  const [success, setSuccess] = React.useState(false);
  const router = useRouter();
  const supabase = createClient();

  const handleSignup = async (e: React.FormEvent) => {
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
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            display_name: displayName || email.split("@")[0],
          },
        },
      });

      if (error) {
        setError(error.message);
      } else {
        setSuccess(true);
        // If email confirmation is disabled, redirect directly
        setTimeout(() => {
          router.push("/");
          router.refresh();
        }, 2000);
      }
    } catch {
      setError("An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignup = async () => {
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

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
        {/* Background effects */}
        <div className="aurora-bg" aria-hidden="true" />
        <div className="fixed inset-0 synthwave-grid pointer-events-none opacity-30" />
        <div className="fixed inset-0 bg-gradient-to-br from-[#00fff5]/5 via-transparent to-[#ff00ff]/5 pointer-events-none" />

        <div className="relative z-10 w-full max-w-md px-4 text-center">
          <div className="relative">
            <div className="absolute -inset-1 bg-gradient-to-r from-[#39ff14]/20 via-[#00fff5]/20 to-[#39ff14]/20 rounded-2xl blur-xl opacity-50" />
            
            <div className="relative bg-card/90 backdrop-blur-xl border border-[#39ff14]/30 rounded-2xl p-8 shadow-2xl">
              <div className="flex items-center justify-center mb-6">
                <div className="relative h-16 w-16 rounded-full bg-[#39ff14]/10 flex items-center justify-center">
                  <CheckCircle className="h-8 w-8 text-[#39ff14]" />
                  <div className="absolute inset-0 rounded-full border-2 border-[#39ff14]/30 animate-ping" />
                </div>
              </div>
              
              <h2 className="text-xl font-bold mb-2">
                <span className="text-[#39ff14]">ACCOUNT</span> CREATED
              </h2>
              <p className="text-muted-foreground text-sm mb-4">
                Welcome to Nexus Terminal! Redirecting you to the dashboard...
              </p>
              
              <div className="flex items-center justify-center gap-1">
                <div className="h-2 w-2 rounded-full bg-[#39ff14] animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="h-2 w-2 rounded-full bg-[#39ff14] animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="h-2 w-2 rounded-full bg-[#39ff14] animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

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
        <div className="h-full w-full bg-gradient-to-r from-transparent via-[#ff00ff] to-transparent animate-[data-flow_3s_linear_infinite]" />
      </div>

      <div className="relative z-10 w-full max-w-md px-4 py-8">
        {/* Logo/Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center gap-3 mb-4">
            <div className="relative">
              <Terminal className="h-10 w-10 text-[#ff00ff]" />
              <div className="absolute inset-0 h-10 w-10 text-[#ff00ff] blur-md opacity-50">
                <Terminal className="h-10 w-10" />
              </div>
            </div>
            <h1 className="text-3xl font-bold tracking-tight">
              <span className="neon-text-cyan">NEXUS</span>
              <span className="text-[#ff00ff]"> TERMINAL</span>
            </h1>
          </div>
          <p className="text-muted-foreground text-sm">
            Initialize your trading profile
          </p>
        </div>

        {/* Signup Card */}
        <div className="relative">
          {/* Glow effect */}
          <div className="absolute -inset-1 bg-gradient-to-r from-[#ff00ff]/20 via-[#00fff5]/20 to-[#ff00ff]/20 rounded-2xl blur-xl opacity-50" />
          
          <div className="relative bg-card/90 backdrop-blur-xl border border-[#ff00ff]/20 rounded-2xl p-8 shadow-2xl">
            {/* Header decoration */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2">
              <div className="relative flex items-center justify-center h-12 w-12 rounded-full bg-card border-2 border-[#ff00ff]/50">
                <User className="h-5 w-5 text-[#ff00ff]" />
                <div className="absolute inset-0 rounded-full border-2 border-[#ff00ff]/30 animate-ping" />
              </div>
            </div>

            <div className="mt-4">
              <h2 className="text-xl font-bold text-center mb-2">
                <span className="text-[#ff00ff]">NEW</span> OPERATIVE
              </h2>
              <div className="flex items-center gap-2 justify-center mb-6">
                <div className="h-px flex-1 bg-gradient-to-r from-transparent to-[#ff00ff]/30" />
                <Zap className="h-3 w-3 text-[#ff00ff]" />
                <div className="h-px flex-1 bg-gradient-to-l from-transparent to-[#ff00ff]/30" />
              </div>

              {error && (
                <div className="mb-4 p-3 rounded-lg bg-[#ff3366]/10 border border-[#ff3366]/30 flex items-center gap-2 text-sm text-[#ff3366]">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  {error}
                </div>
              )}

              <form onSubmit={handleSignup} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="displayName" className="text-xs uppercase tracking-wider text-muted-foreground">
                    Display Name (Optional)
                  </Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="displayName"
                      type="text"
                      placeholder="ShadowTrader"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      className="pl-10 bg-background/50 border-[#ff00ff]/20 focus:border-[#ff00ff]/50 focus:ring-[#ff00ff]/20"
                    />
                  </div>
                </div>

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
                      className="pl-10 bg-background/50 border-[#ff00ff]/20 focus:border-[#ff00ff]/50 focus:ring-[#ff00ff]/20"
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
                      className="pl-10 pr-10 bg-background/50 border-[#ff00ff]/20 focus:border-[#ff00ff]/50 focus:ring-[#ff00ff]/20"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground">Minimum 6 characters</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirmPassword" className="text-xs uppercase tracking-wider text-muted-foreground">
                    Confirm Password
                  </Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="confirmPassword"
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      className="pl-10 bg-background/50 border-[#ff00ff]/20 focus:border-[#ff00ff]/50 focus:ring-[#ff00ff]/20"
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={loading || googleLoading}
                  className="w-full bg-gradient-to-r from-[#ff00ff] to-[#cc00cc] hover:from-[#ff00ff]/90 hover:to-[#cc00cc]/90 text-white font-bold py-5 transition-all duration-300 hover:shadow-lg hover:shadow-[#ff00ff]/20"
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      INITIALIZING...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Zap className="h-4 w-4" />
                      CREATE ACCOUNT
                    </span>
                  )}
                </Button>
              </form>

              {/* Divider */}
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-[#ff00ff]/20" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">Or continue with</span>
                </div>
              </div>

              {/* Google Sign Up */}
              <Button
                type="button"
                variant="outline"
                onClick={handleGoogleSignup}
                disabled={loading || googleLoading}
                className="w-full border-[#ff00ff]/20 bg-background/50 hover:bg-[#ff00ff]/10 hover:border-[#ff00ff]/40 py-5 transition-all duration-300"
              >
                {googleLoading ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Connecting to Google...
                  </span>
                ) : (
                  <span className="flex items-center gap-3">
                    <GoogleIcon className="h-5 w-5" />
                    <span>Sign up with Google</span>
                  </span>
                )}
              </Button>

              <div className="mt-6 text-center">
                <p className="text-sm text-muted-foreground">
                  Already have access?{" "}
                  <Link
                    href="/login"
                    className="text-[#ff00ff] hover:text-[#ff00ff]/80 font-medium transition-colors hover:underline"
                  >
                    Sign In
                  </Link>
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-xs text-muted-foreground">
            <span className="text-[#ff00ff]/50">◆</span> Encrypted Registration <span className="text-[#ff00ff]/50">◆</span>
          </p>
        </div>
      </div>
    </div>
  );
}
