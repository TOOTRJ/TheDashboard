import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { browserEnvironment } from "../scripts/browser-fixture.mjs";

const production = { VERCEL: "1", VERCEL_ENV: "production", VERCEL_TARGET_ENV: "production",
  VERCEL_PROJECT_ID: "prj_wFUe9k9USVreOQcmQKNWRAVsx5fH",
  NEXT_PUBLIC_SUPABASE_URL: "https://fxpxsciltakyypunglzr.supabase.co",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "fixture-production-key-with-no-access" };
const offline = { CI: "true", DASHBOARD_OFFLINE_BUILD: "1",
  NEXT_PUBLIC_SUPABASE_URL: "https://dashboard-ci.invalid",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "dashboard-ci-fake-public-key",
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_dashboard_ci_fake",
  SUPABASE_SERVICE_ROLE_KEY: "dashboard-ci-fake-secret-with-no-access" };

function load(environment) {
  const source = fs.readFileSync(new URL("../next.config.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, { exports, URL, process: { env: environment },
    require(name) {
      assert.equal(name, "next/constants");
      return { PHASE_PRODUCTION_BUILD: "phase-production-build" };
    },
    fetch() { throw new Error("Network forbidden"); },
  });
  return exports;
}
function accepts(environment, expected) {
  const policy = load(environment);
  assert.equal(policy.assertDashboardBuildTarget(environment), expected);
  assert.doesNotThrow(() => policy.default("phase-production-build"));
}
function refuses(environment) {
  const policy = load(environment);
  assert.throws(() => policy.assertDashboardBuildTarget(environment), /Dashboard/);
  assert.throws(() => policy.default("phase-production-build"), /Dashboard/);
}

test("the exact Dashboard production configuration is admitted", () => {
  accepts(production, "production");
  const noOptionalTarget = { ...production };
  delete noOptionalTarget.VERCEL_TARGET_ENV;
  accepts(noOptionalTarget, "production");
});

test("production rejects missing, empty and mismatched database or project metadata", () => {
  for (const override of [
    { NEXT_PUBLIC_SUPABASE_URL: undefined }, { NEXT_PUBLIC_SUPABASE_URL: "" },
    { NEXT_PUBLIC_SUPABASE_URL: "https://another-project.supabase.co" },
    { NEXT_PUBLIC_SUPABASE_URL: production.NEXT_PUBLIC_SUPABASE_URL + "/" },
    { NEXT_PUBLIC_SUPABASE_ANON_KEY: undefined }, { NEXT_PUBLIC_SUPABASE_ANON_KEY: "   " },
    { VERCEL: undefined }, { VERCEL: "" }, { VERCEL: "0" }, { VERCEL: "false" },
    { VERCEL_PROJECT_ID: undefined }, { VERCEL_PROJECT_ID: "another-project" }, { VERCEL_PROJECT_ID: "" },
    { VERCEL_TARGET_ENV: "staging" }, { VERCEL_TARGET_ENV: "" },
  ]) refuses({ ...production, ...override });
});

test("preview, development and custom hosted builds reject production settings", () => {
  for (const name of ["preview", "development", "staging", "", undefined]) {
    refuses({ ...production, VERCEL_ENV: name });
  }
});

test("offline marker cannot bypass any detected hosted environment", () => {
  for (const key of ["VERCEL", "VERCEL_ENV", "VERCEL_TARGET_ENV", "VERCEL_URL",
    "VERCEL_DEPLOYMENT_ID", "VERCEL_PROJECT_ID"]) {
    for (const value of ["preview", "production", "", "1"]) refuses({ ...offline, [key]: value });
  }
});

