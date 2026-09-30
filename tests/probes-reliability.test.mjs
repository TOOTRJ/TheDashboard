import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import * as registry from "../src/lib/probes/gene-registry.ts";
import * as transport from "../src/lib/probes/transport.ts";

function loadModule(path, modules, globals = {}) {
  const exports = {};
  const source = fs.readFileSync(new URL(path, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(compiled, {
    exports, AbortController,
    require(name) { assert.ok(Object.hasOwn(modules, name), `Unexpected import ${name}`); return modules[name]; },
    fetch() { throw new Error("Real network is forbidden in reliability tests"); },
    ...globals,
  });
  return exports;
}
const configs = loadModule("../src/lib/probes/colony-config.ts", { "./gene-registry": registry, "./transport": transport });
const valid = () => configs.buildDefaultStartConfig();
const plain = (value) => JSON.parse(JSON.stringify(value));

function databaseHarness(responses) {
  const calls = [];
  const client = {
    from(table) {
      const call = { table, filters: [] }; calls.push(call);
      const result = responses.shift();
      assert.ok(result, `Missing offline result for ${table}`);
      const query = {
        select() { return this; }, order() { return this; }, limit() { return this; },
        eq(...args) { call.filters.push(args); return this; }, in() { return this; }, not() { return this; },
        maybeSingle() { return this; }, delete() { return this; }, gte() { return this; },
        then(resolve, reject) { return Promise.resolve(result).then(resolve, reject); },
      };
      return query;
    },
  };
  return { calls, api: loadModule("../src/lib/probes/probes-supabase.ts", { "@/lib/supabase/client": { createClient: () => client } }) };
}

test("database errors are never converted to empty probe, generation, trade, or fitness results", async () => {
  for (const method of ["fetchProbes", "fetchGenerationStats", "fetchProbeTrades", "fetchFitnessSnapshots", "fetchLatestRunId", "fetchProbe"]) {
    const { api } = databaseHarness([{ data: null, error: { message: "private-database-token" } }]);
    await assert.rejects(api[method]("colony-A"), (error) => {
      assert.equal(error.name, "ProbeDataError");
      assert.ok(!error.message.includes("private-database-token"));
      return true;
    });
  }
});

test("successful empty data stays distinct from failure, and selected run IDs are mandatory", async () => {
  const { api, calls } = databaseHarness([{ data: [], error: null }, { data: [], error: null }]);
  assert.deepEqual(plain(await api.fetchProbes("A")), []);
  assert.deepEqual(plain(await api.fetchGenerationStats("A")), []);
  assert.deepEqual(calls.map((call) => call.filters), [[["run_id", "A"]], [["run_id", "A"]]]);
  await assert.rejects(api.fetchProbes(undefined), /selected colony/);
  await assert.rejects(api.fetchGenerationStats(""), /selected colony/);
  assert.equal(calls.length, 2);
});

test("colony history does not silently fall back on query failure or fabricate counts after enrichment failure", async () => {
  const failed = databaseHarness([{ data: null, error: { code: "PGRST205" } }]);
  await assert.rejects(failed.api.fetchColonyRuns(), /colony history/);
  assert.equal(failed.calls.length, 1);
  const enrichment = databaseHarness([
    { data: [{ id: "A", mode: "paper", strategy: "genetic_algorithm", started_at: "2026-01-01" }], error: null },
    { data: null, error: { message: "offline" } },
  ]);
  await assert.rejects(enrichment.api.fetchColonyRuns(), /summary statistics/);
  const legacy = databaseHarness([{ data: [], error: null }, { data: [], error: null }]);
  assert.deepEqual(plain(await legacy.api.fetchColonyRuns()), []);
  assert.equal(legacy.calls.length, 2);
});

test("colony history preserves persisted terminal diagnostics without exposing raw messages or configuration", async () => {
  const h = databaseHarness([
    { data: [{ id: "A", mode: "paper", status: "failed", config: { private: "secret", runtime: {
      failure_code: "persistence_failed", failure_message: "private-server-message", state_persisted: true,
      open_positions: 2, requires_reconciliation: true, valuation_available: false,
    } } }], error: null },
    { data: [], error: null },
  ]);
  const [run] = await h.api.fetchColonyRuns();
  assert.equal(run.status, "failed");
  assert.equal(run.runtime.open_positions, 2);
  assert.equal(run.runtime.requires_reconciliation, true);
  assert.equal(run.runtime.valuation_available, false);
  assert.equal(run.runtime.failure_code, "persistence_failed");
  assert.ok(!JSON.stringify(run).includes("private-server-message"));
  assert.ok(!JSON.stringify(run).includes("secret"));
  assert.match(transport.formatColonyFailure(run.runtime.failure_code), /Saving colony state failed/);
  assert.match(transport.formatColonyFailure("feed_unavailable"), /Current market data is unavailable/);
  assert.match(transport.formatColonyFailure("feed_configuration"), /configured HTTPS Solana mainnet RPC/);
  assert.match(transport.formatColonyFailure("feed_stale"), /quote became stale/);
  assert.match(transport.formatColonyFailure("feed_source_invalid"), /source time is missing, invalid/);
  assert.match(transport.formatColonyFailure("invalid_market_value"), /market observation or position value is invalid/);
  assert.match(transport.formatColonyFailure("funding_insufficient"), /cannot fully fund/);
  assert.match(transport.formatColonyFailure("funding_capacity"), /exceeds the configured capacity/);
  assert.match(transport.formatColonyFailure("funding_invalid_plan"), /capital ledger is invalid/);
  assert.match(transport.formatColonyFailure("population_extinct"), /No active candidates remain/);
  assert.ok(!transport.formatColonyFailure("private-server-message").includes("private-server-message"));
});

test("saved valuation availability accepts only explicit booleans", async () => {
  for (const value of [true, false, null, "false", 0]) {
    const h = databaseHarness([
      { data: [{ id: "A", mode: "paper", config: { runtime: { valuation_available: value } } }], error: null },
      { data: [], error: null },
    ]);
    const [run] = await h.api.fetchColonyRuns();
    assert.equal(run.runtime.valuation_available, typeof value === "boolean" ? value : undefined);
  }
});

test("saved history preserves explicit valid market-clock metadata without relabeling legacy simulations", async () => {
  const make = (runtime) => databaseHarness([
    { data: [{ id: "A", mode: "simulation", config: { runtime } }], error: null },
    { data: [], error: null },
  ]);
  const validClock = { clock_basis: "synthetic_market", market_time: "2024-01-01T00:02:00+00:00", market_elapsed_secs: 120 };
  const [run] = await make(validClock).api.fetchColonyRuns();
  for (const [key, value] of Object.entries(validClock)) assert.equal(run.runtime[key], value);
  for (const runtime of [{}, { clock_basis: "simulation", market_time: "invalid-date", market_elapsed_secs: -1 },
    { clock_basis: true, market_time: 123, market_elapsed_secs: Infinity }]) {
    const [bad] = await make(runtime).api.fetchColonyRuns();
    assert.equal(bad.runtime.clock_basis, undefined);
    assert.equal(bad.runtime.market_time, undefined);
    assert.equal(bad.runtime.market_elapsed_secs, undefined);
  }
});

test("overview uses reported marked total, guards nullable metrics, and never replaces unknown valuation with cached probe cash", () => {
  const jsx = (type, props, key) => ({ type, props, key });
  const { ProbesOverview } = loadModule("../src/components/probes/ProbesOverview.tsx", {
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "lucide-react": { Activity: "Activity", Dna: "Dna", DollarSign: "DollarSign", TrendingUp: "TrendingUp", Zap: "Zap" },
    "@/components/ui/card": { Card: "Card", CardContent: "CardContent" },
  });
  const probes = [{ state: "TRADING", current_capital: 999, fitness_score: 1, generation: 0 }];
  const status = { total_capital: 250, reserve_capital: 50, diversity: 0.2, valuation_available: true };
  const render = (systemStatus, valuationAvailable) => JSON.stringify(ProbesOverview({ probes, systemStatus, valuationAvailable }));
  assert.match(render(status), /\$250/);
  assert.match(render(status), /Last reported total/);
  assert.ok(!render(status).includes("$999"));
  assert.match(render({ ...status, total_capital: 0 }), /\$0/);
  for (const systemStatus of [null, { total_capital: null, reserve_capital: null, diversity: null },
    { ...status, total_capital: NaN, diversity: Infinity }, { ...status, valuation_available: false }]) {
    const output = render(systemStatus);
    assert.match(output, /Current market valuation is unavailable/);
    assert.ok(!output.includes("$999"));
    assert.ok(!output.includes("NaN"));
    assert.ok(!output.includes("Infinity"));
  }
  assert.match(render(status, false), /Current market valuation is unavailable/);
  assert.ok(!render(status, false).includes("$250"));
});

test("all built-in presets validate with the same worker limits", () => {
  for (const preset of configs.PRESETS) {
    const config = { ...valid(), ...preset.startOverrides, preset: preset.name, colony_config: preset.config };
    assert.deepEqual(plain(configs.validateStartConfig(config)), [], preset.name);
  }
});

test("numeric input rejects nonfinite, fractional integer, excessive, negative, and underfunded settings", () => {
  for (const patch of [
    { seed_capital: Infinity }, { max_capital: NaN }, { gen0_count: 2.5 }, { gen0_count: 51 },
    { tick_interval_ms: 99 }, { tick_interval_ms: 60_001 }, { mutation_rate: -0.01 }, { mutation_rate: 0.51 },
    { max_probes: 9 }, { max_capital: 999 }, { strategy: "differential_evolution", gen0_count: 3 },
    { gen0_count: "10" }, { max_probes: true }, { mode: "live" }, { strategy: "unknown" }, { user_id: "forged" },
  ]) assert.ok(configs.validateStartConfig({ ...valid(), ...patch }).length > 0, String(Object.keys(patch)));
  assert.deepEqual(plain(configs.validateStartConfig({ ...valid(), mutation_rate: 0, tick_interval_ms: 60_000 })), []);
});

test("gene and asset constraints reject unknown, impossible, duplicate, and unsafe overrides", () => {
  for (const patch of [
    { available_assets: [] }, { available_assets: ["SOL/USDC", "SOL/USDC"] }, { available_assets: ["UNKNOWN"] },
    { enabled_genes: ["made_up_gene"] }, { enabled_genes: ["ema_fast", "ema_fast"] },
    { reproduction_interval: 0 }, { max_lifespan_ticks: -1 },
    { gene_overrides: { made_up_gene: { min: 1 } } },
    { gene_overrides: { ema_fast: { fixed: 3.5 } } },
    { gene_overrides: { stop_loss_pct: { min: 0.05, max: 0.02 } } },
    { gene_overrides: { stop_loss_pct: { min: 0.04, fixed: 0.03 } } },
    { gene_overrides: { ema_fast: { fixed: 15 }, ema_slow: { fixed: 10 } } },
    { gene_overrides: { stop_loss_pct: { fixed: 0.05 }, take_profit_pct: { min: 0.03, max: 0.06 } } },
    { available_assets: ["SOL/USDC"], gene_overrides: { num_assets: { min: 2 } } },
  ]) assert.ok(configs.validateStartConfig({ ...valid(), colony_config: { ...valid().colony_config, ...patch } }).length > 0);
  const unlocked = { ...valid(), preset: "rsi_focus", colony_config: {
    ...valid().colony_config, enabled_genes: [], available_assets: ["SOL/USDC"],
    gene_overrides: Object.fromEntries(registry.GENE_DEFINITIONS.map((gene) => [gene.name, {}])),
  } };
  assert.deepEqual(plain(configs.validateStartConfig(unlocked)), []);
});

test("structured 422 errors identify known fields without reflecting server text, inputs, or unrecognized field names", async () => {
  const body = { detail: [
    { loc: ["body", "gen0_count"], msg: "private-token", input: "secret", type: "less_than_equal" },
    { loc: ["body", "colony_config", "gene_overrides", "ema_fast", "fixed"], msg: "private-token" },
    { loc: ["body", "private-token"], msg: "private-token" },
  ] };
  const message = transport.formatWorkerValidation(body);
  assert.match(message, /Initial probes.*2 to 50/);
  assert.match(message, /EMA fast.*fixed value/);
  assert.ok(!message.includes("private-token"));
  assert.ok(!message.includes("secret"));
  const endpoints = transport.resolveWorkerEndpoints({ environment: "production", apiUrl: "https://worker.example", wsUrl: "wss://worker.example/ws" });
  await assert.rejects(transport.requestWorker(endpoints, "test", "/api/v1/colonies/", {}, async () => Response.json(body, { status: 422 })), (error) => error.status === 422 && error.message === message);
});

function pageHarness(initial = {}) {
  let hookIndex = 0, dirty = false, output, websocketMessage, now = 0;
  const hooks = [], pendingEffects = [], intervals = new Map(), requests = [];
  const control = { databaseFails: false, workerFails: false, launchFails: false, revision: 1, ...initial };
  const sameDeps = (a, b) => a && b && a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
  function memo(factory, deps) {
    const i = hookIndex++;
    if (!hooks[i] || !sameDeps(hooks[i].deps, deps)) hooks[i] = { deps, value: factory() };
    return hooks[i].value;
  }
  function effect(fn, deps) {
    const i = hookIndex++;
    if (!hooks[i] || !sameDeps(hooks[i].deps, deps)) {
      const previous = hooks[i]; hooks[i] = { deps, cleanup: previous?.cleanup };
      pendingEffects.push(() => { hooks[i].cleanup?.(); hooks[i].cleanup = fn(); });
    }
  }
  const react = {
    useState(initial) {
      const i = hookIndex++;
      if (!hooks[i]) hooks[i] = { value: typeof initial === "function" ? initial() : initial };
      return [hooks[i].value, (next) => {
        const value = typeof next === "function" ? next(hooks[i].value) : next;
        if (!Object.is(value, hooks[i].value)) { hooks[i].value = value; dirty = true; }
      }];
    },
    useRef: (initial) => memo(() => ({ current: initial }), []),
    useCallback: (callback, deps) => memo(() => callback, deps),
    useEffect: effect, useLayoutEffect: effect,
  };
  const history = () => [{ run_id: "A", mode: control.savedMode ?? "paper", started_at: "2026-01-01", probe_count: control.revision, best_fitness: 1,
    status: control.savedStatus, runtime: control.savedRuntime }];
  const live = () => [{ colony_id: "A", mode: "paper", status: "running", live_probes: control.revision }];
  const dbRead = async (value) => { if (control.databaseFails) throw new Error("private-database-error"); return value; };
  const worker = async (_endpoints, token, path, options = {}) => {
    requests.push({ token, path, options });
    if (control.workerFails || (options.method === "POST" && control.launchFails)) throw new transport.WorkerRequestError(503, "Worker unavailable; check status before retrying.");
    if (options.method === "POST") return { colony_id: "NEW" };
    if (path === "/api/v1/colonies/") return live();
    return { status: "running", mode: "paper", started_at: "2026-01-01", state_persisted: true };
  };
  const modules = {
    react, "react/jsx-runtime": { jsx: (type, props, key) => ({ type, props, key }), jsxs: (type, props, key) => ({ type, props, key }) },
    "next/link": { default: "link" }, sonner: { toast: { success() { control.successes = (control.successes ?? 0) + 1; } } },
    "lucide-react": { BookOpen: "BookOpen", Dna: "Dna" },
    "@/components/auth/AuthProvider": { useAuth: () => ({ user: { id: "user-A" }, session: { access_token: "token-A" }, loading: false }) },
    "@/components/probes/ProbesDashboard": { ProbesDashboard: "Dashboard" },
    "@/components/ui/skeleton": { Skeleton: "Skeleton" },
    "@/lib/probes/probes-supabase": {
      fetchColonyRuns: () => dbRead(history()), fetchProbes: (id) => { assert.equal(id, "A"); return dbRead([{ id: "probe", current_capital: control.revision }]); },
      fetchGenerationStats: (id) => { assert.equal(id, "A"); return dbRead([{ generation: control.revision }]); },
    },
    "@/lib/probes/websocket": { useProbesWebSocket: (_token, _user, callback) => { websocketMessage = callback; return { connected: true, error: null }; } },
    "@/lib/probes/constants": { VN_ENDPOINTS: { apiUrl: "https://offline.invalid", wsUrl: "wss://offline.invalid", error: null } },
    "@/lib/probes/transport": { ...transport, requestWorker: worker },
    "@/lib/probes/colony-config": configs,
  };
  const page = loadModule("../src/app/(dashboard)/probes/page.tsx", modules, {
    setInterval: (callback, delay) => { intervals.set(++now, { callback, delay }); return now; },
    clearInterval: (id) => intervals.delete(id),
  });
  const child = page.default();
  function render() {
    hookIndex = 0; dirty = false;
    output = child.type(child.props);
    while (pendingEffects.length) pendingEffects.shift()();
  }
  render();
  function find(node, type) {
    if (!node || typeof node !== "object") return undefined;
    if (node.type === type) return node;
    const children = node.props?.children;
    for (const item of Array.isArray(children) ? children.flat(Infinity) : [children]) {
      const result = find(item, type); if (result) return result;
    }
  }
  return { control, requests,
    dashboard: () => find(output, "Dashboard").props,
    alerts: () => JSON.stringify(output).match(/unavailable|retained|failed/g) ?? [],
    text: () => JSON.stringify(output),
    async pump() { for (let i = 0; i < 8; i++) { await new Promise((resolve) => setImmediate(resolve)); if (dirty) render(); } },
    tick() { for (const timer of [...intervals.values()]) timer.callback(); },
    event: (message) => websocketMessage(message),
    cleanup() { for (const hook of hooks) hook?.cleanup?.(); },
  };
}

test("actual page explains the saved synthetic clock when the worker is unavailable and leaves legacy dates unclassified", async () => {
  for (const savedRuntime of [undefined,
    { clock_basis: "synthetic_market", market_time: "invalid-date" },
    { clock_basis: "synthetic_market", market_time: "2024-01-01T00:02:00+00:00" }]) {
    const h = pageHarness({ workerFails: true, savedStatus: "stopped", savedMode: "simulation", savedRuntime });
    try {
      await h.pump();
      if (savedRuntime?.market_time === "2024-01-01T00:02:00+00:00") {
        assert.match(h.text(), /Last reported synthetic market time/);
        assert.match(h.text(), /2024-01-01 00:02:00 UTC/);
        assert.match(h.text(), /Prices are generated/);
      } else {
        assert.ok(!h.text().includes("Last reported synthetic market time"));
      }
    } finally { h.cleanup(); }
  }
});

test("actual page retains last successful DB data, history, live list and status during outage, then recovers on retry", async () => {
  const h = pageHarness(); await h.pump();
  assert.equal(h.dashboard().probes[0].current_capital, 1);
  assert.equal(h.dashboard().simStatus, "running");
  h.control.databaseFails = true; h.control.workerFails = true;
  h.tick(); await h.pump();
  assert.equal(h.dashboard().probes[0].current_capital, 1);
  assert.equal(h.dashboard().generationStats[0].generation, 1);
  assert.equal(h.dashboard().colonyRuns[0].probe_count, 1);
  assert.equal(h.dashboard().activeColonies[0].live_probes, 1);
  assert.equal(h.dashboard().simStatus, "running");
  assert.ok(h.alerts().length > 0);
  h.control.databaseFails = false; h.control.workerFails = false; h.control.revision = 2;
  h.tick(); await h.pump();
  assert.equal(h.dashboard().probes[0].current_capital, 2);
  assert.equal(h.dashboard().generationStats[0].generation, 2);
  assert.equal(h.dashboard().activeColonies[0].live_probes, 2);
  assert.equal(h.dashboard().colonyRuns[0].probe_count, 2);
  assert.equal(h.alerts().length, 0);
  h.cleanup();
});

test("actual page rejects unsafe launch before request and preserves selected colony on startup failure", async () => {
  const h = pageHarness(); await h.pump();
  let posts = () => h.requests.filter((request) => request.options.method === "POST").length;
  assert.equal(await h.dashboard().onStart({ ...valid(), seed_capital: Infinity }), false);
  await h.pump();
  assert.equal(posts(), 0);
  h.control.launchFails = true;
  assert.equal(await h.dashboard().onStart(valid()), false);
  await h.pump();
  assert.equal(posts(), 1);
  assert.equal(h.dashboard().activeRunId, "A");
  assert.equal(h.dashboard().probes[0].current_capital, 1);
  assert.equal(h.control.successes ?? 0, 0);
  assert.match(h.dashboard().startError, /unavailable/);
  assert.equal(h.dashboard().starting, false);
  h.cleanup();
});

test("worker failure events remain explicit and terminal rather than masquerading as paused/running", async () => {
  const h = pageHarness(); await h.pump();
  h.event({ type: "simulation_status", colony_id: "A", data: { status: "failed", mode: "paper", state_persisted: false, open_positions: 2, requires_reconciliation: true } });
  await h.pump();
  assert.equal(h.dashboard().simStatus, "failed");
  assert.equal(h.dashboard().systemStatus.state_persisted, false);
  assert.equal(h.dashboard().systemStatus.requires_reconciliation, true);
  h.cleanup();
});

test("persisted failed status and reconciliation survive worker unavailability, but stored running is not live authority", async () => {
  const failed = pageHarness({ workerFails: true, savedStatus: "failed", savedRuntime: {
    failure_code: "persistence_failed", state_persisted: true, requires_reconciliation: true, open_positions: 2, valuation_available: false,
  } });
  await failed.pump();
  assert.equal(failed.dashboard().simStatus, "failed");
  assert.match(failed.text(), /saved terminal status/);
  assert.match(failed.text(), /Saving colony state failed/);
  assert.match(failed.text(), /Paper positions or saved trade records require reconciliation/);
  assert.match(failed.text(), /Current colony valuation is unavailable/);
  assert.equal(failed.dashboard().valuationAvailable, false);
  failed.cleanup();
  const running = pageHarness({ workerFails: true, savedStatus: "running" });
  await running.pump();
  assert.equal(running.dashboard().simStatus, "unknown");
  running.cleanup();
});
