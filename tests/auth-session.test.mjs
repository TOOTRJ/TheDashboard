import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { createSessionGuard, sessionIdentity } from "../src/lib/auth/session-guard.ts";

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const flush = () => new Promise((resolve) => setImmediate(resolve));
const session = (id, token = `test-token-${id}`) => ({ user: { id }, access_token: token });

// Exercise the real provider with deterministic React state and deferred SDK calls.
// No renderer package, Supabase project, network, browser, or real token is involved.
function providerHarness() {
  const states = [], userRead = deferred(), sessionRead = deferred(), signOut = deferred(), profiles = [];
  let cursor = 0, effects = [], listener, sessionReads = 0, signOutCalls = 0;
  const supabase = {
    auth: {
      getUser: () => userRead.promise,
      getSession: () => { sessionReads++; return sessionRead.promise; },
      signOut: () => { signOutCalls++; return signOut.promise; },
      onAuthStateChange: (callback) => {
        listener = callback;
        return { data: { subscription: { unsubscribe: () => { listener = undefined; } } } };
      },
    },
    from(table) {
      assert.equal(table, "profiles");
      const row = { id: null, ...deferred() };
      return {
        select() { return this; },
        eq(field, value) { assert.equal(field, "id"); row.id = value; return this; },
        maybeSingle() { profiles.push(row); return row.promise; },
      };
    },
  };
  const react = {
    createContext: () => ({ Provider: "Provider" }),
    useMemo: (factory) => factory(),
    useCallback: (callback) => callback,
    useEffect: (effect) => effects.push(effect),
    useState(initial) {
      const index = cursor++;
      if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
      return [states[index], (next) => { states[index] = typeof next === "function" ? next(states[index]) : next; }];
    },
  };
  const modules = {
    react, "react/jsx-runtime": { jsx: (_type, props) => props },
    "@/lib/supabase/client": { createClient: () => supabase },
    "@/lib/auth/session-guard": { createSessionGuard, sessionIdentity },
  };
  const exports = {};
  const source = fs.readFileSync(new URL("../src/components/auth/AuthProvider.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(compiled, {
    exports, queueMicrotask,
    require(name) { assert.ok(Object.hasOwn(modules, name), `Unexpected dependency ${name}`); return modules[name]; },
    fetch() { throw new Error("Network is forbidden in auth tests"); },
  });
  function render() {
    cursor = 0; effects = [];
    return exports.AuthProvider({ children: null }).value;
  }
  render();
  assert.equal(effects.length, 1);
  const cleanup = effects[0]();
  return {
    current: render, userRead, sessionRead, signOut, profiles, cleanup,
    emit: (event, value) => listener?.(event, value),
    sessionReads: () => sessionReads, signOutCalls: () => signOutCalls,
  };
}

test("local logout clears authority before network completion and late bootstrap/profile/refresh cannot restore it", async () => {
  const h = providerHarness();
  h.emit("SIGNED_IN", session("A"));
  await flush();
  assert.equal(h.profiles.length, 1);
  const pending = h.current().signOut();
  assert.equal(h.signOutCalls(), 1);
  assert.equal(h.current().user, null);
  assert.equal(h.current().session, null);
  assert.equal(h.current().profile, null);
  assert.equal(h.current().loading, false);
  h.userRead.resolve({ data: { user: { id: "A" } } });
  h.profiles[0].resolve({ data: { id: "A", full_name: "Old account" }, error: null });
  h.emit("TOKEN_REFRESHED", session("A", "late-token"));
  h.emit("INITIAL_SESSION", session("A"));
  h.emit("SIGNED_IN", session("A")); // SDK focus/reestablishment during pending logout.
  await flush();
  assert.equal(h.sessionReads(), 0);
  assert.equal(h.current().user, null);
  assert.equal(h.current().profile, null);
  h.signOut.resolve({ error: null });
  await pending;
  h.emit("SIGNED_OUT", null);
  h.emit("SIGNED_IN", session("B"));
  assert.equal(h.current().user.id, "B");
  h.cleanup();
});