test("only the isolated helper's exact fake configuration is admitted offline", () => {
  accepts(offline, "offline");
  for (const override of [
    { CI: undefined }, { CI: "false" }, { DASHBOARD_OFFLINE_BUILD: undefined },
    { NEXT_PUBLIC_SUPABASE_URL: production.NEXT_PUBLIC_SUPABASE_URL },
    { NEXT_PUBLIC_SUPABASE_ANON_KEY: production.NEXT_PUBLIC_SUPABASE_ANON_KEY },
    { NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_fixture_real_like" },
    { SUPABASE_SERVICE_ROLE_KEY: "fixture-private-key-with-no-access" },
    { SUPABASE_SECRET_KEY: "fixture-private-key-with-no-access" },
    { NEXT_PUBLIC_SUPABASE_EXTRA_KEY: "fixture-with-no-access" },
    { NEXT_PUBLIC_VN_API_URL: "https://worker.example.test" },
    { JUPITER_API_KEY: "fixture-with-no-access" }, { JUP_API_KEY: "fixture-with-no-access" },
    { BIRDEYE_API_KEY: "fixture-with-no-access" }, { VN_SOLANA_RPC_URL: "https://rpc.example.test" },
  ]) refuses({ ...offline, ...override });
});

test("missing hosted context never admits a real-configuration production artifact", () => {
  refuses({ NEXT_PUBLIC_SUPABASE_URL: production.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: production.NEXT_PUBLIC_SUPABASE_ANON_KEY });
  refuses({});
});

test("error messages never disclose credential or connection values", () => {
  const environment = { ...production, VERCEL_ENV: "preview" };
  try { load(environment).default("phase-production-build"); assert.fail("must refuse"); }
  catch (error) {
    assert.match(error.message, /^Dashboard/);
    assert.equal(error.message.includes(environment.NEXT_PUBLIC_SUPABASE_ANON_KEY), false);
    assert.equal(error.message.includes(environment.NEXT_PUBLIC_SUPABASE_URL), false);
  }
});

test("development server and built-artifact startup do not compile a new production bundle", () => {
  for (const phase of ["phase-development-server", "phase-production-server"]) {
    assert.doesNotThrow(() => load({}).default(phase));
  }
});

const fixtureOrigin = "http://127.0.0.1:12345";
const browserFixture = { ...offline, DASHBOARD_BROWSER_FIXTURE_BUILD: "1",
  NEXT_PUBLIC_SUPABASE_URL: fixtureOrigin,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "dashboard-browser-fixture-public-key",
  SUPABASE_SERVICE_ROLE_KEY: "dashboard-browser-fixture-service-role-fake",
  NEXT_PUBLIC_VN_API_URL: fixtureOrigin,
  NEXT_PUBLIC_VN_WS_URL: "ws://127.0.0.1:12345/ws",
  NEXT_PUBLIC_VN_SERVICE_MODE: "browser-fixture-legacy",
  API_SECRET_KEY: "dashboard-browser-fixture-api-key",
};

test("the compiled browser fixture admits only exact loopback and literal fake credentials", () => {
  accepts(browserFixture, "browser-fixture");
  for (const override of [
    { DASHBOARD_BROWSER_FIXTURE_BUILD: undefined }, { DASHBOARD_BROWSER_FIXTURE_BUILD: "0" },
    { DASHBOARD_OFFLINE_BUILD: undefined }, { CI: "false" },
    { NEXT_PUBLIC_SUPABASE_URL: production.NEXT_PUBLIC_SUPABASE_URL },
    { NEXT_PUBLIC_SUPABASE_ANON_KEY: production.NEXT_PUBLIC_SUPABASE_ANON_KEY },
    { SUPABASE_SERVICE_ROLE_KEY: "fixture-private-key-with-no-access" },
    { API_SECRET_KEY: "fixture-private-key-with-no-access" },
    { NEXT_PUBLIC_VN_API_URL: "https://real-worker.example.test" },
    { NEXT_PUBLIC_VN_WS_URL: "wss://real-worker.example.test/ws" },
    { NEXT_PUBLIC_VN_SERVICE_MODE: "paper-v5" },
    { VERCEL: "1" }, { VERCEL_ENV: "preview" }, { VERCEL_TARGET_ENV: "staging" },
    { VERCEL_ENV: "production" }, { VERCEL_PROJECT_ID: production.VERCEL_PROJECT_ID },
    { JUPITER_API_KEY: "fixture-private-key-with-no-access" },
  ]) refuses({ ...browserFixture, ...override });
});

test("browser fixture origin cannot become an external, implicit-port or noncanonical backend", () => {
  for (const origin of ["http://127.0.0.1", "http://127.0.0.1:0", "http://localhost:12345",
    "https://127.0.0.1:12345", "http://127.0.0.1:12345/", "http://127.0.0.1:12345/path",
    "http://user@127.0.0.1:12345", "http://127.0.0.1:12345?key=fixture",
    "http://127.0.0.1:12345#fixture", "http://127.0.0.1.example.test:12345"] ) {
    refuses({ ...browserFixture, NEXT_PUBLIC_SUPABASE_URL: origin });
  }
});

test("the actual browser helper supplies the exact admitted synthetic build context", () => {
  const context = browserEnvironment("/private/tmp/dashboard-owned-fixture-test", "http://127.0.0.1:23456", {
    ...production, DASHBOARD_OFFLINE_BUILD: "0", JUPITER_API_KEY: "fixture-never-inherit",
    BIRDEYE_API_KEY: "fixture-never-inherit", API_SECRET_KEY: "fixture-never-inherit",
  });
  accepts(context, "browser-fixture");
  assert.equal(Object.values(context).some(value => value.includes("fixture-never-inherit")), false);
});
