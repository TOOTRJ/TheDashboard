import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import * as registry from "../src/lib/probes/gene-registry.ts";
import * as transport from "../src/lib/probes/transport.ts";
import * as execution from "../src/lib/probes/execution.ts";
import { parseSignalPolicy, savedSignalPolicy, signalPolicyDescription } from "../src/lib/probes/signal-profile.ts";

const plain = (value) => JSON.parse(JSON.stringify(value));
const components = (...names) => Object.fromEntries(names.map(name => [name, name]));
const jsx = (type, props, key) => ({ type, props, key });
function compile(path, modules) {
  const exports = {};
  const source = fs.readFileSync(new URL(path, import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(output, { exports, AbortController,
    require(name) { assert.ok(Object.hasOwn(modules, name), `Unexpected import ${name}`); return modules[name]; },
    fetch() { throw new Error("Profile tests must remain offline"); },
  });
  return exports;
}
const configApi = compile("../src/lib/probes/colony-config.ts", {
  "./gene-registry": registry, "./transport": transport, "./execution": execution,
});
const baseline = () => ({ ...configApi.buildDefaultStartConfig(), preset: "ema_baseline_v1",
  colony_config: plain(configApi.PRESETS.find(preset => preset.name === "ema_baseline_v1").config) });
const emaPolicy = () => ({ version: "ema-crossover-v1", profile: "ema_baseline_v1",
  rsi_enabled: false, volume_enabled: false, warmup_completed_bars: 61,
  entry: "previous_fast_lte_slow_then_fast_gt_slow", exit: "previous_fast_gte_slow_then_fast_lt_slow",
  execution: "later_eligible_quote" });
const legacyPolicy = () => ({ version: "rsi-ema-volume-v1", profile: "rsi_ema_volume_v1",
  rsi_enabled: true, volume_enabled: true, warmup_completed_bars: null,
  entry: "rsi_oversold_ema_above_and_volume", exit: "rsi_overbought_or_ema_below",
  execution: "later_eligible_quote" });

test("the baseline is opt-in and its declared experiment has exactly two search genes", () => {
  const current = configApi.buildDefaultStartConfig();
  assert.equal(current.colony_config.strategy_profile, "rsi_ema_volume_v1");
  delete current.colony_config.strategy_profile;
  assert.equal(configApi.validateStartConfig(current).length, 0, "old requests retain legacy behavior");
  const config = baseline();
  assert.deepEqual(plain(configApi.validateStartConfig(config)), []);
  assert.deepEqual(config.colony_config.enabled_genes, ["ema_fast", "ema_slow"]);
  assert.deepEqual(config.colony_config.available_assets, ["SOL/USDC"]);
  assert.equal(config.colony_config.reproduction_interval, 1440);
  assert.equal(config.colony_config.max_lifespan_ticks, null);
  assert.deepEqual(config.colony_config.gene_overrides.ema_fast, { min: 3, max: 12, default: 9 });
  assert.deepEqual(config.colony_config.gene_overrides.ema_slow, { min: 15, max: 60, default: 21 });
  assert.equal(config.colony_config.gene_overrides.position_size_pct.fixed, .25);
  assert.equal(config.colony_config.gene_overrides.timeframe_minutes.fixed, 15);
});

test("baseline API validation rejects profile ambiguity and additional behavior dimensions", () => {
  const invalid = [
    { strategy_profile: null }, { strategy_profile: "private-unknown-profile" },
    { strategy_profile: "rsi_ema_volume_v1" },
    { enabled_genes: null }, { enabled_genes: [] }, { enabled_genes: ["ema_fast"] },
    { enabled_genes: ["ema_fast", "ema_fast"] },
    { enabled_genes: ["ema_fast", "ema_slow", "rsi_period"] },
    { available_assets: null }, { available_assets: [] }, { available_assets: ["SOL/USDC", "JUP/USDC"] },
    { max_lifespan_ticks: 0 }, { max_lifespan_ticks: 100 },
    { reproduction_interval: 0 }, { reproduction_interval: 1.5 },
    { gene_overrides: { max_open_positions: { fixed: 2 } } },
    { gene_overrides: { num_assets: { fixed: 2 } } },
    { gene_overrides: { ema_fast: { fixed: 20 }, ema_slow: { fixed: 15 } } },
  ];
  for (const change of invalid) {
    const config = baseline();
    config.colony_config = { ...config.colony_config, ...change };
    assert.ok(configApi.validateStartConfig(config).length, JSON.stringify(change));
  }
});

test("fixed controls may change between runs and fixed EMA grid controls remain legal", () => {
  const config = baseline();
  config.colony_config.enabled_genes.reverse();
  config.colony_config.available_assets = ["BONK/USDC"];
  config.colony_config.reproduction_interval = 480;
  Object.assign(config.colony_config.gene_overrides, {
    ema_fast: { min: 5, max: 5, default: 5 }, ema_slow: { fixed: 20 },
    position_size_pct: { fixed: .1 }, stop_loss_pct: { fixed: .02 },
    timeframe_minutes: { fixed: 5 }, death_drawdown_pct: { fixed: .3 },
  });
  assert.deepEqual(plain(configApi.validateStartConfig(config)), []);
  assert.deepEqual(plain(configApi.validateStartConfig(JSON.parse(JSON.stringify(config)))), []);
});

test("signal policy parsing requires the entire known semantic contract and strips unknown fields", () => {
  for (const policy of [emaPolicy(), legacyPolicy()]) {
    assert.deepEqual(parseSignalPolicy({ ...policy, private_detail: "never display" }), policy);
    assert.equal("private_detail" in parseSignalPolicy({ ...policy, private_detail: "never display" }), false);
    for (const field of Object.keys(policy)) {
      const missing = { ...policy }; delete missing[field];
      assert.equal(parseSignalPolicy(missing), undefined, field);
    }
  }
  for (const change of [{ version: "unknown" }, { profile: "rsi_ema_volume_v1" },
    { rsi_enabled: true }, { volume_enabled: 0 }, { warmup_completed_bars: 60 },
    { warmup_completed_bars: "61" }, { entry: "fast_above" }, { exit: "fast_below" },
    { execution: "same_close" }]) assert.equal(parseSignalPolicy({ ...emaPolicy(), ...change }), undefined);
  for (const absent of [null, undefined, [], {}, "ema_baseline_v1"]) assert.equal(parseSignalPolicy(absent), undefined);
});

test("saved policies use initial metadata only when the runtime field is absent", () => {
  assert.deepEqual(savedSignalPolicy({ signal_policy: emaPolicy() }), emaPolicy());
  assert.deepEqual(savedSignalPolicy({ signal_policy: emaPolicy(), runtime: {} }), emaPolicy());
  assert.deepEqual(savedSignalPolicy({ signal_policy: legacyPolicy(), runtime: { signal_policy: emaPolicy() } }), emaPolicy());
  for (const value of [null, {}, { ...emaPolicy(), version: "new" }]) {
    assert.equal(savedSignalPolicy({ signal_policy: emaPolicy(), runtime: { signal_policy: value } }), undefined);
  }
  assert.equal(savedSignalPolicy(baseline()), undefined, "a preset name is not policy evidence");
  assert.match(signalPolicyDescription(emaPolicy()), /RSI and volume filters are off/);
  assert.match(signalPolicyDescription(emaPolicy()), /61 completed timeframe bars/);
  assert.match(signalPolicyDescription(legacyPolicy()), /EMA trend/);
  assert.match(signalPolicyDescription({ ...emaPolicy(), exit: "PRIVATE" }), /unavailable/);
  assert.ok(!signalPolicyDescription({ ...emaPolicy(), exit: "PRIVATE" }).includes("PRIVATE"));
});

function nodes(node, predicate) {
  if (Array.isArray(node)) return node.flatMap(item => nodes(item, predicate));
  if (!node || typeof node !== "object") return [];
  return [...(predicate(node) ? [node] : []), ...nodes(node.props?.children, predicate)];
}
function visibleText(node) {
  if (Array.isArray(node)) return node.map(visibleText).join(" ");
  if (node == null || typeof node === "boolean") return "";
  return typeof node === "object" ? visibleText(node.props?.children) : String(node);
}
function dialogHarness() {
  let cursor = 0; const state = [], submitted = [];
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial;
      return [state[index], next => { state[index] = typeof next === "function" ? next(state[index]) : next; }];
    }, useEffect() {}, useMemo(fn) { return fn(); },
  };
  const modules = {
    react, "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "Fragment" },
    "lucide-react": components("FlaskConical", "Zap", "Settings2", "Dna", "Shield", "Timer", "Lock", "Unlock"),
    "@/components/ui/button": components("Button"), "@/components/ui/checkbox": components("Checkbox"),
    "@/components/ui/input": components("Input"), "@/components/ui/label": components("Label"),
    "@/components/ui/dialog": components("Dialog", "DialogContent", "DialogHeader", "DialogTitle", "DialogDescription"),
    "@/components/ui/select": components("Select", "SelectContent", "SelectItem", "SelectTrigger", "SelectValue"),
    "@/components/ui/switch": components("Switch"), "@/components/ui/slider": components("Slider"),
    "@/components/ui/tooltip": components("Tooltip", "TooltipContent", "TooltipProvider", "TooltipTrigger"),
    "@/lib/probes/gene-registry": registry, "@/lib/probes/colony-config": configApi,
    "@/lib/probes/transport": transport, "@/lib/probes/execution": execution,
    "@/lib/probes/constants": { STRATEGY_LABELS: { genetic_algorithm: "GA" }, STRATEGY_DESCRIPTIONS: {}, VN_ENDPOINTS: {} },
  };
  const { ColonyConfigDialog } = compile("../src/components/probes/ColonyConfigDialog.tsx", modules);
  const render = () => { cursor = 0; return ColonyConfigDialog({ open: true, starting: false,
    onClose() {}, onStart: async value => { submitted.push(plain(value)); return true; } }); };
  const choosePreset = name => { nodes(render(), node => node.type === "Select")[1].props.onValueChange(name); return render(); };
  const input = (id, value) => { const control = nodes(render(), node => node.type === "Input" && node.props.id === id)[0]; assert.ok(control, id); control.props.onChange({ target: { value: String(value) } }); return render(); };
  const launch = () => { const button = nodes(render(), node => node.type === "Button" && visibleText(node) === "Launch Colony")[0]; assert.ok(button); button.props.onClick(); return render(); };
  return { render, choosePreset, input, launch, submitted };
}

