import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import * as registry from "../src/lib/probes/gene-registry.ts";
import * as transport from "../src/lib/probes/transport.ts";
import * as execution from "../src/lib/probes/execution.ts";

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
const lifecycle = loadModule("../src/lib/probes/lifecycle.ts", {});
const configs = loadModule("../src/lib/probes/colony-config.ts", { "./gene-registry": registry, "./execution": execution, "./transport": transport });
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
  return { calls, api: loadModule("../src/lib/probes/probes-supabase.ts", {
    "@/lib/supabase/client": { createClient: () => client }, "./execution": execution, "./transport": transport,
  }) };
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
  assert.match(transport.formatColonyFailure("candle_configuration"), /private Birdeye key/);
  assert.match(transport.formatColonyFailure("candle_history_invalid"), /history is missing, incomplete, revised/);
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
    "@/lib/probes/transport": transport, "@/lib/probes/execution": execution,
    "@/components/ui/card": { Card: "Card", CardContent: "CardContent" },
  });
  const probes = [{ state: "TRADING", current_capital: 999, fitness_score: 1, generation: 0 }];
  const status = { execution_policy: { version: "usd-reference-percentage-cost-v1", account_currency: "USD", valuation: "reference_mark", cost_assumptions: "uncalibrated_scenario", config: execution.defaultExecutionConfig() }, total_capital: 250, reserve_capital: 50, diversity: 0.2, valuation_available: true };
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
    { gene_overrides: { stop_loss_pct: { fixed: 0.05 }, take_profit_pct: { min: 0.03, max: 0.05 } } },
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
    if (options.method === "POST") {
      if (control.postGate) await control.postGate;
      return { colony_id: "NEW" };
    }
    if (path === "/api/v1/colonies/") return live();
    return { status: control.workerStatus ?? "running", mode: "paper", started_at: "2026-01-01", state_persisted: true,
      ...(control.workerRuntime ?? {}) };
  };
  const modules = {
    react, "react/jsx-runtime": { jsx: (type, props, key) => ({ type, props, key }), jsxs: (type, props, key) => ({ type, props, key }) },
    "next/link": { default: "link" }, sonner: { toast: { success() { control.successes = (control.successes ?? 0) + 1; } } },
    "lucide-react": { BookOpen: "BookOpen", Dna: "Dna" },
    "@/components/auth/AuthProvider": { useAuth: () => ({ user: { id: "user-A" }, session: { access_token: "token-A" }, loading: false }) },
    "@/components/probes/ProbesDashboard": { ProbesDashboard: "Dashboard" },
    "@/components/probes/ExecutionPolicyNotice": { ExecutionPolicyNotice: "ExecutionPolicyNotice" },
    "@/components/ui/skeleton": { Skeleton: "Skeleton" },
    "@/lib/probes/probes-supabase": {
      fetchColonyRuns: () => dbRead(history()), fetchProbes: (id) => { assert.equal(id, "A"); return dbRead([{ id: "probe", current_capital: control.revision }]); },
      fetchGenerationStats: (id) => { assert.equal(id, "A"); return dbRead([{ generation: control.revision }]); },
    },
    "@/lib/probes/websocket": { useProbesWebSocket: (_token, _user, callback) => { websocketMessage = callback; return { connected: true, error: null }; } },
    "@/lib/probes/constants": { VN_ENDPOINTS: { apiUrl: "https://offline.invalid", wsUrl: "wss://offline.invalid", error: null } },
    "@/lib/probes/lifecycle": lifecycle, "@/lib/probes/execution": execution,
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
    visibleText: () => {
      const read = (node) => {
        if (typeof node === "string" || typeof node === "number") return String(node);
        if (Array.isArray(node)) return node.map(read).join(" ");
        return node && typeof node === "object" ? read(node.props?.children) : "";
      };
      return read(output).replace(/\s+/g, " ").trim();
    },
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

test("probe details distinguish unavailable equity diagnostics from zero and legacy definitions", () => {
  const jsx = (type, props, key) => ({ type, props, key });
  const { ProbeDetail } = loadModule("../src/components/probes/ProbeDetail.tsx", {
    "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "Fragment" },
    "lucide-react": { Clock: "Clock", Skull: "Skull", Sparkles: "Sparkles" },
    "@/components/ui/badge": { Badge: "Badge" },
    "@/components/ui/button": { Button: "Button" },
    "@/components/ui/card": { Card: "Card", CardContent: "CardContent", CardHeader: "CardHeader" },
    "@/components/ui/dialog": { Dialog: "Dialog", DialogContent: "DialogContent", DialogHeader: "DialogHeader", DialogTitle: "DialogTitle" },
    "@/lib/probes/constants": { STATE_COLORS: { TRADING: "#fff" }, STATE_LABELS: { TRADING: "Trading" } },
    "@/lib/probes/lifecycle": lifecycle, "@/lib/probes/execution": execution,
    "@/lib/probes/gene-registry": { GENE_DEFINITIONS: [] },
    "./GenomeRadar": { GenomeRadar: "GenomeRadar" }, "./TradeLog": { TradeLog: "TradeLog" },
  });
  const probe = { id: "probe", state: "TRADING", born_at: "2024-01-01", total_trades: 0,
    fitness_score: -.2, current_capital: 100, total_pnl: 0, max_drawdown: .2, genome: {}, sharpe_ratio: null };
  const render = (changes) => JSON.stringify(ProbeDetail({ probe: { ...probe, ...changes }, open: true, onClose() {} }));
  const legacy = render({ sharpe_ratio: 1.25 });
  assert.match(legacy, /Sharpe \(run policy\)/);
  assert.match(legacy, /legacy definitions/);
  assert.ok(!legacy.includes("Historical max drawdown"));
  assert.ok(!legacy.includes("Equity Sharpe (diagnostic)"));
  const metrics = { fitness_version: "equity-roi-historical-dd-v1", current_drawdown: 0, accounting: { execution_policy: { version: "usd-reference-percentage-cost-v1", account_currency: "USD", valuation: "reference_mark", cost_assumptions: "uncalibrated_scenario", config: execution.defaultExecutionConfig() }, cash: 100, position_value: 0, equity: 100, roi: 0, valuation_available: true } };
  const missing = render({ metrics });
  assert.match(missing, /Unavailable/);
  assert.match(missing, /Historical max drawdown/);
  assert.match(missing, /Current drawdown: 0.0%/);
  assert.match(missing, /minute equity returns without annualization; it does not affect the score/);
  for (const sharpe_ratio of [null, undefined, Infinity, NaN]) assert.match(render({ metrics, sharpe_ratio }), /Unavailable/);
  assert.ok(!render({ metrics, sharpe_ratio: 0 }).includes("Unavailable"));
  assert.ok(!render({ metrics: { fitness_version: "unrecognized-policy" }, sharpe_ratio: 0 }).includes("Historical max drawdown"));
});

test("actual page preserves nullable Sharpe and policy metadata from probe events", async () => {
  const h = pageHarness(); await h.pump();
  for (const sharpe_ratio of [null, undefined, NaN, Infinity, 0, 1.23456789123, NaN]) {
    const metrics = { fitness_version: "equity-roi-historical-dd-v1", status: "insufficient_samples", sharpe_ratio };
    h.event({ type: "probe_update", colony_id: "A", data: { probe_id: "probe", sharpe_ratio, metrics } });
    await h.pump();
    const saved = h.dashboard().probes.find((probe) => probe.id === "probe");
    assert.equal(saved.sharpe_ratio, typeof sharpe_ratio === "number" && Number.isFinite(sharpe_ratio) ? sharpe_ratio : null);
    assert.equal(saved.metrics.fitness_version, metrics.fitness_version);
  }
  h.event({ type: "probe_update", colony_id: "A", data: { probe_id: "probe", metrics: [] } });
  await h.pump();
  assert.equal(h.dashboard().probes.find((probe) => probe.id === "probe").metrics, null);
  h.cleanup();
});

const riskTrip = "11111111-1111-4111-8111-111111111111";
const riskDetails = () => ({
  policy: "initial-account-loss-v1", threshold_fraction: 0.3, baseline_equity: 100,
  observed_equity: 70, observed_loss_fraction: 0.3, observed_at: "2026-09-30T10:00:00+00:00",
  trip_id: riskTrip, tripped_at: "2026-09-30T10:00:00+00:00", trip_equity: 70,
  trip_loss_fraction: 0.3, last_recovered_at: null, recovery_count: 0,
});

test("saved risk halts preserve only validated public diagnostics", async () => {
  const h = databaseHarness([
    { data: [{ id: "A", mode: "paper", status: "risk_halted", config: { private: "secret", runtime: {
      circuit_breaker: true, risk_control: { ...riskDetails(), private: "secret" },
    } } }], error: null },
    { data: [], error: null },
  ]);
  const [run] = await h.api.fetchColonyRuns();
  assert.equal(run.status, "risk_halted");
  assert.equal(run.runtime.circuit_breaker, true);
  assert.deepEqual(plain(run.runtime.risk_control), riskDetails());
  assert.ok(!JSON.stringify(run).includes("secret"));
  const bad = databaseHarness([
    { data: [{ id: "A", mode: "paper", config: { runtime: {
      circuit_breaker: "true", risk_control: { ...riskDetails(), policy: "private-policy" },
    } } }], error: null }, { data: [], error: null },
  ]);
  const [invalid] = await bad.api.fetchColonyRuns();
  assert.equal(invalid.runtime.circuit_breaker, undefined);
  assert.equal(invalid.runtime.risk_control, undefined);
});

test("risk diagnostics reject invalid policies, counters, fractions, timestamps and trip identifiers", () => {
  for (const patch of [
    { policy: "unknown" }, { threshold_fraction: 0 }, { threshold_fraction: 1.01 },
    { threshold_fraction: NaN }, { threshold_fraction: "0.3" }, { threshold_fraction: Infinity },
    { recovery_count: -1 }, { recovery_count: 0.5 }, { recovery_count: "0" },
  ]) assert.equal(transport.parseRiskControl({ ...riskDetails(), ...patch }), undefined);
  for (const input of [null, undefined, [], true, "private-token"]) assert.equal(transport.parseRiskControl(input), undefined);
  const invalid = transport.parseRiskControl({ ...riskDetails(),
    baseline_equity: Infinity, observed_equity: "100", observed_loss_fraction: -0.1,
    observed_at: "2026-09-30", trip_id: "private-token", tripped_at: "2026-99-99T10:00:00Z",
    trip_equity: NaN, trip_loss_fraction: "0.3", last_recovered_at: true,
  });
  for (const key of ["baseline_equity", "observed_equity", "observed_loss_fraction", "observed_at", "trip_id",
    "tripped_at", "trip_equity", "trip_loss_fraction", "last_recovered_at"]) assert.equal(invalid[key], null, key);
  assert.equal(transport.parseRiskControl({ ...riskDetails(), threshold_fraction: 1 }).threshold_fraction, 1);
  assert.equal(transport.parseRiskControl({ ...riskDetails(), observed_loss_fraction: 0 }).observed_loss_fraction, 0);
});

test("risk recovery uses selected colony, current bearer and JSON trip identity", async () => {
  const endpoints = transport.resolveWorkerEndpoints({ environment: "production", apiUrl: "https://worker.example", wsUrl: "wss://worker.example/ws" });
  await transport.requestWorker(endpoints, "current-session", transport.colonyPath("colony/A", "recover"), {
    method: "POST", body: { trip_id: riskTrip },
  }, async (url, options) => {
    assert.equal(url, "https://worker.example/api/v1/colonies/colony%2FA/recover");
    assert.equal(options.headers.Authorization, "Bearer current-session");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), { trip_id: riskTrip });
    assert.equal(options.redirect, "error");
    return Response.json({ status: "running" });
  });
});

