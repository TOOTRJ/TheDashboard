import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import * as transport from "../src/lib/probes/transport.ts";
import * as execution from "../src/lib/probes/execution.ts";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const plain = (value) => JSON.parse(JSON.stringify(value));
const jsx = (type, props, key) => ({ type, props, key });
const components = (...names) => Object.fromEntries(names.map(name => [name, name]));
function compile(source, modules = {}, globals = {}) {
  const exports = {};
  const javascript = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(javascript, {
    exports, AbortController,
    require(name) { assert.ok(Object.hasOwn(modules, name), `Unexpected import ${name}`); return modules[name]; },
    fetch() { throw new Error("Lifecycle tests cannot access the network"); },
    ...globals,
  });
  return exports;
}
const lifecycle = compile(read("../src/lib/probes/lifecycle.ts"));
const genome = () => ({ rsi_period: 14, rsi_oversold: 30, rsi_overbought: 70,
  ema_fast: 9, ema_slow: 21, volume_threshold: 1.4, position_size_pct: .75,
  stop_loss_pct: .03, take_profit_pct: .07, max_open_positions: 1,
  timeframe_minutes: 15, benchmark_target_pct: .08, reproduce_target_dollars: 10,
  death_drawdown_pct: .2, num_assets: 1, assets: ["SOL/USDC"], generation: 0, parent_ids: [] });
