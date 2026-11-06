import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { createClient } from "@supabase/supabase-js";
import * as transport from "../src/lib/probes/transport.ts";
import * as execution from "../src/lib/probes/execution.ts";
import * as signals from "../src/lib/probes/signal-profile.ts";

const source = fs.readFileSync(new URL("../src/lib/probes/probes-supabase.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const probeId = "probe-A";
const trade = (i, extra = {}) => ({ id: String(i).padStart(6, "0"), probe_id: probeId, opened_at: "2026-01-01T00:00:00.000001Z", pair: "SOL/USDC", ...extra });
function api(client, globals = {}) {
  const exports = {};
  const modules = { "@/lib/supabase/client": { createClient: () => client }, "./transport": transport, "./execution": execution, "./signal-profile": signals };
  vm.runInNewContext(compiled, { exports, AbortController, setTimeout, clearTimeout,
    require(name) { assert.ok(Object.hasOwn(modules, name)); return modules[name]; }, ...globals });
  return exports;
}
function harness({ rows = [], cap = 200, response, globals } = {}) {
  const calls = [];
  const client = { from(table) {
    const call = { table, orders: [] }; calls.push(call);
    return {
      select(fields, options) { call.fields = fields; call.options = options; return this; },
      eq(column, value) { call.filter = [column, value]; return this; },
      order(column, options) { call.orders.push([column, options]); return this; },
      range(from, to) { call.range = [from, to]; return this; },
      abortSignal(signal) { call.signal = signal; return this; },
      then(resolve, reject) {
        const normal = { data: rows.slice(call.range[0], Math.min(call.range[1] + 1, call.range[0] + cap)), count: rows.length, error: null };
        return Promise.resolve().then(() => response ? response(call, normal) : normal).then(resolve, reject);
      },
    };
  } };
  return { calls, api: api(client, globals) };
}
const rejects = (h, signal) => assert.rejects(h.api.fetchProbeTrades(probeId, signal), error => {
  assert.equal(error.name, "ProbeDataError"); assert.match(error.message, /trade history/);
  assert.ok(!error.message.includes("private")); return true;
});

test("installed SDK retrieves all 1001 trades under a 37-row cap and deterministic timestamp ties", async () => {
  const rows = Array.from({ length: 1001 }, (_, i) => trade(i));
  const requests = [];
  const client = createClient("https://offline.invalid", "fake-key", { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }, global: {
    fetch: async (url, options) => {
      const u = new URL(url); requests.push(u);
      assert.equal(u.pathname, "/rest/v1/vn_trades");
      assert.equal(u.searchParams.get("probe_id"), "eq." + probeId);
      assert.equal(u.searchParams.get("order"), "opened_at.desc,id.asc");
      assert.equal(u.searchParams.get("limit"), "200");
      assert.ok(new Headers(options.headers).get("prefer").includes("count=exact"));
      assert.ok(options.signal instanceof AbortSignal);
      const offset = Number(u.searchParams.get("offset"));
      const data = rows.slice(offset, offset + 37);
      return new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json", "content-range": offset + "-" + (offset + data.length - 1) + "/1001" } });
    },
  } });
  const result = await api(client).fetchProbeTrades(probeId);
  assert.deepEqual(Array.from(result, row => row.id), rows.map(row => row.id));
  assert.equal(requests.length, 28);
});

test("empty trade history is distinct from failure; missing selected identity makes no query", async () => {
  const h = harness();
  assert.deepEqual(Array.from(await h.api.fetchProbeTrades(probeId)), []);
  for (const id of [undefined, "", " "]) await assert.rejects(h.api.fetchProbeTrades(id), /selected probe/);
  assert.equal(h.calls.length, 1);
});

for (const count of [null, undefined, -1, 1.5, NaN, Infinity, 50_001, "1"]) {
  test("invalid exact trade count refuses: " + String(count), async () => {
    const h = harness({ response: (_call, normal) => ({ ...normal, count }) });
    await rejects(h); assert.equal(h.calls.length, 1);
  });
}

for (const fault of ["drift", "gap", "duplicate", "foreign", "late-error"]) {
  test("a later " + fault + " cannot publish partial trade history", async () => {
    const h = harness({ rows: [trade(1), trade(2), trade(3)], cap: 1, response: (call, normal) => {
      if (call.range[0] !== 1) return normal;
      if (fault === "drift") return { ...normal, count: 4 };
      if (fault === "gap") return { ...normal, data: [] };
      if (fault === "duplicate") return { ...normal, data: [trade(1)] };
      if (fault === "foreign") return { ...normal, data: [trade(2, { probe_id: "probe-B" })] };
      return { data: null, count: null, error: { message: "private-database-token" } };
    } });
    await rejects(h); assert.equal(h.calls.length, 2);
  });
}

test("oversized pages, malformed identities/times and count underruns refuse", async () => {
  for (const data of [Array.from({ length: 201 }, (_, i) => trade(i)), [trade(1, { id: "" })], [trade(1, { opened_at: "invalid" })], [null]]) {
    await rejects(harness({ response: () => ({ data, count: 201, error: null }) }));
  }
  await rejects(harness({ rows: [trade(1)], response: (_call, normal) => ({ ...normal, count: 0 }) }));
});

test("the finite page budget refuses a one-row server cap without returning 500 partial rows", async () => {
  const h = harness({ rows: Array.from({ length: 501 }, (_, i) => trade(i)), cap: 1 });
  await rejects(h); assert.equal(h.calls.length, 500);
});

test("external cancellation prevents initial dispatch and aborts a real SDK pending query", async () => {
  const already = new AbortController(); already.abort();
  const empty = harness(); await rejects(empty, already.signal); assert.equal(empty.calls.length, 0);
  let dispatched, observedAbort = false;
  const started = new Promise(resolve => { dispatched = resolve; });
  const client = createClient("https://offline.invalid", "fake-key", { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }, global: {
    fetch: async (_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => { observedAbort = true; reject(new DOMException("private aborted transport", "AbortError")); }, { once: true });
      dispatched();
    }),
  } });
  const abort = new AbortController();
  const pending = api(client).fetchProbeTrades(probeId, abort.signal);
  await started; abort.abort();
  await assert.rejects(pending, error => error.name === "ProbeDataError" && !error.message.includes("private"));
  assert.equal(observedAbort, true);
});