test("recovery conflicts expose known local explanations without raw error data", async () => {
  const endpoints = transport.resolveWorkerEndpoints({ environment: "production", apiUrl: "https://worker.example", wsUrl: "wss://worker.example/ws" });
  const cases = {
    risk_not_halted: /no longer risk halted/, risk_trip_changed: /tripped again/,
    risk_loss_unrecovered: /original limit/, risk_quotes_unavailable: /fresh quotes/,
    risk_history_unavailable: /valid candle history/, risk_no_candidates: /No eligible candidates/,
    "private-token": /cannot perform this action/,
  };
  for (const [code, expected] of Object.entries(cases)) {
    await assert.rejects(transport.requestWorker(endpoints, "session", transport.colonyPath("A", "recover"), {},
      async () => Response.json({ detail: { code, message: "private-token", arbitrary: "secret" } }, { status: 409 })),
    (error) => {
      assert.equal(error.status, 409);
      assert.match(error.message, expected);
      assert.ok(!error.message.includes("private-token"));
      assert.ok(!error.message.includes("secret"));
      return true;
    });
  }
  await assert.rejects(transport.requestWorker(endpoints, "session", transport.colonyPath("A", "recover"), {},
    async () => new Response("private-token", { status: 409 })), /cannot perform this action/);
});

