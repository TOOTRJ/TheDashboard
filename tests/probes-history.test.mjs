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
const owner = "owner-A";
const plain = (value) => JSON.parse(JSON.stringify(value));
const colony = (id, extra = {}) => ({ id, user_id: owner, mode: "simulation", strategy: "genetic_algorithm", status: "stopped", config: {}, started_at: "2026-01-02T00:00:00Z", stopped_at: "2026-01-03T00:00:00Z", ...extra });
const probe = (i, run_id = "legacy", extra = {}) => ({ id: String(i).padStart(6, "0"), user_id: owner, run_id, mode: "simulation", fitness_score: -10, created_at: "2026-01-01T00:00:00Z", ...extra });
function api(client, globals = {}) {
  const exports = {};
  const modules = { "@/lib/supabase/client": { createClient: () => client }, "./transport": transport, "./execution": execution, "./signal-profile": signals };
  vm.runInNewContext(compiled, { exports, AbortController, setTimeout, clearTimeout,
    require(name) { assert.ok(Object.hasOwn(modules, name)); return modules[name]; }, ...globals });
  return exports;
}
function harness({ colonies = [], probes = [], cap = 200, response, globals } = {}) {
  const calls = [];
  const client = { from(table) {
    const call = { table }; calls.push(call);
    return {
      select(fields, options) { call.fields = fields; call.options = options; return this; },
      eq(column, value) { call.filter = [column, value]; return this; },
      order(column, options) { call.order = [column, options]; return this; },
      range(from, to) { call.range = [from, to]; return this; },
      abortSignal(signal) { call.signal = signal; return this; },
      then(resolve, reject) {
        const rows = table === "vn_colonies" ? colonies : probes;
        const normal = { data: rows.slice(call.range[0], Math.min(call.range[1] + 1, call.range[0] + cap)), count: rows.length, error: null };
        return Promise.resolve().then(() => response ? response(call, normal, calls.length) : normal).then(resolve, reject);
      },
    };
  } };
  return { calls, api: api(client, globals) };
}
const rejects = (h, signal) => assert.rejects(h.api.fetchColonyRuns(owner, signal), error => {
  assert.equal(error.name, "ProbeDataError");
  assert.ok(!error.message.includes("private"));
  return true;
});

test("mixed 8-colony/497-probe history includes all 24 runs, 16 probe-only groups, and every member exactly once", async () => {
  const colonies = Array.from({ length: 8 }, (_, i) => colony(`run-${String(i).padStart(2, "0")}`));
  const probes = Array.from({ length: 497 }, (_, i) => probe(i, `run-${String(i % 24).padStart(2, "0")}`, { fitness_score: -100 + i / 100 }));
  const h = harness({ colonies, probes });
  const runs = plain(await h.api.fetchColonyRuns(owner));
  assert.equal(runs.length, 24);
  assert.equal(runs.filter(run => run.history_source === "probe_only").length, 16);
  assert.equal(new Set(runs.map(run => run.run_id)).size, 24);
  assert.equal(runs.reduce((sum, run) => sum + run.probe_count, 0), 497);
  for (const run of runs) {
    const members = probes.filter(p => p.run_id === run.run_id);
    assert.equal(run.probe_count, members.length);
    assert.equal(run.best_fitness, Math.max(...members.map(p => p.fitness_score)));
    if (run.history_source === "probe_only") {
      assert.equal(run.status, undefined); assert.equal(run.strategy, undefined);
      assert.equal(run.runtime, undefined); assert.equal(run.ended_at, null);
    }
  }
  assert.deepEqual(h.calls.map(call => call.range), [[0, 199], [0, 199], [200, 399], [400, 599]]);
  for (const call of h.calls) {
    assert.deepEqual(call.filter, ["user_id", owner]);
    assert.deepEqual(plain(call.options), { count: "exact" });
    assert.deepEqual(plain(call.order), ["id", { ascending: true }]);
    assert.ok(call.signal instanceof AbortSignal);
    assert.ok(!call.fields.includes("*"));
  }
});

test("history supports empty, colony-only and probe-only results without manufacturing authority", async () => {
  assert.deepEqual(plain(await harness().api.fetchColonyRuns(owner)), []);
  const [saved] = await harness({ colonies: [colony("saved")] }).api.fetchColonyRuns(owner);
  assert.equal(saved.history_source, "colony"); assert.equal(saved.probe_count, 0);
  const [legacy] = await harness({ probes: [probe(1)] }).api.fetchColonyRuns(owner);
  assert.equal(legacy.history_source, "probe_only"); assert.equal(legacy.status, undefined);
});

test("earliest probe time and negative best fitness survive the last page; mixed modes remain unknown", async () => {
  const h = harness({ cap: 1, probes: [probe(1, "legacy", { created_at: "2026-04-01T00:00:00Z", fitness_score: -5 }),
    probe(2, "legacy", { created_at: "2026-02-01T00:00:00Z", mode: "paper", fitness_score: -1 })] });
  const [run] = await h.api.fetchColonyRuns(owner);
  assert.equal(run.started_at, "2026-02-01T00:00:00Z"); assert.equal(run.best_fitness, -1);
  assert.equal(run.mode, "unknown"); assert.equal(run.ended_at, null);
});