const probe = (patch = {}) => ({ id: "probe", probe_name: "Candidate", state: "TRADING",
  generation: 0, parent_id: null, parent_ids: [], genome: genome(),
  initial_capital: 100, current_capital: 102, peak_capital: 105,
  total_trades: 5, winning_trades: 3, total_pnl: 2, max_drawdown: .03,
  fitness_score: -.04, sharpe_ratio: 1.5, metrics: { fitness_version: "policy", current_drawdown: .01 },
  born_at: "2024-01-01T00:00:00Z", died_at: null, death_reason: null,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", mode: "simulation", ...patch });
const when = "2024-01-01T00:10:00Z";
const birth = (patch = {}) => ({ ...probe(), probe_id: "new-probe", probe_name: "New candidate", state: "OBSERVING", max_drawdown_pct: 3, ...patch });
const event = (type, data, colony_id = "A") => ({ type, colony_id, data, timestamp: when });

test("intent never commits terminal evidence; explicit death preserves final financial and lineage fields", () => {
  const source = probe({ parent_ids: ["parent-A", "parent-B"], parent_id: "parent-A" });
  for (const kind of ["probe_dying", "probe_reproducing"]) {
    const intent = lifecycle.applyProbeEvent(source, kind, { probe_id: source.id,
      died_at: when, death_reason: "max_lifespan", current_capital: 101 }, when);
    assert.equal(intent.state, kind === "probe_dying" ? "DYING" : "REPRODUCING");
    assert.equal(intent.died_at, null);
    assert.equal(intent.death_reason, null);
    assert.equal(intent.current_capital, 101);
    const dead = lifecycle.applyProbeEvent(intent, "probe_dead", { probe_id: source.id,
      state: "DEAD", died_at: when, death_reason: "max_lifespan", current_capital: 99,
      total_pnl: -1, total_trades: 8, winning_trades: 4, fitness_score: -.12,
      max_drawdown_pct: 7, sharpe_ratio: null, metrics: { current_drawdown: .07 } }, when);
    assert.equal(dead.state, "DEAD");
    assert.equal(dead.died_at, when);
    assert.equal(dead.death_reason, "max_lifespan");
    assert.equal(dead.current_capital, 99);
    assert.equal(dead.total_pnl, -1);
    assert.equal(dead.total_trades, 8);
    assert.equal(dead.winning_trades, 4);
    assert.equal(dead.fitness_score, -.12);
    assert.equal(dead.max_drawdown, .07);
    assert.equal(dead.sharpe_ratio, null);
    assert.deepEqual(plain(dead.parent_ids), ["parent-A", "parent-B"]);
  }
  assert.equal(source.current_capital, 102);
});

test("sparse updates preserve omitted metrics and a terminal record cannot be revived by later intents", () => {
  const source = probe();
  const updated = lifecycle.applyProbeEvent(source, "probe_update", { probe_id: source.id,
    current_capital: 0, total_trades: Infinity, total_pnl: NaN, sharpe_ratio: null,
    metrics: { current_drawdown: .2 }, genome: { parent_ids: ["p"] }, state: "DEAD" }, when);
  assert.equal(updated.current_capital, 0);
  assert.equal(updated.total_trades, source.total_trades);
  assert.equal(updated.total_pnl, source.total_pnl);
  assert.equal(updated.sharpe_ratio, null);
  assert.equal(updated.state, "TRADING");
  assert.equal(updated.metrics.fitness_version, "policy");
  assert.equal(updated.genome.rsi_period, 14);
  assert.equal(updated.born_at, source.born_at);
  const dead = probe({ state: "DEAD", died_at: when, death_reason: "evolution_culled" });
  for (const kind of ["probe_update", "probe_dying", "probe_reproducing", "probe_born"]) {
    assert.equal(lifecycle.applyProbeEvent(dead, kind, { probe_id: dead.id, state: "TRADING", died_at: null }), dead);
  }
  assert.equal(lifecycle.applyProbeEvent(source, "probe_dead", { probe_id: "another" }), source);
});

test("lineage resolves legacy empty-array defaults, malformed JSON and all distinct source identities", () => {
  for (const row of [undefined, null, [], "bad-json", {}]) {
    const source = probe({ parent_ids: row, parent_id: "legacy", genome: { ...genome(), parent_ids: ["genome-source"] } });
    assert.deepEqual(plain(lifecycle.probeParentIds(source)), ["genome-source"]);
    source.genome.parent_ids = [];
    assert.deepEqual(plain(lifecycle.probeParentIds(source)), ["legacy"]);
  }
  assert.deepEqual(plain(lifecycle.probeParentIds(probe({ parent_ids: ["", 2, "probe", "first", "second", "first"] }))), ["first", "second"]);
  const mapped = lifecycle.mapProbeEvent({ probe_id: "child", parent_ids: [], parent_id: "old" });
  assert.deepEqual(plain(mapped.parent_ids), ["old"]);
  assert.equal(mapped.parent_id, "old");
});

test("only complete birth events introduce renderable candidates; sparse updates do not invent a candidate", () => {
  assert.equal(lifecycle.probeFromBirth({ probe_id: "new" }, when), null);
  assert.equal(lifecycle.probeFromBirth(birth({ fitness_score: NaN }), when), null);
  assert.equal(lifecycle.probeFromBirth(birth({ born_at: "invalid" }), when), null);
  const created = lifecycle.probeFromBirth(birth({ genome: { ...genome(), parent_ids: ["a", "b"] } }), when);
  assert.equal(created.id, "new-probe");
  assert.equal(created.current_capital, 102);
  assert.deepEqual(plain(created.parent_ids), ["a", "b"]);
  assert.equal(created.died_at, null);
});

// Extract the real React callback bodies through the TypeScript AST. Tests run
// the production guard, reducer and async read code, without rewriting them or
// depending on hook call indices. Imports are supplied as explicit offline stubs.
const pageSource = read("../src/app/(dashboard)/probes/page.tsx");
const pageAst = ts.createSourceFile("page.tsx", pageSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function pageCallback(name, globals) {
  let initializer;
  const visit = (node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === name) initializer = node.initializer;
    ts.forEachChild(node, visit);
  };
  visit(pageAst);
  assert.ok(initializer && ts.isCallExpression(initializer), `Missing actual page callback ${name}`);
  return compile(`exports.run = ${initializer.arguments[0].getText(pageAst)};`, {}, globals).run;
}
function pageCallbacks() {
  const scope = transport.createSelectionScope(); scope.select("A");
  const state = { probes: [probe()], stats: [], loading: true, errors: [] };
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  let reads = 0;
  const set = key => value => { state[key] = typeof value === "function" ? value(state[key]) : value; };
  const common = { scope, belongsToSelectedColony: transport.belongsToSelectedColony,
    ...lifecycle, setProbes: set("probes"), setGenStats: set("stats"), setLoading: set("loading"),
    reportError: (...args) => state.errors.push(args), setSystemStatus() {}, setSimStatus() {}, setSimMode() {},
    prevPrices: { current: {} }, setPrices() {},
    fetchProbes: async id => { assert.equal(id, "A"); reads++; await pending; return [probe({ current_capital: 55 })]; },
    fetchGenerationStats: async id => { assert.equal(id, "A"); await pending; return []; },
  };
  return { state, scope, release, reads: () => reads,
    event: pageCallback("handleWsMessage", common), read: pageCallback("refreshSelected", common) };
}

test("actual page ignores older pending reads after every structural lifecycle event and releases loading", async () => {
  for (const kind of ["probe_born", "probe_dying", "probe_reproducing", "probe_dead", "generation_complete"]) {
    const h = pageCallbacks();
    const read = h.read();
    const data = kind === "probe_born" ? birth() : kind === "generation_complete" ? { generation: 7, total_probes: 4 }
      : { probe_id: "probe", state: "DEAD", died_at: when, death_reason: "max_lifespan", current_capital: 99 };
    h.event(event(kind, data));
    assert.equal(h.state.loading, false, kind);
    const afterEvent = plain(h.state);
    h.release(); await read;
    assert.deepEqual(plain(h.state), afterEvent, kind);
    if (kind === "probe_dead") assert.equal(h.state.probes[0].state, "DEAD");
    if (kind === "generation_complete") assert.equal(h.state.stats[0].generation, 7);
    if (kind === "probe_born") assert.equal(h.state.probes.length, 2);
  }
});

test("actual page frequent metric updates do not starve polling; next read refreshes after a structural event", async () => {
  const h = pageCallbacks();
  const pending = h.read();
  for (let i = 0; i < 100; i++) h.event(event("probe_update", { probe_id: "probe", current_capital: i }));
  assert.equal(h.state.loading, true);
  h.release(); await pending;
  assert.equal(h.state.loading, false);
  assert.equal(h.state.probes[0].current_capital, 55);
  const first = h.read();
  h.event(event("probe_dying", { probe_id: "probe" }));
  await first;
  assert.equal(h.state.probes[0].state, "DYING");
  await h.read();
  assert.equal(h.reads(), 3);
  assert.equal(h.state.probes[0].current_capital, 55);
});

test("actual page rejects other-colony events before invalidating reads or releasing loading", async () => {
  const h = pageCallbacks(); const pending = h.read();
  for (const colony of ["B", null]) h.event(event("probe_dead", { probe_id: "probe", current_capital: -999 }, colony));
  // Explicitly omit the field to test missing ownership as well.
  h.event({ type: "probe_dead", data: { probe_id: "probe" } });
  assert.equal(h.state.loading, true);
  assert.equal(h.state.probes[0].state, "TRADING");
  h.release(); await pending;
  assert.equal(h.state.probes[0].current_capital, 55);
});

const uiModules = {
  "@/lib/probes/execution": execution,
  "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "Fragment" },
  "lucide-react": components("Clock", "Skull", "Sparkles"),
  "@/components/ui/card": components("Card", "CardHeader", "CardContent"),
  "@/components/ui/badge": components("Badge"), "@/components/ui/button": components("Button"),
  "@/components/ui/dialog": components("Dialog", "DialogContent", "DialogHeader", "DialogTitle"),
  "@/lib/probes/constants": { STATE_COLORS: { TRADING: "green", DYING: "red", REPRODUCING: "blue", DEAD: "gray" },
    STATE_LABELS: { TRADING: "Trading", DYING: "Dying", REPRODUCING: "Reproducing", DEAD: "Dead" } },
  "@/lib/probes/gene-registry": { GENE_DEFINITIONS: [] }, "@/lib/probes/lifecycle": lifecycle,
  "./GenomeRadar": components("GenomeRadar"), "./TradeLog": components("TradeLog"),
};
const { ProbeDetail } = compile(read("../src/components/probes/ProbeDetail.tsx"), uiModules);
const { GenealogyTree } = compile(read("../src/components/probes/GenealogyTree.tsx"), uiModules);
function visible(node) {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(visible).join(" ");
  return node && typeof node === "object" ? visible(node.props?.children) : "";
}
function findAll(node, predicate, found = []) {
  if (!node || typeof node !== "object") return found;
  if (predicate(node)) found.push(node);
  const children = node.props?.children;
  for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) findAll(child, predicate, found);
  return found;
}

test("actual detail distinguishes pending intent and missing legacy death time from a confirmed terminal timestamp", () => {
  for (const [state, label] of [["DYING", "Awaiting terminal confirmation"], ["REPRODUCING", "Awaiting replacement confirmation"]]) {
    const output = visible(ProbeDetail({ probe: probe({ state, died_at: when, death_reason: "intent-only" }), open: true, onClose() {} }));
    assert.match(output, new RegExp(label));
    assert.ok(!output.includes("Died"));
    assert.ok(!output.includes("Alive"));
    assert.ok(!output.includes("intent-only"));
  }
  const legacy = visible(ProbeDetail({ probe: probe({ state: "DEAD" }), open: true, onClose() {} }));
  assert.match(legacy, /Terminal record · death time unavailable/);
  assert.ok(!legacy.includes("Alive"));
  const dead = visible(ProbeDetail({ probe: probe({ state: "DEAD", died_at: when, death_reason: "evolution_culled" }), open: true, onClose() {} }));
  assert.match(dead, /Died/);
  assert.match(dead, /10m 0s/);
  assert.match(dead, /evolution_culled/);
});

test("actual genealogy lists all sources with missing-history and accessible state labels; detail exposes all IDs", () => {
  const parent = probe({ id: "parent-A", probe_name: "Parent A" });
  const child = probe({ id: "child", parent_ids: ["parent-A", "parent-B"], generation: 1 });
  const chosen = [];
  const tree = GenealogyTree({ probes: [child, parent], onSelectProbe: value => chosen.push(value.id) });
  const text = visible(tree);
  assert.match(text, /No recorded sources/);
  assert.match(text, /parent-B\s+· outside loaded history/);
  assert.match(text, /Trading/);
  const sourceButton = findAll(tree, node => node.type === "button" && node.props.children === "Parent A")[0];
  sourceButton.props.onClick();
  assert.deepEqual(chosen, ["parent-A"]);
  const detail = visible(ProbeDetail({ probe: child, open: true, onClose() {} }));
  assert.match(detail, /Sources:\s+parent-A, parent-B/);
});

test("actual dashboard keeps an open detail attached to the latest probe record", () => {
  const hooks = []; let index = 0;
  const react = { useState(initial) {
    const position = index++;
    if (!(position in hooks)) hooks[position] = typeof initial === "function" ? initial() : initial;
    return [hooks[position], value => { hooks[position] = value; }];
  } };
  const modules = { react, "react/jsx-runtime": { jsx, jsxs: jsx },
    "@/components/ui/tabs": components("Tabs", "TabsContent", "TabsList", "TabsTrigger") };
  for (const name of ["SimulationControls", "ProbesOverview", "ProbeGrid", "ProbeDetail", "FitnessChart",
    "GenerationTimeline", "GenealogyTree", "ColonySelector", "PriceFeed"]) modules[`./${name}`] = components(name);
  const { ProbesDashboard } = compile(read("../src/components/probes/ProbesDashboard.tsx"), modules);
  const source = probe();
  const props = { probes: [source], generationStats: [], systemStatus: null,
    connected: true, simStatus: "running", mode: "simulation", activeColonies: [],
    starting: false, recoveryAvailable: false, controlPending: false, colonyRuns: [], activeRunId: "A", prices: {} };
  const render = values => { index = 0; return ProbesDashboard(values); };
  let output = render(props);
  findAll(output, node => node.type === "ProbeGrid")[0].props.onSelectProbe(source);
  const final = { ...source, state: "DEAD", died_at: when, death_reason: "max_lifespan", current_capital: 99 };
  output = render({ ...props, probes: [final] });
  const detail = findAll(output, node => node.type === "ProbeDetail")[0];
  assert.equal(detail.props.open, true);
  assert.equal(detail.props.probe, final);
  assert.equal(detail.props.probe.state, "DEAD");
  assert.equal(detail.props.probe.current_capital, 99);
});

test("acknowledged generation updates replace the same birth epoch without duplicate cards", () => {
  const h = pageCallbacks();
  h.event(event("generation_complete", { generation: 2, total_probes: 4 }));
  h.event(event("generation_complete", { generation: 1, total_probes: 3 }));
  h.event(event("generation_complete", { generation: 2, total_probes: 5 }));
  assert.deepEqual(plain(h.state.stats).map(row => [row.generation, row.total_probes]), [[1, 3], [2, 5]]);
});