test("actual page displays confirmed risk monitoring and binds recovery to the latest halt", async () => {
  const h = pageHarness();
  try {
    await h.pump();
    h.event({ type: "simulation_status", colony_id: "A", data: {
      status: "risk_halted", circuit_breaker: true, mode: "paper", risk_control: riskDetails(),
    } });
    await h.pump();
    assert.equal(h.dashboard().simStatus, "risk_halted");
    assert.equal(h.dashboard().recoveryAvailable, true);
    assert.match(h.text(), /New entries and evolution are blocked/);
    assert.match(h.text(), /continues checking fresh quotes/);
    assert.match(h.text(), /including reserve/);
    assert.match(h.text(), /does not reset the starting balance/);
    h.control.workerStatus = "risk_halted";
    h.control.workerRuntime = { circuit_breaker: true, risk_control: riskDetails() };
    await h.dashboard().onRecover();
    await h.pump();
    const posts = h.requests.filter((request) => request.options.method === "POST");
    assert.equal(posts.length, 1);
    assert.equal(posts[0].path, "/api/v1/colonies/A/recover");
    assert.deepEqual(plain(posts[0].options.body), { trip_id: riskTrip });
    assert.equal(h.dashboard().simStatus, "risk_halted", "successful control alone must not fabricate running");
    h.event({ type: "simulation_status", colony_id: "A", data: {
      status: "running", circuit_breaker: false, mode: "paper",
      risk_control: { ...riskDetails(), recovery_count: 1 },
    } });
    await h.pump();
    assert.equal(h.dashboard().simStatus, "running");
    assert.equal(h.dashboard().recoveryAvailable, false);
    assert.ok(!h.text().includes("continues checking fresh quotes"));
  } finally { h.cleanup(); }
});