test("display order is newest-first with exact run ID ties and saved timestamps take precedence", async () => {
  const h = harness({ colonies: [colony("a"), colony("z")], probes: [probe(1, "z", { created_at: "2027-01-01T00:00:00Z" }), probe(2, "legacy")] });
  const runs = await h.api.fetchColonyRuns(owner);
  assert.deepEqual(plain(runs.map(run => run.run_id)), ["a", "z", "legacy"]);
  assert.equal(runs[1].started_at, "2026-01-02T00:00:00Z");
});

for (const [total, cap] of [[1001, 200], [400, 200], [201, 37], [200, 37]]) {
  test(`exact count completes ${total} rows under a ${cap}-row cap without skipping short pages`, async () => {
    const h = harness({ cap, probes: Array.from({ length: total }, (_, i) => probe(i, "legacy", { fitness_score: i })) });
    const [run] = await h.api.fetchColonyRuns(owner);
    assert.equal(run.probe_count, total); assert.equal(run.best_fitness, total - 1);
    const pages = h.calls.filter(call => call.table === "vn_probes");
    assert.equal(pages.length, Math.ceil(total / cap));
    assert.deepEqual(pages.map(call => call.range[0]), Array.from({ length: pages.length }, (_, i) => i * cap));
  });
}

for (const count of [null, undefined, -1, 1.5, NaN, Infinity, 50_001, "1"]) {
  test(`invalid or unavailable exact count (${String(count)}) fails before publishing history`, async () => {
    const h = harness({ response: (_call, normal) => ({ ...normal, count }) });
    await rejects(h); assert.equal(h.calls.length, 1);
  });
}

test("count drift, empty gaps, repeated/overlapping pages and reverse order fail rather than truncate or double-count", async () => {
  for (const fault of ["drift", "empty", "overlap", "reverse"]) {
    const h = harness({ probes: [probe(1), probe(2), probe(3)], cap: 1, response: (call, normal) => {
      if (call.table === "vn_probes" && call.range[0] === 1) {
        if (fault === "drift") return { ...normal, count: 4 };
        if (fault === "empty") return { ...normal, data: [] };
        if (fault === "overlap") return { ...normal, data: [probe(1)] };
        return { ...normal, data: [probe(0)] };
      }
      return normal;
    } });
    await rejects(h); assert.equal(h.calls.length, 3);
  }
  await rejects(harness({ probes: [probe(2), probe(1)] }));
  await rejects(harness({ probes: [probe(1), probe(1)] }));
});

test("oversized pages and rows beyond the exact count are rejected", async () => {
  await rejects(harness({ response: (_call, normal) => ({ ...normal, data: Array.from({ length: 201 }, (_, i) => colony(String(i))), count: 201 }) }));
  await rejects(harness({ colonies: [colony("a")], response: (_call, normal) => ({ ...normal, count: 0 }) }));
});

test("a late probe page failure cannot return the already read colonies or partial statistics", async () => {
  const h = harness({ colonies: [colony("saved")], probes: [probe(1), probe(2)], cap: 1, response: (call, normal) =>
    call.table === "vn_probes" && call.range[0] === 1 ? { data: null, count: null, error: { message: "private credential" } } : normal });
  await rejects(h); assert.equal(h.calls.length, 3);
});

test("missing owner, foreign-owner rows and malformed identities cannot produce history", async () => {
  const h = harness();
  for (const input of [undefined, "", " "]) await assert.rejects(h.api.fetchColonyRuns(input), /authenticated owner/);
  assert.equal(h.calls.length, 0);
  for (const rows of [{ colonies: [colony("a", { user_id: "owner-B" })] }, { probes: [probe(1, "legacy", { user_id: "owner-B" })] },
    { colonies: [colony("")] }, { probes: [probe(1, "")] }, { probes: [probe(1, "legacy", { id: null })] }]) await rejects(harness(rows));
});

test("invalid saved timestamps and fitness values fail; null run IDs never become manufactured runs", async () => {
  for (const rows of [{ colonies: [colony("a", { started_at: "bad" })] }, { colonies: [colony("a", { stopped_at: "bad" })] },
    { probes: [probe(1, "legacy", { created_at: "bad" })] }, { probes: [probe(1, "legacy", { fitness_score: NaN })] },
    { probes: [probe(1, "legacy", { fitness_score: null })] }]) await rejects(harness(rows));
  assert.deepEqual(plain(await harness({ probes: [probe(1, null)] }).api.fetchColonyRuns(owner)), []);
});

test("the finite page budget fails a very small cap without returning a partial aggregate", async () => {
  const h = harness({ cap: 1, probes: Array.from({ length: 501 }, (_, i) => probe(i)) });
  await rejects(h); assert.equal(h.calls.filter(call => call.table === "vn_probes").length, 500);
});

