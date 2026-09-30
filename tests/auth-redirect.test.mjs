import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { getSafeAuthRedirect } from "../src/lib/auth/redirect.ts";

const callback = "https://dashboard.example/auth/callback?code=test";

test("login redirects retain a local path, query, and fragment", () => {
  assert.equal(
    getSafeAuthRedirect(callback, "/probes?view=history#colony").href,
    "https://dashboard.example/probes?view=history#colony",
  );
});

test("external, protocol-relative, backslash, and control-character destinations fail closed", () => {
  for (const next of [null, "", "https://attacker.example", "//attacker.example",
    "/\\attacker.example", "\\\\attacker.example", "/\n/attacker.example",
    "/\t/attacker.example", "javascript:alert(1)", "probes"]) {
    assert.equal(getSafeAuthRedirect(callback, next).href, "https://dashboard.example/");
  }
});

test("encoded separators are not decoded a second time after URLSearchParams", () => {
  const url = new URL(callback);
  url.searchParams.set("next", "/%2f%2fattacker.example");
  const target = getSafeAuthRedirect(url.href, url.searchParams.get("next"));
  assert.equal(target.origin, "https://dashboard.example");
  assert.equal(target.pathname, "/%2f%2fattacker.example");
});

test("development redirects preserve the actual request origin and port", () => {
  assert.equal(
    getSafeAuthRedirect("http://localhost:3000/auth/callback", "/probes").href,
    "http://localhost:3000/probes",
  );
});

test("successful callback ignores a forged forwarded host", async () => {
  const source = fs.readFileSync(new URL("../src/app/auth/callback/route.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  let exchanges = 0;
  const modules = {
    "@supabase/ssr": { createServerClient: () => ({ auth: {
      exchangeCodeForSession: async (code) => {
        assert.equal(code, "test");
        exchanges++;
        return { error: null };
      },
    } }) },
    "next/headers": { cookies: async () => ({ getAll: () => [], set: () => {} }) },
    "next/server": { NextResponse: { redirect: (target) => new URL(target) } },
    "@/lib/auth/redirect": { getSafeAuthRedirect },
  };
  vm.runInNewContext(compiled, {
    exports, URL,
    process: { env: { NODE_ENV: "production", NEXT_PUBLIC_SUPABASE_URL: "https://offline.invalid",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-only" } },
    require: (name) => {
      assert.ok(Object.hasOwn(modules, name), `Unexpected dependency: ${name}`);
      return modules[name];
    },
    fetch: () => { throw new Error("Network forbidden in callback tests"); },
  });
  const result = await exports.GET(new Request(`${callback}&next=%2Fprobes`, {
    headers: { "x-forwarded-host": "attacker.example" },
  }));
  assert.equal(exchanges, 1);
  assert.equal(result.href, "https://dashboard.example/probes");
});