test("saved risk halt and outage retain history without claiming active monitoring or enabling recovery", async () => {
  const h = pageHarness({ workerFails: true, savedStatus: "risk_halted", savedRuntime: {
    circuit_breaker: true, risk_control: riskDetails(),
  } });
  try {
    await h.pump();
    assert.equal(h.dashboard().simStatus, "risk_halted");
    assert.equal(h.dashboard().recoveryAvailable, false);
    assert.match(h.text(), /saved risk-halted status/);
    assert.match(h.text(), /ongoing position monitoring cannot be confirmed/);
    assert.ok(!h.text().includes("continues checking fresh quotes"));
    await h.dashboard().onRecover();
    assert.equal(h.requests.filter((request) => request.options.method === "POST").length, 0);
  } finally { h.cleanup(); }
});

test("last confirmed risk halt stops claiming monitoring after worker status fails", async () => {
  const h = pageHarness({ workerStatus: "risk_halted", workerRuntime: {
    circuit_breaker: true, risk_control: riskDetails(),
  } });
  try {
    await h.pump();
    assert.equal(h.dashboard().recoveryAvailable, true);
    h.control.workerFails = true;
    h.tick(); await h.pump();
    assert.equal(h.dashboard().simStatus, "risk_halted");
    assert.equal(h.dashboard().recoveryAvailable, false);
    assert.match(h.text(), /ongoing position monitoring cannot be confirmed/);
    assert.ok(!h.text().includes("continues checking fresh quotes"));
  } finally { h.cleanup(); }
});

test("recovery without a valid current trip never sends a request", async () => {
  for (const risk_control of [undefined, { ...riskDetails(), trip_id: null }, { ...riskDetails(), trip_id: "stale-secret" }]) {
    const h = pageHarness({ workerStatus: "risk_halted", workerRuntime: { circuit_breaker: true, risk_control } });
    try {
      await h.pump();
      assert.equal(h.dashboard().recoveryAvailable, false);
      await h.dashboard().onRecover();
      assert.equal(h.requests.filter((request) => request.options.method === "POST").length, 0);
    } finally { h.cleanup(); }
  }
});