test("actual baseline dialog exposes only EMA ranges and one asset, then submits explicit profile and costs", () => {
  const h = dialogHarness();
  assert.ok(nodes(h.render(), node => node.type === "Checkbox").length > 2);
  h.input("execution-fee_bps", 12);
  const output = h.choosePreset("ema_baseline_v1");
  assert.equal(nodes(output, node => node.type === "Checkbox" || node.type === "Switch").length, 0);
  assert.equal(nodes(output, node => node.type === "Input" && String(node.props.id).startsWith("baseline-ema_")).length, 4);
  assert.match(visibleText(output), /RSI and volume filters are off/);
  assert.match(visibleText(output), /61 completed timeframe bars/);
  assert.match(visibleText(output), /1,440 modeled minutes \(24 hours\)/);
  h.input("baseline-ema_fast-min", 10);
  h.input("baseline-ema_fast-max", 11);
  h.input("baseline-horizon", 720);
  const assetSelect = nodes(h.render(), node => node.type === "Select")[2];
  assetSelect.props.onValueChange("JUP/USDC");
  h.launch();
  assert.equal(h.submitted.length, 1);
  const request = h.submitted[0];
  assert.equal(request.colony_config.strategy_profile, "ema_baseline_v1");
  assert.deepEqual(request.colony_config.enabled_genes, ["ema_fast", "ema_slow"]);
  assert.deepEqual(request.colony_config.available_assets, ["JUP/USDC"]);
  assert.deepEqual(request.colony_config.gene_overrides.ema_fast, { min: 10, max: 11, default: 10 });
  assert.equal(request.colony_config.reproduction_interval, 720);
  assert.equal(request.execution.fee_bps, 12);
  assert.deepEqual(plain(configApi.validateStartConfig(request)), []);
});