test("external abort prevents initial dispatch and cancels a scan before the next page", async () => {
  const abort = new AbortController(); abort.abort();
  const empty = harness(); await rejects(empty, abort.signal); assert.equal(empty.calls.length, 0);
  const during = new AbortController();
  const h = harness({ cap: 1, probes: [probe(1), probe(2)], response: (call, normal) => {
    if (call.table === "vn_probes") during.abort(); return normal;
  } });
  await rejects(h, during.signal); assert.equal(h.calls.length, 2);
  assert.equal(h.calls[1].signal.aborted, true);
});

test("the owned 8-second deadline aborts pending requests and cleans up its timer", async () => {
  let timeout, cleaned = false;
  const h = harness({ globals: { setTimeout(fn, ms) { assert.equal(ms, 8000); timeout = fn; return 7; }, clearTimeout(id) { assert.equal(id, 7); cleaned = true; } },
    response: (_call, normal) => { timeout(); return normal; } });
  await rejects(h); assert.equal(h.calls.length, 1); assert.equal(h.calls[0].signal.aborted, true); assert.equal(cleaned, true);
});

test("the installed Supabase SDK sends exact owner/count/order/range requests and parses capped HTTP counts", async () => {
  const requests = [], probes = [probe(1), probe(2), probe(3)];
  const client = createClient("https://offline.invalid", "fake-test-key", { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }, global: {
    fetch: async (url, options) => {
      const u = new URL(url); requests.push({ u, options });
      assert.equal(u.searchParams.get("user_id"), `eq.${owner}`);
      assert.equal(u.searchParams.get("order"), "id.asc");
      assert.ok(new Headers(options.headers).get("prefer").includes("count=exact"));
      assert.ok(options.signal instanceof AbortSignal);
      const isProbe = u.pathname.endsWith("vn_probes");
      const offset = Number(u.searchParams.get("offset"));
      assert.equal(u.searchParams.get("limit"), "200");
      const data = isProbe ? probes.slice(offset, offset + 1) : [];
      return new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json", "content-range": isProbe ? `${offset}-${offset}/3` : "*/0" } });
    },
  } });
  const [run] = await api(client).fetchColonyRuns(owner);
  assert.equal(run.probe_count, 3); assert.equal(requests.length, 4);
});

test("the actual selector shows a single legacy run, unknown authority and first-record time, with distinct history count", () => {
  const jsx = (type, props) => ({ type, props });
  const stubs = (...names) => Object.fromEntries(names.map(name => [name, name]));
  const modules = {
    react: { useState: () => [false, () => {}] }, "react/jsx-runtime": { jsx, jsxs: jsx },
    "lucide-react": stubs("History", "Clock", "Dna", "Trophy"),
    "@/components/ui/badge": stubs("Badge"), "@/components/ui/button": stubs("Button"),
    "@/components/ui/sheet": stubs("Sheet", "SheetContent", "SheetHeader", "SheetTitle", "SheetTrigger"),
    "@/lib/probes/constants": { STRATEGY_LABELS: {} }, "@/lib/probes/transport": transport,
  };
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(new URL("../src/components/probes/ColonySelector.tsx", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(code, { exports, require: name => modules[name] });
  const run = { run_id: "legacy", history_source: "probe_only", mode: "simulation", started_at: "2026-01-01T00:00:00Z", ended_at: null, probe_count: 1, best_fitness: -1 };
  const readText = node => typeof node === "string" || typeof node === "number" ? String(node)
    : Array.isArray(node) ? node.map(readText).join(" ") : node && typeof node === "object" ? readText(node.props?.children) : "";
  const render = activeColonies => exports.ColonySelector({ runs: [run], activeRunId: "legacy", activeColonies, onSelectRun() {} });
  const output = readText(render([])).replace(/\s+/g, " ");
  assert.match(output, /Legacy probe records\. Colony status, strategy and policies are unknown/);
  assert.match(output, /First probe record:/); assert.ok(!output.includes("Saved status:"));
  assert.match(output, /History \(\s*1\s*\)/);
  const overlap = readText(render([{ colony_id: "legacy", mode: "simulation", strategy: "genetic_algorithm", status: "stopped", live_probes: 0, uptime_secs: 0 }]));
  assert.match(overlap, /History \(\s*1\s*\)/);
});

test("the installed Supabase SDK receives an external abort during a pending HTTP page and dispatches no further pages", async () => {
  let started;
  const dispatched = new Promise(resolve => { started = resolve; });
  const requests = [];
  const abort = new AbortController();
  const client = createClient("https://offline.invalid", "fake-test-key", { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }, global: {
    fetch: async (url, options) => {
      requests.push(new URL(url).pathname);
      if (new URL(url).pathname.endsWith("vn_colonies")) return new Response("[]", { status: 200, headers: { "content-type": "application/json", "content-range": "*/0" } });
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener("abort", () => reject(new DOMException("private abort detail", "AbortError")), { once: true });
        started();
      });
    },
  } });
  const result = api(client).fetchColonyRuns(owner, abort.signal);
  await dispatched; abort.abort();
  await assert.rejects(result, error => error.name === "ProbeDataError" && !error.message.includes("private"));
  assert.equal(requests.length, 2);
});