test("repeated recovery clicks issue one control and keep the halt while confirmation is pending", async () => {
  let release;
  const postGate = new Promise((resolve) => { release = resolve; });
  const h = pageHarness({ workerStatus: "risk_halted", workerRuntime: {
    circuit_breaker: true, risk_control: riskDetails(),
  }, postGate });
  try {
    await h.pump();
    const first = h.dashboard().onRecover();
    const second = h.dashboard().onRecover();
    await h.pump();
    assert.equal(h.requests.filter((request) => request.options.method === "POST").length, 1);
    assert.equal(h.dashboard().controlPending, true);
    assert.equal(h.dashboard().simStatus, "risk_halted");
    release();
    await Promise.all([first, second]);
    await h.pump();
    assert.equal(h.dashboard().controlPending, false);
    assert.equal(h.dashboard().simStatus, "risk_halted");
  } finally { release(); h.cleanup(); }
});

test("risk-halted controls remain stoppable and offer explicit recovery instead of normal resume or launch", () => {
  const jsx = (type, props, key) => ({ type, props, key });
  const { SimulationControls } = loadModule("../src/components/probes/SimulationControls.tsx", {
    react: { useState: () => [false, () => {}] }, "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "Fragment" },
    "lucide-react": { Loader2: "Loader2", Pause: "Pause", Play: "Play", Square: "Square", Settings2: "Settings2" },
    "@/components/ui/button": { Button: "Button" }, "@/components/ui/badge": { Badge: "Badge" },
    "./ConnectionStatus": { ConnectionStatus: "ConnectionStatus" }, "./ColonyConfigDialog": { ColonyConfigDialog: "ColonyConfigDialog" },
    "@/lib/probes/constants": { STRATEGY_LABELS: {} },
  });
  function findButtons(node, found = []) {
    if (!node || typeof node !== "object") return found;
    if (node.type === "Button") found.push(node);
    for (const child of [node.props?.children].flat(Infinity)) findButtons(child, found);
    return found;
  }
  const onRecover = () => {}, onStop = () => {};
  const props = { status: "risk_halted", connected: true, generation: 1, tick: 5, liveProbes: 2,
    mode: "paper", starting: false, recoveryAvailable: true, controlPending: false,
    onStart() {}, onStop, onPause() {}, onResume() {}, onRecover };
  const controls = SimulationControls(props);
  const buttons = findButtons(controls);
  assert.equal(buttons.length, 2);
  assert.equal(buttons[0].props.onClick, onRecover);
  assert.equal(buttons[0].props.disabled, false);
  assert.equal(buttons[1].props.onClick, onStop);
  assert.equal(buttons[1].props.disabled, false);
  const text = JSON.stringify(controls);
  assert.match(text, /Risk halted/);
  assert.ok(!text.includes("New Colony"));
  assert.ok(!text.includes('"Resume"'));
  assert.ok(!text.includes('"Pause"'));
  assert.equal(findButtons(SimulationControls({ ...props, recoveryAvailable: false }))[0].props.disabled, true);
  assert.ok(findButtons(SimulationControls({ ...props, controlPending: true })).every((button) => button.props.disabled));
});

const evaluationPolicy = () => ({ version: "common-market-window-v1", horizon_unit: "market_minutes",
  warmup: "all_candidates_ready", interruptions: "abort_without_tell" });
const evaluationCohort = (phase = "warming") => ({
  phase, iteration_id: "colony-A:iteration-1", member_count: 3, completed_count: phase === "completed" ? 3 : 0,
  started_at: phase === "warming" ? null : 1_704_067_200,
  ends_at: phase === "warming" ? null : 1_704_073_200, abort_reason: null,
});