test("failed SDK sign-out blocks the retired session but permits a deliberate new login", async () => {
  const h = providerHarness();
  h.emit("SIGNED_IN", session("A"));
  const pending = h.current().signOut();
  h.signOut.resolve({ error: { message: "offline" } });
  await pending;
  h.emit("SIGNED_IN", session("A"));
  assert.equal(h.current().user, null);
  assert.equal(h.current().session, null);
  h.emit("SIGNED_IN", session("A", "new-login-token"));
  assert.equal(h.current().user.id, "A");
  assert.equal(h.current().session.access_token, "new-login-token");
  h.cleanup();
});

test("retired Supabase session IDs block reestablishment even after JWT refresh, while a new login recovers", async () => {
  const token = (id, expiry) => `test.${Buffer.from(JSON.stringify({ session_id: id, exp: expiry })).toString("base64url")}.signature`;
  const h = providerHarness();
  h.emit("SIGNED_IN", session("A", token("old-session", 1000)));
  const pending = h.current().signOut();
  h.signOut.resolve({ error: { message: "offline" } });
  await pending;
  h.emit("SIGNED_IN", session("A", token("old-session", 2000)));
  assert.equal(h.current().user, null);
  h.emit("SIGNED_IN", session("A", token("new-session", 2000)));
  assert.equal(h.current().user.id, "A");
  h.cleanup();
});

test("bootstrap getSession finishing after logout cannot restore the previously verified user", async () => {
  const h = providerHarness();
  h.userRead.resolve({ data: { user: { id: "A" } } });
  await flush();
  assert.equal(h.sessionReads(), 1);
  const pending = h.current().signOut();
  h.sessionRead.resolve({ data: { session: session("A") } });
  await flush();
  assert.equal(h.current().session, null);
  assert.equal(h.current().user, null);
  h.signOut.resolve({ error: null });
  await pending;
  h.cleanup();
});

test("switching accounts ignores old profile and bootstrap results", async () => {
  const h = providerHarness();
  h.emit("SIGNED_IN", session("A")); await flush();
  h.emit("SIGNED_IN", session("B")); await flush();
  assert.equal(h.profiles.length, 2);
  h.profiles[1].resolve({ data: { id: "B", full_name: "Current account" }, error: null });
  await flush();
  h.profiles[0].resolve({ data: { id: "A", full_name: "Old account" }, error: null });
  h.userRead.resolve({ data: { user: { id: "A" } } });
  await flush();
  assert.equal(h.current().user.id, "B");
  assert.equal(h.current().profile.id, "B");
  assert.equal(h.sessionReads(), 0);
  h.cleanup();
});

test("profile refresh and pending initialization cannot write after provider cleanup", async () => {
  const h = providerHarness();
  h.emit("SIGNED_IN", session("A")); await flush();
  const refresh = h.current().refreshProfile();
  assert.equal(h.profiles.length, 2);
  h.cleanup();
  h.profiles[0].resolve({ data: { id: "A", full_name: "Old profile" }, error: null });
  h.profiles[1].resolve({ data: { id: "A", full_name: "Late refresh" }, error: null });
  h.userRead.resolve({ data: { user: { id: "A" } } });
  await refresh; await flush();
  assert.equal(h.current().profile, null);
  assert.equal(h.sessionReads(), 0);
});

test("unauthenticated or failed bootstrap exits loading without granting access", async () => {
  for (const failure of [false, true]) {
    const h = providerHarness();
    if (failure) h.userRead.reject(new Error("offline"));
    else h.userRead.resolve({ data: { user: null } });
    await flush();
    assert.equal(h.current().loading, false);
    assert.equal(h.current().user, null);
    assert.equal(h.current().session, null);
    h.cleanup();
  }
});
