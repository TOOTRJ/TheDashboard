import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import * as execution from "../src/lib/probes/execution.ts";
import * as transport from "../src/lib/probes/transport.ts";
import * as registry from "../src/lib/probes/gene-registry.ts";
import * as signalProfiles from "../src/lib/probes/signal-profile.ts";

const plain = value => JSON.parse(JSON.stringify(value));
const jsx = (type, props, key) => ({ type, props, key });
const stubs = (...names) => Object.fromEntries(names.map(name => [name, name]));
function compile(path, modules = {}, globals = {}) {
  const exports = {};
  const source = fs.readFileSync(new URL(path, import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  vm.runInNewContext(output, { exports, AbortController,
    require(name) { assert.ok(Object.hasOwn(modules, name), `Unexpected import ${name}`); return modules[name]; },
    fetch() { throw new Error("Execution UI tests must remain offline"); }, ...globals,
  });
  return exports;
}
const configModule = compile("../src/lib/probes/colony-config.ts", {
  "./execution": execution, "./transport": transport, "./gene-registry": registry,
});
const policy = (config = execution.defaultExecutionConfig()) => ({
  version: "usd-reference-percentage-cost-v1", account_currency: "USD", valuation: "reference_mark",
  cost_assumptions: "uncalibrated_scenario", config,
});
const ledger = () => ({ version: policy().version, account_currency: "USD",
  config: { fee_bps: 100, half_spread_bps: 0, slippage_bps: 0 },
  entry: { reference_price: 100, fill_price: 100, quantity: 1, notional: 100,
    fee: 1, cash_debit: 101, spread_cost: 0, slippage_cost: 0 },
  exit: { kind: "fill", reference_price: 110, fill_price: 110, quantity: 1, notional: 110,
    fee: 1.1, cash_credit: 108.9, spread_cost: 0, slippage_cost: 0,
    gross_pnl: 10, net_pnl: 7.9, net_return: 7.9 / 101 },
});
function text(node) {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(text).join(" ");
  return node && typeof node === "object" ? text(node.props?.children) : "";
}
function nodes(node, predicate, found = []) {
  if (!node || typeof node !== "object") return found;
  if (predicate(node)) found.push(node);
  const children = node.props?.children;
  for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) nodes(child, predicate, found);
  return found;
}
const ui = {
  "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "Fragment" },
  "@/lib/probes/execution": execution,
  "lucide-react": stubs("Clock", "Skull", "Sparkles", "TrendingUp", "TrendingDown", "Radio"),
  "@/components/ui/badge": stubs("Badge"), "@/components/ui/button": stubs("Button"),
  "@/components/ui/card": stubs("Card", "CardContent", "CardHeader"),
  "@/components/ui/dialog": stubs("Dialog", "DialogContent", "DialogHeader", "DialogTitle", "DialogDescription"),
  "@/lib/probes/constants": { STATE_COLORS: { TRADING: "green" }, STATE_LABELS: { TRADING: "Trading" } },
  "@/lib/probes/gene-registry": registry,
  "@/lib/probes/lifecycle": compile("../src/lib/probes/lifecycle.ts"),
  "./TradeLog": stubs("TradeLog"), "./GenomeRadar": stubs("GenomeRadar"),
};

test("execution request defaults are explicit and validation enforces complete finite cost configuration", () => {
  const valid = configModule.buildDefaultStartConfig();
  assert.deepEqual(plain(valid.execution), execution.defaultExecutionConfig());
  assert.equal(configModule.validateStartConfig(valid).length, 0);
  delete valid.execution;
  assert.equal(configModule.validateStartConfig(valid).length, 0);
  for (const entry of [null, [], {}, { fee_bps: 1 }, { ...execution.defaultExecutionConfig(), extra: 0 },
    { fee_bps: true, half_spread_bps: 0, slippage_bps: 0 },
    { fee_bps: "1", half_spread_bps: 0, slippage_bps: 0 },
    { fee_bps: NaN, half_spread_bps: 0, slippage_bps: 0 },
    { fee_bps: Infinity, half_spread_bps: 0, slippage_bps: 0 },
    { fee_bps: -1, half_spread_bps: 0, slippage_bps: 0 },
    { fee_bps: 10000, half_spread_bps: 0, slippage_bps: 0 },
    { fee_bps: 0, half_spread_bps: 5000, slippage_bps: 5000 },
    { fee_bps: 0, half_spread_bps: -1, slippage_bps: 1 }]) {
    assert.ok(configModule.validateStartConfig({ ...valid, execution: entry }).some(issue => issue.field === "execution"));
  }
  assert.equal(configModule.validateStartConfig({ ...valid, execution: {
    fee_bps: 9999.9, half_spread_bps: 5000, slippage_bps: 4999.9,
  } }).length, 0);
});

test("policy parsing leaves legacy and unknown currencies unclassified and strips unapproved metadata", () => {
  for (const input of [null, {}, [], { ...policy(), account_currency: "USDC" },
    { ...policy(), version: "future" }, { ...policy(), config: {} }]) {
    assert.equal(execution.parseExecutionPolicy(input), undefined);
  }
  assert.deepEqual(execution.parseExecutionPolicy({ ...policy(), private: "secret" }), policy());
  assert.equal(execution.isFrictionless(policy().config), true);
  assert.equal(execution.isFrictionless({ ...policy().config, fee_bps: 0.01 }), false);
});

test("trade execution parsing preserves open, closed and explicit zero writeoff without invented fees", () => {
  const input = ledger();
  assert.deepEqual(execution.parseTradeExecution(input), input);
  assert.deepEqual(execution.parseTradeExecution({ ...input, exit: null }).exit, null);
  const writeoff = { kind: "writeoff", reference_price: 0, fill_price: 0, quantity: 1,
    notional: 0, fee: 0, cash_credit: 0, spread_cost: 0, slippage_cost: 0,
    gross_pnl: -100, net_pnl: -101, net_return: -1 };
  assert.deepEqual(execution.parseTradeExecution({ ...input, exit: writeoff }).exit, writeoff);
  for (const bad of [undefined, null, {}, { ...input, account_currency: "USDC" },
    { ...input, exit: undefined }, { ...input, entry: { ...input.entry, fee: NaN } },
    { ...input, entry: { ...input.entry, quantity: 0 } },
    { ...input, exit: { ...input.exit, cash_credit: -1 } },
    { ...input, exit: { ...writeoff, fee: 1 } }]) assert.equal(execution.parseTradeExecution(bad), undefined);
  const cleaned = execution.parseTradeExecution({ ...input, private: "secret", entry: { ...input.entry, private: "secret" } });
  assert.ok(!JSON.stringify(cleaned).includes("secret"));
});

test("tiny valid prices and costs remain visible while nonfinite values are unavailable", () => {
  for (const amount of [0.000025, 1e-12, -0.000003, 1e-100]) {
    const formatted = execution.formatReferenceNumber(amount);
    assert.notEqual(Number(formatted), 0);
    assert.equal(Math.sign(Number(formatted)), Math.sign(amount));
  }
  assert.equal(execution.formatReferenceNumber(0), "0.00");
  for (const amount of [NaN, Infinity, null, "1"]) assert.equal(execution.formatReferenceNumber(amount), "Unavailable");
});

test("actual policy and cost details identify uncalibrated scenarios, embedded costs and unknown legacy records", () => {
  const { ExecutionPolicyNotice } = compile("../src/components/probes/ExecutionPolicyNotice.tsx", ui);
  const { TradeExecutionDetails } = compile("../src/components/probes/TradeExecutionDetails.tsx", ui);
  assert.match(text(ExecutionPolicyNotice({ policy: policy() })), /frictionless mechanics control/);
  assert.match(text(ExecutionPolicyNotice({ policy: policy() })), /no USDC conversion/i);
  assert.match(text(ExecutionPolicyNotice({})), /unclassified/);
  assert.match(text(TradeExecutionDetails({ execution: null })), /Cost accounting unavailable/);
  const closed = text(TradeExecutionDetails({ execution: ledger() }));
  assert.match(closed, /Gross P&L before fees/);
  assert.match(closed, /7.90/);
  assert.match(closed, /embedded in fill prices, not extra cash debits/);
  assert.match(text(TradeExecutionDetails({ execution: { ...ledger(), exit: null } })), /Not realized; position remains open/);
});

test("actual probe views use reported marked equity ROI rather than cash divided by initial capital", () => {
  const { ProbeCard } = compile("../src/components/probes/ProbeCard.tsx", ui);
  const { ProbeDetail } = compile("../src/components/probes/ProbeDetail.tsx", ui);
  const accounting = { execution_policy: policy(), cash: 25, position_value: 75, equity: 100, roi: 0, valuation_available: true };
  const probe = { id: "p", state: "TRADING", current_capital: 25, initial_capital: 100,
    total_trades: 0, total_pnl: 0, fitness_score: 0, generation: 0, max_drawdown: 0,
    born_at: "2024-01-01T00:00:00Z", genome: {}, metrics: { accounting } };
  for (const render of [() => ProbeCard({ probe, onClick() {} }), () => ProbeDetail({ probe, open: true, onClose() {} })]) {
    const output = text(render());
    assert.match(output, /Cash \(USD\)/);
    assert.match(output, /100.00/);
    assert.match(output, /0.00%/);
    assert.ok(!output.includes("-75"));
  }
  probe.metrics = {};
  const legacy = text(ProbeCard({ probe, onClick() {} }));
  assert.match(legacy, /unit unverified/);
  assert.match(legacy, /Equity ROI:\s+Unavailable/);
  const unavailable = execution.parseProbeAccounting({ ...accounting, valuation_available: false, equity: 999 });
  assert.equal(unavailable.equity, null);
  assert.equal(unavailable.roi, null);
});

test("actual price strip describes last-reported synthetic data and preserves tiny source prices", () => {
  const { PriceFeed } = compile("../src/components/probes/PriceFeed.tsx", { ...ui, react: {} });
  const output = PriceFeed({ prices: { BONK: { asset: "BONK/USDC", price: .000025, timestamp: 1704067200 } }, mode: "simulation", policy: policy() });
  assert.match(text(output), /Last reported synthetic prices/);
  assert.match(text(output), /USD/);
  assert.match(text(output), /0.000025000/);
  assert.ok(!text(output).includes("Live Prices"));
  assert.ok(nodes(output, node => String(node.props?.title).includes("2024-01-01T00:00:00.000Z")).length);
});

test("actual config dialog shows cost controls before advanced settings and submits their exact immutable values", async () => {
  let hook = 0; const state = [];
  const react = { useState(initial) { const index = hook++; if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial;
    return [state[index], next => { state[index] = typeof next === "function" ? next(state[index]) : next; }]; },
    useEffect() {}, useMemo(fn) { return fn(); } };
  const modules = { ...ui, react, "lucide-react": stubs("FlaskConical", "Zap", "Settings2", "Dna", "Shield", "Timer", "Lock", "Unlock"),
    "@/lib/probes/constants": { STRATEGY_LABELS: { genetic_algorithm: "GA" }, STRATEGY_DESCRIPTIONS: {}, VN_ENDPOINTS: {} },
    "@/lib/probes/transport": transport, "@/lib/probes/colony-config": configModule,
    "@/components/ui/checkbox": stubs("Checkbox"), "@/components/ui/input": stubs("Input"), "@/components/ui/label": stubs("Label"),
    "@/components/ui/select": stubs("Select", "SelectContent", "SelectItem", "SelectTrigger", "SelectValue"),
    "@/components/ui/switch": stubs("Switch"), "@/components/ui/slider": stubs("Slider"),
    "@/components/ui/tooltip": stubs("Tooltip", "TooltipContent", "TooltipProvider", "TooltipTrigger"),
  };
  const { ColonyConfigDialog } = compile("../src/components/probes/ColonyConfigDialog.tsx", modules);
  const submitted = [];
  const render = () => { hook = 0; return ColonyConfigDialog({ open: true, onClose() {}, starting: false, onStart: async value => { submitted.push(value); return true; } }); };
  let output = render();
  assert.match(text(output), /frictionless mechanics control/);
  for (const [key, value] of [["fee_bps", 12], ["half_spread_bps", 4], ["slippage_bps", 9]]) {
    const input = nodes(output, node => node.type === "Input" && node.props.id === `execution-${key}`)[0];
    assert.ok(input); input.props.onChange({ target: { value: String(value) } }); output = render();
  }
  await nodes(output, node => node.type === "Button" && text(node).includes("Launch Colony"))[0].props.onClick();
  assert.deepEqual(plain(submitted[0].execution), { fee_bps: 12, half_spread_bps: 4, slippage_bps: 9 });
  nodes(output, node => node.type === "Input" && node.props.id === "execution-fee_bps")[0].props.onChange({ target: { value: "" } });
  output = render();
  assert.equal(nodes(output, node => node.type === "Input" && node.props.id === "execution-fee_bps")[0].props.value, "");
  await nodes(output, node => node.type === "Button" && text(node).includes("Launch Colony"))[0].props.onClick();
  assert.equal(submitted.length, 1);
  assert.match(text(render()), /Execution costs must be finite/);
});

test("saved run policy is allowlisted without exposing raw configuration and legacy costs stay unknown", async () => {
  for (const value of [undefined, policy(), { ...policy(), account_currency: "USDC" }]) {
    const responses = [{ data: [{ id: "A", config: { secret: "do-not-copy", runtime: {
      execution_policy: value ? { ...value, secret: "do-not-copy" } : undefined,
    } } }], error: null }, { data: [], error: null }];
    const client = { from() { const result = responses.shift(); return {
      select() { return this; }, order() { return this; }, in() { return this; },
      then(resolve, reject) { return Promise.resolve(result).then(resolve, reject); },
    }; } };
    const database = compile("../src/lib/probes/probes-supabase.ts", {
      "./signal-profile": signalProfiles,
      "./execution": execution, "./transport": transport,
      "@/lib/supabase/client": { createClient: () => client },
    });
    const [run] = await database.fetchColonyRuns();
    assert.deepEqual(plain(run.runtime.execution_policy ?? null), value?.account_currency === "USD" ? policy() : null);
    assert.ok(!JSON.stringify(run).includes("do-not-copy"));
  }
});

test("actual trade rows show precise executed prices and net costs without relabeling legacy trades", () => {
  let index = 0;
  const detailed = ledger();
  detailed.entry.reference_price = .000025;
  detailed.entry.fill_price = .000025;
  detailed.entry.quantity = detailed.exit.quantity = 4_000_000;
  detailed.exit.reference_price = detailed.exit.fill_price = .0000275;
  const rows = [{ id: "new", pair: "BONK/USDC", opened_at: "2024-01-01T00:00:00Z",
    entry_price: .000025, exit_price: null, pnl: 999, exit_reason: "SIGNAL_EXIT", execution: detailed },
    { id: "new-open", pair: "SOL/USDC", opened_at: "2024-01-01T00:00:00Z", entry_price: 100,
      exit_price: 333, pnl: 888, exit_reason: "FALSE_LEGACY_CLOSE", execution: { ...ledger(), exit: null } },
    { id: "legacy", pair: "SOL/USDC", opened_at: "2024-01-01T00:00:00Z", entry_price: 100,
      exit_price: null, pnl: null, exit_reason: null, execution: null }];
  const states = [rows, false, false, 0];
  const modules = { ...ui, react: { useState: () => [states[index++], () => {}], useEffect() {} },
    "@/lib/probes/probes-supabase": { fetchProbeTrades() { throw new Error("Unneeded fetch"); } },
    "./TradeExecutionDetails": stubs("TradeExecutionDetails"),
    "@/components/ui/table": stubs("Table", "TableBody", "TableCell", "TableHead", "TableHeader", "TableRow"),
  };
  const { TradeLog } = compile("../src/components/probes/TradeLog.tsx", modules);
  const wrapper = TradeLog({ probeId: "p" });
  const rendered = wrapper.type(wrapper.props);
  const rowViews = nodes(rendered, node => node.type === "TableRow" && node.key);
  assert.equal(rowViews.length, 3);
  assert.match(text(rowViews[0]), /USD reference/);
  assert.match(text(rowViews[0]), /0.000025000/);
  assert.match(text(rowViews[0]), /7.90/);
  assert.ok(!text(rowViews[0]).includes("999"));
  assert.match(text(rowViews[0]), /0.000027500/);
  assert.match(text(rowViews[1]), /open/);
  assert.ok(!text(rowViews[1]).includes("333"));
  assert.ok(!text(rowViews[1]).includes("888"));
  assert.ok(!text(rowViews[1]).includes("FALSE_LEGACY_CLOSE"));
  assert.match(text(rowViews[2]), /SOL\/USDC · unit unverified/);
  assert.ok(!text(rowViews[2]).includes("USD reference"));
  assert.ok(!text(rowViews[2]).includes("$"));
});

test("structured cost validation errors use known local fields and never server-provided text", () => {
  const message = transport.formatWorkerValidation({ detail: [{ loc: ["body", "execution", "fee_bps"], msg: "private-payload" },
    { loc: ["body", "execution", "unknown-private-field"], input: "secret" }] });
  assert.match(message, /Execution costs \/ Fee \(bps\)/);
  assert.match(message, /half-spread plus slippage below 10,000/);
  assert.ok(!message.includes("private"));
  assert.ok(!message.includes("secret"));
});

test("return diagnostic explains pre-decision sampling only for a known execution policy and explicit metadata", () => {
  const { ProbeDetail } = compile("../src/components/probes/ProbeDetail.tsx", ui);
  const accounting = { execution_policy: policy(), cash: 107.9, position_value: 0, equity: 107.9, roi: .079, valuation_available: true };
  const probe = { id: "p", state: "TRADING", current_capital: 107.9, initial_capital: 100,
    total_trades: 1, total_pnl: 7.9, winning_trades: 1, fitness_score: 0, generation: 0, max_drawdown: 0,
    born_at: "2024-01-01T00:00:00Z", genome: {}, metrics: { accounting,
      execution_sampling: "pre_decision", terminal_execution_costs_in_returns: false } };
  const render = value => text(ProbeDetail({ probe: value, open: true, onClose() {} }));
  assert.match(render(probe), /Return samples precede decisions; final liquidation costs are included in net P&L and ROI but not this return diagnostic/);
  assert.ok(!render({ ...probe, metrics: { ...probe.metrics, accounting: undefined } }).includes("Return samples precede decisions"));
  assert.ok(!render({ ...probe, metrics: { ...probe.metrics, execution_sampling: undefined } }).includes("Return samples precede decisions"));
});


test("known execution policy rejects contradictory economic identities and malformed zero writeoffs", () => {
  const good = ledger();
  for (const side of ["entry", "exit"]) {
    for (const field of Object.keys(good[side]).filter(key => key !== "kind")) {
      const altered = structuredClone(good);
      altered[side][field] += 1;
      assert.equal(execution.parseTradeExecution(altered), undefined, `${side}.${field}`);
    }
  }
  const writeoff = { kind: "writeoff", reference_price: 0, fill_price: 0, quantity: 1,
    notional: 0, fee: 0, cash_credit: 0, spread_cost: 0, slippage_cost: 0,
    gross_pnl: -100, net_pnl: -101, net_return: -1 };
  for (const field of ["quantity", "gross_pnl", "net_pnl"]) {
    assert.equal(execution.parseTradeExecution({ ...good, exit: { ...writeoff, [field]: writeoff[field] + 1 } }), undefined);
  }
  assert.equal(execution.parseTradeExecution({ ...good, exit: { ...good.exit, notional: 0, cash_credit: 0 } }), undefined);
  const withinFloatNoise = structuredClone(good);
  withinFloatNoise.exit.net_pnl = 7.900000000000006;
  assert.ok(execution.parseTradeExecution(withinFloatNoise));
  const accounting = { execution_policy: policy(), cash: 25, position_value: 75, equity: 101, roi: .01, valuation_available: true };
  assert.equal(execution.parseProbeAccounting(accounting), undefined);
});

test("initial saved policy remains classified before a runtime snapshot while unknown runtime versions do not fall back", async () => {
  for (const [runtime, expected] of [[undefined, true], [{}, true], [{ execution_policy: null }, false], [{ execution_policy: { ...policy(), version: "future" } }, false]]) {
    const responses = [{ data: [{ id: "A", config: { execution_policy: { ...policy(), secret: "do-not-copy" }, runtime } }], error: null }, { data: [], error: null }];
    const client = { from() { const result = responses.shift(); return {
      select() { return this; }, order() { return this; }, in() { return this; },
      then(resolve, reject) { return Promise.resolve(result).then(resolve, reject); },
    }; } };
    const database = compile("../src/lib/probes/probes-supabase.ts", {
      "./signal-profile": signalProfiles,
      "./execution": execution, "./transport": transport,
      "@/lib/supabase/client": { createClient: () => client },
    });
    const [run] = await database.fetchColonyRuns();
    assert.equal(Boolean(run.runtime.execution_policy), expected);
    assert.ok(!JSON.stringify(run).includes("do-not-copy"));
  }
});


test("Python-generated execution records survive cross-language tiny, extreme and near-boundary arithmetic", () => {
  // Generated with the actual worker buy_fill/sell_fill/execution_record implementation.
  const records = [
  {
    "version": "usd-reference-percentage-cost-v1",
    "account_currency": "USD",
    "config": {
      "fee_bps": 12.0,
      "half_spread_bps": 4.0,
      "slippage_bps": 9.0
    },
    "entry": {
      "reference_price": 100.0,
      "fill_price": 100.13000000000001,
      "quantity": 1.0074797290091,
      "notional": 100.87894526568118,
      "fee": 0.12105473431881741,
      "cash_debit": 101.0,
      "spread_cost": 0.040299189160364,
      "slippage_cost": 0.090673175610819
    },
    "exit": {
      "kind": "fill",
      "reference_price": 110.0,
      "fill_price": 109.857,
      "quantity": 1.0074797290091,
      "notional": 110.6787005897527,
      "fee": 0.1328144407077032,
      "cash_credit": 110.54588614904499,
      "spread_cost": 0.0443291080764004,
      "slippage_cost": 0.09974049317190091,
      "gross_pnl": 9.799755324071512,
      "net_pnl": 9.545886149044989,
      "net_return": 0.0945137242479702
    }
  },
  {
    "version": "usd-reference-percentage-cost-v1",
    "account_currency": "USD",
    "config": {
      "fee_bps": 12.0,
      "half_spread_bps": 4.0,
      "slippage_bps": 9.0
    },
    "entry": {
      "reference_price": 1e-308,
      "fill_price": 1.0013e-308,
      "quantity": 9.975046821872277e+27,
      "notional": 9.98801438274071e-281,
      "fee": 1.1985617259288852e-283,
      "cash_debit": 1e-280,
      "spread_cost": 3.9900187287489104e-284,
      "slippage_cost": 8.97754213968505e-284
    },
    "exit": {
      "kind": "fill",
      "reference_price": 1.1e-308,
      "fill_price": 1.09857e-308,
      "quantity": 9.975046821872277e+27,
      "notional": 1.0958287187104226e-280,
      "fee": 1.314994462452507e-283,
      "cash_credit": 1.0945137242479701e-280,
      "spread_cost": 4.389020601623802e-284,
      "slippage_cost": 9.875296353653554e-284,
      "gross_pnl": 9.702728043635153e-282,
      "net_pnl": 9.451372424797015e-282,
      "net_return": 0.09451372424797015
    }
  },
  {
    "version": "usd-reference-percentage-cost-v1",
    "account_currency": "USD",
    "config": {
      "fee_bps": 9999.99999,
      "half_spread_bps": 2.0,
      "slippage_bps": 3.0
    },
    "entry": {
      "reference_price": 1e-12,
      "fill_price": 1.0004999999999998e-12,
      "quantity": 499750125187.4064,
      "notional": 0.50000000025,
      "fee": 0.49999999975000003,
      "cash_debit": 1.0,
      "spread_cost": 9.995002503748127e-05,
      "slippage_cost": 0.0001499250375562219
    },
    "exit": {
      "kind": "fill",
      "reference_price": 1.1e-12,
      "fill_price": 1.09945e-12,
      "quantity": 499750125187.4064,
      "notional": 0.5494502751372939,
      "fee": 0.5494502745878437,
      "cash_credit": 5.494502612570125e-10,
      "spread_cost": 0.0001099450275412294,
      "slippage_cost": 0.00016491754131184408,
      "gross_pnl": 0.04945027488729392,
      "net_pnl": -0.9999999994505497,
      "net_return": -0.9999999994505497
    }
  },
  {
    "version": "usd-reference-percentage-cost-v1",
    "account_currency": "USD",
    "config": {
      "fee_bps": 0.0,
      "half_spread_bps": 5000.0,
      "slippage_bps": 4999.9999
    },
    "entry": {
      "reference_price": 10000000000.0,
      "fill_price": 19999999900.0,
      "quantity": 5.000000025e+297,
      "notional": 1e+308,
      "fee": 0.0,
      "cash_debit": 1e+308,
      "spread_cost": 2.5000000125e+307,
      "slippage_cost": 2.4999999624999993e+307
    },
    "exit": {
      "kind": "fill",
      "reference_price": 50000000000.0,
      "fill_price": 500.0000055588317,
      "quantity": 5.000000025e+297,
      "notional": 2.5000000402941586e+300,
      "fee": 0.0,
      "cash_credit": 2.5000000402941586e+300,
      "spread_cost": 1.2500000062499999e+308,
      "slippage_cost": 1.2499999812499998e+308,
      "gross_pnl": -9.999999749999995e+307,
      "net_pnl": -9.999999749999995e+307,
      "net_return": -0.9999999749999995
    }
  }
];
  for (const record of records) {
    assert.deepEqual(execution.parseTradeExecution(record), record);
    const tampered = structuredClone(record);
    tampered.entry.spread_cost *= 2;
    assert.equal(execution.parseTradeExecution(tampered), undefined);
  }
});