test("saved evaluation metadata recognizes only the common-window policy and strips private ledger contents", async () => {
  for (const policy of [evaluationPolicy(), undefined, { ...evaluationPolicy(), version: "old-policy" }]) {
    const h = databaseHarness([
      { data: [{ id: "A", mode: "simulation", config: { private: "secret", runtime: {
        evaluation_policy: policy && { ...policy, private: "secret" }, cohort: { ...evaluationCohort(),
          member_ids: ["private-members"], evaluations: [{ private: "secret" }], private: "secret" },
      } } }], error: null }, { data: [], error: null },
    ]);
    const [run] = await h.api.fetchColonyRuns();
    if (policy?.version === "common-market-window-v1") {
      assert.deepEqual(plain(run.runtime.evaluation_policy), evaluationPolicy());
      assert.deepEqual(plain(run.runtime.cohort), evaluationCohort());
    } else {
      assert.equal(run.runtime.evaluation_policy, undefined);
      assert.equal(run.runtime.cohort, undefined);
    }
    assert.ok(!JSON.stringify(run).includes("secret"));
    assert.ok(!JSON.stringify(run).includes("private-members"));
  }
});

test("cohort parsing rejects invalid counts, times, phases and policy semantics", () => {
  for (const patch of [{ phase: "running" }, { iteration_id: "" }, { iteration_id: "x".repeat(129) },
    { member_count: 0 }, { member_count: 1.5 }, { completed_count: -1 }, { completed_count: 4 },
    { completed_count: "0" }, { started_at: NaN }, { ends_at: Infinity }, { started_at: -1 },
    { started_at: 1_704_073_200 }, { ends_at: 1_704_067_200 }, { ends_at: 8_640_000_000_001 }]) {
    assert.equal(transport.parseEvaluationCohort({ ...evaluationCohort("evaluating"), ...patch }), undefined);
  }
  assert.equal(transport.parseEvaluationCohort({ ...evaluationCohort(), completed_count: 1 }), undefined);
  assert.equal(transport.parseEvaluationCohort({ ...evaluationCohort("completed"), completed_count: 2 }), undefined);
  assert.equal(transport.parseEvaluationCohort({ ...evaluationCohort("evaluating"), started_at: null, ends_at: null }), undefined);
  assert.equal(transport.parseEvaluationCohort({ ...evaluationCohort("aborted"), abort_reason: "private-stacktrace" }).abort_reason, "unknown");
  assert.equal(transport.parseEvaluationCohort({ ...evaluationCohort(), phase: "aborted", abort_reason: "paused" }).abort_reason, "paused");
  for (const patch of [{ version: "unknown" }, { horizon_unit: "ticks" }, { warmup: "none" }, { interruptions: "score_partial" }]) {
    assert.equal(transport.parseEvaluationPolicy({ ...evaluationPolicy(), ...patch }), undefined);
  }
  for (const value of [null, undefined, [], "private"]) {
    assert.equal(transport.parseEvaluationCohort(value), undefined);
    assert.equal(transport.parseEvaluationPolicy(value), undefined);
  }
});

test("actual page explains warmup, shared windows, completed cohorts and aborted optimizer updates", async () => {
  const h = pageHarness();
  try {
    await h.pump();
    for (const [phase, expected] of [["warming", /Candidates are not ranked during warmup/],
      ["evaluating", /All candidates share the same market-time evaluation window/],
      ["completed", /every candidate has a terminal result/], ["aborted", /excluded from optimizer updates/]]) {
      h.event({ type: "simulation_status", colony_id: "A", data: {
        status: "running", mode: "simulation", evaluation_policy: evaluationPolicy(),
        cohort: { ...evaluationCohort(phase), abort_reason: phase === "aborted" ? "private-stacktrace" : null },
      } });
      await h.pump();
      assert.match(h.visibleText(), expected);
      assert.match(h.visibleText(), /Self-reproduction and diversity injection wait for cohort boundaries/);
      assert.match(h.visibleText(), /does not establish strategy quality/);
      assert.ok(!h.visibleText().includes("private-stacktrace"));
      if (phase !== "warming") assert.match(h.visibleText(), /2024-01-01T00:00:00.000Z/);
    }
  } finally { h.cleanup(); }
});

test("saved and retained evaluation progress is clearly historical during worker outage", async () => {
  for (const source of ["saved", "retained"]) {
    const runtime = { evaluation_policy: evaluationPolicy(), cohort: evaluationCohort("evaluating") };
    const h = pageHarness(source === "saved"
      ? { workerFails: true, savedStatus: "running", savedRuntime: runtime }
      : { workerRuntime: runtime });
    try {
      await h.pump();
      if (source === "retained") {
        h.control.workerFails = true; h.tick(); await h.pump();
      }
      assert.match(h.visibleText(), /Recorded evaluation phase/);
      assert.match(h.visibleText(), /historical evaluation details/);
      assert.ok(!h.visibleText().includes("Last reported evaluation phase"));
      if (source === "saved") assert.equal(h.dashboard().simStatus, "unknown", "saved running is not live authority");
    } finally { h.cleanup(); }
  }
});

