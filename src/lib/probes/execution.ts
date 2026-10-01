/** Public, versioned reference-account metadata. Never infer costs for old rows. */
export interface ExecutionConfig { fee_bps: number; half_spread_bps: number; slippage_bps: number }
export interface ExecutionPolicy {
  version: "usd-reference-percentage-cost-v1";
  account_currency: "USD";
  valuation: "reference_mark";
  cost_assumptions: "uncalibrated_scenario";
  config: ExecutionConfig;
}
export interface EntryExecution {
  reference_price: number; fill_price: number; quantity: number; notional: number;
  fee: number; cash_debit: number; spread_cost: number; slippage_cost: number;
}
export interface ExitExecution {
  kind: "fill" | "writeoff"; reference_price: number; fill_price: number; quantity: number;
  notional: number; fee: number; cash_credit: number; spread_cost: number; slippage_cost: number;
  gross_pnl: number; net_pnl: number; net_return: number;
}
export interface TradeExecution {
  version: "usd-reference-percentage-cost-v1"; account_currency: "USD";
  config: ExecutionConfig; entry: EntryExecution; exit: ExitExecution | null;
}
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
export function defaultExecutionConfig(): ExecutionConfig {
  return { fee_bps: 0, half_spread_bps: 0, slippage_bps: 0 };
}
export function parseExecutionConfig(value: unknown): ExecutionConfig | undefined {
  if (!record(value) || Object.keys(value).some(key => !["fee_bps", "half_spread_bps", "slippage_bps"].includes(key))) return undefined;
  const { fee_bps, half_spread_bps, slippage_bps } = value;
  if (!finite(fee_bps) || fee_bps < 0 || fee_bps >= 10000 ||
      !finite(half_spread_bps) || half_spread_bps < 0 || !finite(slippage_bps) || slippage_bps < 0 ||
      half_spread_bps + slippage_bps >= 10000) return undefined;
  return { fee_bps, half_spread_bps, slippage_bps };
}
export function parseExecutionPolicy(value: unknown): ExecutionPolicy | undefined {
  if (!record(value) || value.version !== "usd-reference-percentage-cost-v1" ||
      value.account_currency !== "USD" || value.valuation !== "reference_mark" ||
      value.cost_assumptions !== "uncalibrated_scenario") return undefined;
  const config = parseExecutionConfig(value.config);
  return config ? { version: value.version, account_currency: value.account_currency,
    valuation: value.valuation, cost_assumptions: value.cost_assumptions, config } : undefined;
}
// Cross-language floating point results may differ by a few ULPs. A relative
// bound keeps tiny token values strict; zero never matches a positive amount.
const closeNumber = (actual: number, expected: number): boolean => {
  if (!Number.isFinite(actual) || !Number.isFinite(expected)) return false;
  if (actual === expected) return true;
  if (actual === 0 || expected === 0 || Math.sign(actual) !== Math.sign(expected)) return false;
  const scale = Math.max(Math.abs(actual), Math.abs(expected));
  return Math.abs(actual / scale - expected / scale) <= 1e-10;
};
function scaledPositive(value: number): [number, number] {
  const exponent = Math.min(1023, Math.max(-1022, Math.floor(Math.log2(value))));
  return [value / 2 ** exponent, exponent];
}
/** Compare a product without requiring its intermediate products to fit. */
function matchesProduct(actual: number, ...factors: number[]): boolean {
  if (factors.some(value => !Number.isFinite(value) || value < 0)) return false;
  if (factors.some(value => value === 0)) return actual === 0;
  if (!(actual > 0)) return false;
  let mantissa = 1;
  let exponent = 0;
  for (const factor of factors) {
    const [part, power] = scaledPositive(factor);
    const [normalized, shift] = scaledPositive(mantissa * part);
    mantissa = normalized;
    exponent += power + shift;
  }
  const [actualPart, actualPower] = scaledPositive(actual);
  const difference = exponent - actualPower;
  if (Math.abs(difference) > 64) return false;
  return closeNumber(actualPart, mantissa * 2 ** difference);
}
function entryConsistent(entry: EntryExecution, config: ExecutionConfig): boolean {
  const impact = config.half_spread_bps + config.slippage_bps;
  return closeNumber(entry.cash_debit, entry.notional + entry.fee) &&
    matchesProduct(entry.notional, entry.quantity, entry.fill_price) &&
    matchesProduct(entry.fill_price, entry.reference_price, (10000 + impact) / 10000) &&
    (impact === 0 || entry.fill_price > entry.reference_price) &&
    matchesProduct(entry.fee, entry.notional, config.fee_bps, 1 / 10000) &&
    matchesProduct(entry.spread_cost, entry.quantity, entry.reference_price, config.half_spread_bps, 1 / 10000) &&
    matchesProduct(entry.slippage_cost, entry.quantity, entry.reference_price, config.slippage_bps, 1 / 10000);
}
function exitConsistent(exit: ExitExecution, entry: EntryExecution, config: ExecutionConfig): boolean {
  if (!closeNumber(exit.quantity, entry.quantity) ||
      !closeNumber(exit.gross_pnl, exit.notional - entry.notional) ||
      !closeNumber(exit.net_pnl, exit.cash_credit - entry.cash_debit) ||
      !closeNumber(exit.net_return, (exit.cash_credit - entry.cash_debit) / entry.cash_debit)) return false;
  if (exit.kind === "writeoff") return true; // Explicit zero fields were checked before this call.
  const impact = config.half_spread_bps + config.slippage_bps;
  return exit.notional > 0 && exit.cash_credit > 0 &&
    matchesProduct(exit.notional, exit.quantity, exit.fill_price) &&
    matchesProduct(exit.fill_price, exit.reference_price, (10000 - impact) / 10000) &&
    (impact === 0 || exit.fill_price < exit.reference_price) &&
    matchesProduct(exit.fee, exit.notional, config.fee_bps, 1 / 10000) &&
    matchesProduct(exit.cash_credit, exit.notional, (10000 - config.fee_bps) / 10000) &&
    closeNumber(exit.notional, exit.cash_credit + exit.fee) &&
    matchesProduct(exit.spread_cost, exit.quantity, exit.reference_price, config.half_spread_bps, 1 / 10000) &&
    matchesProduct(exit.slippage_cost, exit.quantity, exit.reference_price, config.slippage_bps, 1 / 10000);
}
export function parseTradeExecution(value: unknown): TradeExecution | undefined {
  if (!record(value) || value.version !== "usd-reference-percentage-cost-v1" || value.account_currency !== "USD") return undefined;
  const config = parseExecutionConfig(value.config);
  const entry = value.entry;
  if (!config || !record(entry)) return undefined;
  const entryFields = ["reference_price", "fill_price", "quantity", "notional", "fee", "cash_debit", "spread_cost", "slippage_cost"] as const;
  if (entryFields.some(key => !finite(entry[key]) || entry[key] < 0) ||
      ["reference_price", "fill_price", "quantity", "notional", "cash_debit"].some(key => (entry[key] as number) <= 0)) return undefined;
  const cleanEntry = Object.fromEntries(entryFields.map(key => [key, entry[key]])) as unknown as EntryExecution;
  if (!entryConsistent(cleanEntry, config)) return undefined;
  let cleanExit: ExitExecution | null = null;
  if (value.exit !== null) {
    const exit = value.exit;
    if (!record(exit) || (exit.kind !== "fill" && exit.kind !== "writeoff")) return undefined;
    const positiveFields = ["reference_price", "fill_price", "quantity", "notional", "fee", "cash_credit", "spread_cost", "slippage_cost"] as const;
    const signedFields = ["gross_pnl", "net_pnl", "net_return"] as const;
    if (positiveFields.some(key => !finite(exit[key]) || exit[key] < 0) ||
        signedFields.some(key => !finite(exit[key])) || (exit.quantity as number) <= 0 ||
        (exit.kind === "fill" && ((exit.reference_price as number) <= 0 || (exit.fill_price as number) <= 0))) return undefined;
    if (exit.kind === "writeoff" && (positiveFields.some(key => key !== "quantity" && exit[key] !== 0) || exit.net_return !== -1)) return undefined;
    cleanExit = { kind: exit.kind, ...Object.fromEntries([...positiveFields, ...signedFields].map(key => [key, exit[key]])) } as unknown as ExitExecution;
  }
  if (cleanExit && !exitConsistent(cleanExit, cleanEntry, config)) return undefined;
  return { version: value.version, account_currency: value.account_currency, config, entry: cleanEntry, exit: cleanExit };
}
export function isFrictionless(config: ExecutionConfig): boolean {
  return config.fee_bps === 0 && config.half_spread_bps === 0 && config.slippage_bps === 0;
}
/** Keep small valid prices/costs visible instead of rendering them as zero. */
export function formatReferenceNumber(value: unknown): string {
  if (!finite(value)) return "Unavailable";
  const magnitude = Math.abs(value);
  if (magnitude > 0 && magnitude < 0.01) return value.toPrecision(5);
  return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export interface ProbeAccounting {
  execution_policy: ExecutionPolicy;
  cash: number;
  position_value: number | null;
  equity: number | null;
  roi: number | null;
  valuation_available: boolean;
}
export function parseProbeAccounting(value: unknown): ProbeAccounting | undefined {
  if (!record(value) || !finite(value.cash) || value.cash < 0 || typeof value.valuation_available !== "boolean") return undefined;
  const execution_policy = parseExecutionPolicy(value.execution_policy);
  if (!execution_policy) return undefined;
  if (!value.valuation_available) return { execution_policy, cash: value.cash, position_value: null, equity: null, roi: null, valuation_available: false };
  if (!finite(value.position_value) || value.position_value < 0 || !finite(value.equity) || value.equity < 0 || !finite(value.roi)) return undefined;
  if (!closeNumber(value.equity, value.cash + value.position_value)) return undefined;
  return { execution_policy, cash: value.cash, position_value: value.position_value,
    equity: value.equity, roi: value.roi, valuation_available: true };
}
