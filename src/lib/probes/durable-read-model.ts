/** Inert DB-03A2D3 reader. No Supabase client, credentials or startup selection.
 * Legacy float records remain in their existing reader; these are USD-reference
 * projections with exact decimal strings and explicitly unavailable metrics.
 */
export type ProjectionKind = "runs" | "probes" | "trades" | "samples" | "evaluations";
export type ProjectionRow = { revision: number; command_id: string; key: string; data: Record<string, unknown> };
export type PageArguments = { run: string; kind: ProjectionKind; through_revision: number | null;
  after_revision: number; after_key: string; max_rows: number; max_bytes: number };
export type PageRPC = (args: PageArguments, signal: AbortSignal) => Promise<unknown>;
/** Whole-snapshot budget; each network request retains its separate 5s limit. */
export const HISTORY_READ_TIMEOUT_MS = 60_000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const KINDS = new Set<ProjectionKind>(["runs", "probes", "trades", "samples", "evaluations"]);
function refuse(): never { throw new Error("Durable history is unavailable or incompatible."); }
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return refuse();
  return value as Record<string, unknown>;
}
function integer(value: unknown, minimum = 1): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) return refuse();
  return value;
}
function uuid(value: unknown): string {
  if (typeof value !== "string" || !UUID.test(value)) return refuse();
  return value;
}
/** Display rounding uses integer arithmetic. It never changes stored amounts. */
export function displayUSD(value: unknown, places = 2): string {
  if (typeof value !== "string" || !/^-?(0|[1-9]\d{0,12})(\.\d{1,36})?$/.test(value)
      || !Number.isInteger(places) || places < 0 || places > 36) return refuse();
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = (negative ? value.slice(1) : value).split(".");
  const scaled = BigInt(whole + fraction.padEnd(36, "0"));
  const divisor = BigInt(10) ** BigInt(36 - places);
  const rounded = (scaled + divisor / BigInt(2)) / divisor; // half away from zero
  const digits = rounded.toString().padStart(places + 1, "0");
  return (negative && rounded !== BigInt(0) ? "-" : "") + (places
    ? digits.slice(0, -places) + "." + digits.slice(-places) : digits);
}
/** Exact rational drawdown, rounded only for display; no float division. */
export function displayDrawdownPct(value: unknown, places = 2): string {
  const ratio = object(value);
  const n = ratio.numerator, d = ratio.denominator;
  if (typeof n !== "string" || typeof d !== "string" || !/^(0|[1-9]\d{0,95})$/.test(n)
      || !/^[1-9]\d{0,95}$/.test(d) || !Number.isInteger(places) || places < 0 || places > 6) return refuse();
  const numerator = BigInt(n), denominator = BigInt(d);
  if (numerator > denominator) return refuse();
  const units = (numerator * BigInt(100) * BigInt(10) ** BigInt(places) * BigInt(2) + denominator) / (denominator * BigInt(2));
  const digits = units.toString().padStart(places + 1, "0");
  return (places ? digits.slice(0, -places) + "." + digits.slice(-places) : digits) + "%";
}
/** Python's tagged float64 is for genes/research scores, never money. */
export function taggedFloat64(value: unknown): number {
  const tag = object(value);
  if (Object.keys(tag).length !== 1 || typeof tag.float64 !== "string") return refuse();
  const match = /^(-?)0x([01])\.([0-9a-f]{1,13})p([+-]\d{1,4})$/.exec(tag.float64);
  if (!match) return refuse();
  const exponent = Number(match[4]);
  if (exponent < -1074 || exponent > 1023) return refuse();
  const mantissa = Number(match[2]) + parseInt(match[3], 16) / 16 ** match[3].length;
  const decoded = (match[1] ? -1 : 1) * mantissa * 2 ** exponent;
  if (!Number.isFinite(decoded)) return refuse();
  return decoded;
}
export function probeBalances(value: unknown) {
  const row = object(value);
  if (row.account_currency !== "USD" || typeof row.retired !== "boolean"
      || !["checkpoint_member", "last_observed_before_replacement"].includes(String(row.metrics_basis))) return refuse();
  const exact = (amount: unknown): string => {
    if (typeof amount !== "string" || amount.startsWith("-")) return refuse();
    displayUSD(amount); return amount;
  };
  const economicCash = exact(row.economic_cash);
  const initialCash = exact(row.initial_cash);
  const terminalCash = row.terminal_cash === null ? null : exact(row.terminal_cash);
  const equity = row.equity === null ? null : exact(row.equity);
  if (row.retired && (BigInt(economicCash.replace(".", "")) !== BigInt(0) || equity !== null
      || terminalCash === null || row.equity_basis !== "terminal_frozen")) return refuse();
  if (!row.retired && (equity === null || !["cash_without_market_mark", "reference_mark"].includes(String(row.equity_basis)))) return refuse();
  return { id: uuid(row.id), currency: "USD" as const, initialCash, economicCash, equity,
    terminalCash, retired: row.retired, metricsBasis: String(row.metrics_basis),
    fitnessAvailability: "evaluation_only" as const };
}
function next(row: { revision: number; key: string }, after: { revision: number; key: string }) {
  return row.revision > after.revision || (row.revision === after.revision && row.key > after.key);
}
/** Publishes only a complete bounded revision snapshot; failure returns no partial history.
 * The injected RPC must use vn_read.page with user-session auth and its own
 * bounded network parser. No owner argument is sent to the database.
 */