test("unknown evaluation policies and malformed cohorts are not presented as valid experiments", async () => {
  for (const metadata of [{ cohort: evaluationCohort() },
    { evaluation_policy: { ...evaluationPolicy(), version: "other" }, cohort: evaluationCohort() },
    { evaluation_policy: evaluationPolicy(), cohort: { ...evaluationCohort(), member_count: -1 } }]) {
    const h = pageHarness({ workerRuntime: metadata });
    try {
      await h.pump();
      assert.ok(!h.visibleText().includes("evaluation phase"));
      assert.ok(!h.visibleText().includes("Candidates are not ranked during warmup"));
    } finally { h.cleanup(); }
  }
  for (const [reason, expected] of [["paused", /paused/], ["stopped", /stopped/], ["risk_halted", /circuit breaker/],
    ["failed", /failure/], ["worker_stopped", /worker stopped/], ["private", /interrupted/]]) {
    assert.match(transport.formatEvaluationAbort(reason), expected);
    assert.ok(!transport.formatEvaluationAbort(reason).includes("private"));
  }
});

test("launch labels and validation explain modeled evaluation minutes without changing serialized fields", () => {
  const jsx = (type, props, key) => ({ type, props, key });
  let stateIndex = 0;
  const components = (names) => Object.fromEntries(names.map((name) => [name, name]));
  const { ColonyConfigDialog } = loadModule("../src/components/probes/ColonyConfigDialog.tsx", {
    react: { useState(value) { return [stateIndex++ === 2 ? true : typeof value === "function" ? value() : value, () => {}]; },
      useEffect() {}, useMemo(fn) { return fn(); } },
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "lucide-react": components(["FlaskConical", "Zap", "Settings2", "Dna", "Shield", "Timer", "Lock", "Unlock"]),
    "@/components/ui/button": components(["Button"]), "@/components/ui/checkbox": components(["Checkbox"]),
    "@/components/ui/input": components(["Input"]), "@/components/ui/label": components(["Label"]),
    "@/components/ui/dialog": components(["Dialog", "DialogContent", "DialogHeader", "DialogTitle", "DialogDescription"]),
    "@/components/ui/select": components(["Select", "SelectContent", "SelectItem", "SelectTrigger", "SelectValue"]),
    "@/components/ui/switch": components(["Switch"]), "@/components/ui/slider": components(["Slider"]),
    "@/components/ui/tooltip": components(["Tooltip", "TooltipContent", "TooltipProvider", "TooltipTrigger"]),
    "@/lib/probes/gene-registry": registry, "@/lib/probes/colony-config": configs,
    "@/lib/probes/transport": transport, "@/lib/probes/execution": execution,
    "@/lib/probes/constants": { STRATEGY_LABELS: { genetic_algorithm: "Genetic Algorithm" }, STRATEGY_DESCRIPTIONS: {}, VN_ENDPOINTS: { error: null } },
  });
  const result = JSON.stringify(ColonyConfigDialog({ open: true, onClose() {}, onStart() {}, starting: false }));
  assert.match(result, /Evaluation window \(market minutes\)/);
  assert.match(result, /Maximum candidate age \(market minutes after warmup\)/);
  assert.match(result, /0 means no age limit/);
  assert.match(result, /Self-reproduction and diversity injection wait for cohort boundaries/);
  assert.ok(!result.includes("Repro Interval (ticks)"));
  assert.ok(!result.includes("Max Lifespan (ticks"));
  const config = valid();
  config.colony_config.reproduction_interval = 0;
  config.colony_config.max_lifespan_ticks = -1;
  const errors = configs.validateStartConfig(config);
  assert.match(errors.find((issue) => issue.field === "reproduction_interval").message, /Evaluation window \(market minutes\)/);
  assert.match(errors.find((issue) => issue.field === "max_lifespan_ticks").message, /Maximum candidate age \(market minutes after warmup\)/);
});