test("the owned deadline cancels the actual pending SDK transport and clears its timer", async () => {
  let timeout, dispatched, observedAbort = false, cleared = false;
  const started = new Promise(resolve => { dispatched = resolve; });
  const client = createClient("https://offline.invalid", "fake-key", { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }, global: {
    fetch: async (_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => { observedAbort = true; reject(new DOMException("aborted", "AbortError")); }, { once: true });
      dispatched();
    }),
  } });
  const pending = api(client, { setTimeout(fn, ms) { assert.equal(ms, 8000); timeout = fn; return 7; }, clearTimeout(id) { assert.equal(id, 7); cleared = true; } }).fetchProbeTrades(probeId);
  await started; timeout(); await assert.rejects(pending, error => error.name === "ProbeDataError");
  assert.equal(observedAbort, true); assert.equal(cleared, true);
});

test("trade-view disposal aborts its request and cannot publish late data or errors", async () => {
  for (const rejectLate of [false, true]) {
    let cleanup, requestSignal, finish;
    const updates = [];
    const react = { useState(initial) { return [initial, value => updates.push(value)]; }, useEffect(fn) { cleanup = fn(); } };
    const jsx = (type, props) => ({ type, props });
    const components = names => Object.fromEntries(names.map(name => [name, name]));
    const modules = {
      react, "react/jsx-runtime": { jsx, jsxs: jsx }, "@/lib/probes/execution": execution,
      "./TradeExecutionDetails": { TradeExecutionDetails: "Details" },
      "@/components/ui/table": components(["Table", "TableBody", "TableCell", "TableHead", "TableHeader", "TableRow"]),
      "@/components/ui/badge": { Badge: "Badge" }, "@/components/ui/button": { Button: "Button" },
      "@/lib/probes/probes-supabase": { fetchProbeTrades(id, signal) {
        assert.equal(id, probeId); requestSignal = signal;
        return new Promise((resolve, reject) => { finish = () => rejectLate ? reject(new Error("late private failure")) : resolve([trade(1)]); });
      } },
    };
    const exports = {};
    const code = ts.transpileModule(fs.readFileSync(new URL("../src/components/probes/TradeLog.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
    vm.runInNewContext(code, { exports, AbortController, require(name) { assert.ok(Object.hasOwn(modules, name)); return modules[name]; } });
    const wrapper = exports.TradeLog({ probeId }); wrapper.type(wrapper.props);
    assert.ok(requestSignal instanceof AbortSignal); assert.equal(requestSignal.aborted, false);
    const before = updates.length; cleanup(); assert.equal(requestSignal.aborted, true);
    finish(); await new Promise(resolve => setImmediate(resolve));
    assert.equal(updates.length, before);
  }
});