export async function collectProjectionPages(rpc: PageRPC, owner: string, run: string,
  kind: ProjectionKind, external?: AbortSignal, throughRevision?: number): Promise<{ throughRevision: number; records: ProjectionRow[] }> {
  uuid(owner); uuid(run);
  if (!KINDS.has(kind)) return refuse();
  let snapshot: number | null = throughRevision === undefined ? null : integer(throughRevision);
  const controller = new AbortController();
  const abort = () => controller.abort();
  external?.addEventListener("abort", abort, { once: true });
  if (external?.aborted) controller.abort();
  const timeout = setTimeout(abort, HISTORY_READ_TIMEOUT_MS);
  let cursor = { revision: 0, key: "" };
  const records: ProjectionRow[] = [];
  try {
    for (let pageIndex = 0; pageIndex < 500; pageIndex++) {
      if (controller.signal.aborted) return refuse();
      const args = { run, kind, through_revision: snapshot, after_revision: cursor.revision,
        after_key: cursor.key, max_rows: 100, max_bytes: 65536 };
      let rejectAbort!: () => void;
      const cancelled = new Promise<never>((_, reject) => {
        rejectAbort = () => reject(new Error("Durable history request interrupted."));
        controller.signal.addEventListener("abort", rejectAbort, { once: true });
      });
      let raw: unknown;
      try { raw = await Promise.race([rpc(args, controller.signal), cancelled]); }
      finally { controller.signal.removeEventListener("abort", rejectAbort); }
      if (controller.signal.aborted) return refuse();
      const page = object(raw);
      if (new TextEncoder().encode(JSON.stringify(page)).length > 65536 || page.version !== 1
          || page.owner_id !== owner || page.run_id !== run || page.kind !== kind
          || typeof page.has_more !== "boolean" || !Array.isArray(page.records) || page.records.length > 100) return refuse();
      const revision = integer(page.through_revision);
      if (snapshot !== null && revision !== snapshot) return refuse();
      snapshot = revision;
      for (const value of page.records) {
        const row = object(value);
        const position = { revision: integer(row.revision), key: row.key as string };
        if (typeof position.key !== "string" || !/^[0-9a-f:-]{1,256}$/.test(position.key)
            || position.revision > snapshot || !next(position, cursor)) return refuse();
        const data = object(row.data);
        if (data.account_currency !== "USD") return refuse();
        records.push({ ...position, command_id: uuid(row.command_id), data });
        cursor = position;
        if (records.length > 50_000) return refuse();
      }
      if (page.records.length === 0) {
        if (page.has_more || page.next_cursor !== null) return refuse();
      } else {
        const claimed = object(page.next_cursor);
        if (claimed.revision !== cursor.revision || claimed.key !== cursor.key) return refuse();
      }
      if (!page.has_more) return { throughRevision: snapshot, records };
    }
    return refuse();
  } finally {
    clearTimeout(timeout); external?.removeEventListener("abort", abort);
    controller.abort();
  }
}
/** Operation versions of a trade share data.id. Samples/evaluations stay history. */
export function latestEntities(rows: ProjectionRow[]): ProjectionRow[] {
  const latest = new Map<string, ProjectionRow>();
  for (const row of rows) {
    const id = uuid(row.data.id);
    const old = latest.get(id);
    if (old && !next(row, old)) return refuse();
    latest.set(id, row);
  }
  return [...latest.values()];
}