test("DE launch requires complete funded target/trial pairs", () => {
  for (const gen0_count of [2, 4, 6, 7, 9, 11]) {
    const config = { ...valid(), strategy: "differential_evolution", gen0_count };
    assert.ok(configs.validateStartConfig(config).some((issue) => issue.field === "gen0_count"));
  }
  for (const gen0_count of [8, 10, 50]) {
    const config = { ...valid(), strategy: "differential_evolution", gen0_count,
      max_probes: gen0_count, max_capital: gen0_count * 100, seed_capital: 100 };
    assert.deepEqual(plain(configs.validateStartConfig(config)), []);
  }
});


test("search seed validation preserves uint64 text and rejects coercion", () => {
  for (const seed of ["0", "42", "9007199254740993", "18446744073709551615"]) {
    const config = { ...valid(), search_seed: seed };
    assert.deepEqual(plain(configs.validateStartConfig(config)), []);
    assert.equal(JSON.parse(JSON.stringify(config)).search_seed, seed);
  }
  for (const seed of [0, true, null, "", "01", "+1", "-1", " 1", "1 ", "1e3", "1.5", "１２", "18446744073709551616"]) {
    assert.ok(configs.validateStartConfig({ ...valid(), search_seed: seed }).some(issue => issue.field === "search_seed"));
  }
  const { search_seed, ...legacy } = valid();
  assert.equal(search_seed, "0");
  assert.deepEqual(plain(configs.validateStartConfig(legacy)), []);
});

test("saved search metadata is versioned and does not imply checkpoint restoration", () => {
  const value = { version: "search-spec-v1", stream_policy: "sha256-namespaced-search-v1", seed: "9007199254740993", algorithm: "cma_es", epoch: 2, optimizer_state_checkpointed: false, private_state: "omitted" };
  const parsed = transport.parseSearchSpec(value);
  assert.equal(parsed.seed, value.seed);
  assert.equal(parsed.epoch, 2);
  assert.equal(parsed.optimizer_state_checkpointed, false);
  assert.equal("private_state" in parsed, false);
  for (const edits of [{ seed: 1 }, { epoch: -1 }, { epoch: 1.5 }, { version: "other" }, { stream_policy: "other" }, { algorithm: "other" }, { optimizer_state_checkpointed: true }]) {
    assert.equal(transport.parseSearchSpec({ ...value, ...edits }), undefined);
  }
});

const lifecyclePolicy = {
  version: "acknowledged-terminal-sealed-generations-v1",
  terminal_event: "probe_dead",
  generation_completion: "sealed_births_all_terminal_acknowledged",
  generation_semantics: "birth_epoch_not_ancestry_depth",
  generation_diversity: "rms_pairwise_global_normalized_numeric_v1",
  generation_diversity_assets: "excluded",
  reproduced_count: "distinct_sources_with_acknowledged_offspring_before_completion",
  closed_trade_retention: 256, dead_probe_retention: 500, generation_history_retention: 100,
};

test("saved lifecycle policy requires exact semantics and bounded integer limits without leaking configuration", async () => {
  assert.deepEqual(transport.parseLifecyclePolicy({ ...lifecyclePolicy, secret: "private" }), lifecyclePolicy);
  for (const value of [undefined, null, {}, { ...lifecyclePolicy, version: "legacy" }, { ...lifecyclePolicy, generation_diversity_assets: "included" },
    { ...lifecyclePolicy, dead_probe_retention: 0 }, { ...lifecyclePolicy, closed_trade_retention: Infinity },
    { ...lifecyclePolicy, generation_history_retention: "100" }, { ...lifecyclePolicy, generation_history_retention: 1.2 }]) {
    assert.equal(transport.parseLifecyclePolicy(value), undefined);
  }
  const h = databaseHarness([
    { data: [{ id: "A", mode: "simulation", config: { runtime: { lifecycle_policy: { ...lifecyclePolicy, secret: "private" } } } }], error: null },
    { data: [], error: null },
  ]);
  const [run] = await h.api.fetchColonyRuns();
  assert.deepEqual(plain(run.runtime.lifecycle_policy), lifecyclePolicy);
  assert.ok(!JSON.stringify(run).includes("private"));
});
