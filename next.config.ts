import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

type BuildEnvironment = Record<string, string | undefined>;

const DASHBOARD_SUPABASE_URL = "https://fxpxsciltakyypunglzr.supabase.co";
const DASHBOARD_VERCEL_PROJECT = "prj_wFUe9k9USVreOQcmQKNWRAVsx5fH";
const OFFLINE_CONFIGURATION: BuildEnvironment = {
  NEXT_PUBLIC_SUPABASE_URL: "https://dashboard-ci.invalid",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "dashboard-ci-fake-public-key",
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_dashboard_ci_fake",
  SUPABASE_SERVICE_ROLE_KEY: "dashboard-ci-fake-secret-with-no-access",
};
const HOSTED_CONTEXT = ["VERCEL", "VERCEL_ENV", "VERCEL_TARGET_ENV", "VERCEL_URL",
  "VERCEL_DEPLOYMENT_ID", "VERCEL_PROJECT_ID"];

// NEXT_PUBLIC settings become browser bundle literals. Refuse unsafe builds
// before compilation; a request-time or browser UI guard cannot isolate them.
export function assertDashboardBuildTarget(environment: BuildEnvironment): "offline" | "browser-fixture" | "production" {
  if (environment.DASHBOARD_OFFLINE_BUILD === "1") {
    let expected = OFFLINE_CONFIGURATION;
    const browserFixture = environment.DASHBOARD_BROWSER_FIXTURE_BUILD === "1";
    if (browserFixture) {
      let origin: URL;
      try { origin = new URL(environment.NEXT_PUBLIC_SUPABASE_URL ?? ""); }
      catch { throw new Error("Dashboard browser fixtures require the owned loopback backend"); }
      if (origin.protocol !== "http:" || origin.hostname !== "127.0.0.1" ||
          !origin.port || Number(origin.port) < 1 || origin.origin !== environment.NEXT_PUBLIC_SUPABASE_URL) {
        throw new Error("Dashboard browser fixtures require the owned loopback backend");
      }
      // These public literals match the synthetic backend; they have no access.
      // The fixture harness separately owns the selected port and child processes.
      expected = { ...OFFLINE_CONFIGURATION,
        NEXT_PUBLIC_SUPABASE_URL: origin.origin,
        NEXT_PUBLIC_SUPABASE_ANON_KEY: "dashboard-browser-fixture-public-key",
        SUPABASE_SERVICE_ROLE_KEY: "dashboard-browser-fixture-service-role-fake",
        NEXT_PUBLIC_VN_API_URL: origin.origin,
        NEXT_PUBLIC_VN_WS_URL: origin.origin.replace("http:", "ws:") + "/ws",
        NEXT_PUBLIC_VN_SERVICE_MODE: "browser-fixture-legacy",
        API_SECRET_KEY: "dashboard-browser-fixture-api-key",
      };
    } else if (environment.DASHBOARD_BROWSER_FIXTURE_BUILD !== undefined) {
      throw new Error("Dashboard browser fixture build context is invalid");
    }
    const configuredKeys = Object.keys(environment).filter(key =>
      key.startsWith("NEXT_PUBLIC_SUPABASE_") || key.startsWith("SUPABASE_") ||
      key.startsWith("NEXT_PUBLIC_VN_") ||
      ["API_SECRET_KEY", "JUPITER_API_KEY", "JUP_API_KEY", "BIRDEYE_API_KEY", "VN_SOLANA_RPC_URL"].includes(key));
    if (environment.CI !== "true" || HOSTED_CONTEXT.some(key => environment[key] !== undefined) ||
        Object.entries(expected).some(([key, value]) => environment[key] !== value) ||
        configuredKeys.some(key => !Object.hasOwn(expected, key) || environment[key] !== expected[key])) {
      throw new Error("Dashboard offline builds require the isolated fake-configuration helper");
    }
    return browserFixture ? "browser-fixture" : "offline";
  }
  if (environment.DASHBOARD_BROWSER_FIXTURE_BUILD !== undefined ||
      environment.VERCEL !== "1" ||
      environment.VERCEL_ENV !== "production" ||
      (environment.VERCEL_TARGET_ENV !== undefined && environment.VERCEL_TARGET_ENV !== "production") ||
      environment.VERCEL_PROJECT_ID !== DASHBOARD_VERCEL_PROJECT ||
      environment.NEXT_PUBLIC_SUPABASE_URL !== DASHBOARD_SUPABASE_URL ||
      !environment.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim()) {
    throw new Error("Dashboard preview and unreviewed builds are blocked until database isolation is configured");
  }
  return "production";
}

const nextConfig: NextConfig = {};

export default function configuration(phase: string): NextConfig {
  if (phase === PHASE_PRODUCTION_BUILD) assertDashboardBuildTarget(process.env);
  return nextConfig;
}