test("actual dialog switching out of the baseline restores legacy profile and gene controls", () => {
  const h = dialogHarness();
  h.choosePreset("ema_baseline_v1");
  const output = h.choosePreset("rsi_focus");
  assert.ok(nodes(output, node => node.type === "Checkbox").length > 2);
  assert.equal(nodes(output, node => node.props?.id === "baseline-horizon").length, 0);
  h.launch();
  assert.equal(h.submitted.length, 1);
  assert.equal(h.submitted[0].colony_config.strategy_profile, "rsi_ema_volume_v1");
  h.choosePreset("ema_baseline_v1");
  h.launch();
  assert.equal(h.submitted[1].colony_config.strategy_profile, "ema_baseline_v1");
  assert.equal(h.submitted[1].colony_config.reproduction_interval, 1440);
  assert.deepEqual(h.submitted[1].colony_config.available_assets, ["SOL/USDC"]);
});

test("actual baseline dialog rejects noninteger EMA ranges and empty horizons before launch", () => {
  const h = dialogHarness(); h.choosePreset("ema_baseline_v1");
  h.input("baseline-ema_fast-min", 3.5); h.launch();
  assert.equal(h.submitted.length, 0);
  assert.match(visibleText(h.render()), /whole number/);
  h.choosePreset("ema_baseline_v1"); h.input("baseline-horizon", ""); h.launch();
  assert.equal(h.submitted.length, 0);
  assert.match(visibleText(h.render()), /Evaluation window/);
  h.input("baseline-horizon", 1440);
  h.input("baseline-ema_fast-min", ""); h.launch();
  assert.equal(h.submitted.length, 0);
  h.input("baseline-ema_fast-min", 5); h.launch();
  assert.equal(h.submitted.length, 1, "correcting an empty range does not poison its default");
});
