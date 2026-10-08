/** Fixed-project, user-authenticated reads and original-ID paper controls. */
import { collectProjectionPages, displayUSD, probeBalances, taggedFloat64, HISTORY_READ_TIMEOUT_MS, type ProjectionKind } from './durable-read-model';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const READS = new Set(['discover', 'page', 'events', 'archive_run']);
function refuse(): never { throw new Error('Paper service data is unavailable or incompatible.'); }
export function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return refuse();
  return value as Record<string, unknown>;
}
export function identity(value: unknown): string {
  if (typeof value !== 'string' || !UUID.test(value)) return refuse(); return value;
}
function integer(value: unknown, min = 0): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min) return refuse(); return value;
}
async function boundedRequest(url: string, token: string, key: string | null,
  args: unknown, signal?: AbortSignal, schema?: string): Promise<unknown> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  const timer = setTimeout(abort, 5000);
  try {
    const response = await fetch(url, { method: args === undefined ? 'GET' : 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json',
        ...(key ? { apikey: key } : {}), ...(schema ? { 'Accept-Profile': schema, 'Content-Profile': schema } : {}) },
      body: args === undefined ? undefined : JSON.stringify(args), signal: controller.signal,
      cache: 'no-store', redirect: 'error', credentials: 'omit' });
    if (!response.ok || !response.body) return refuse();
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = []; let total = 0;
    try {
      while (true) {
        const chunk = await reader.read(); if (chunk.done) break;
        total += chunk.value.byteLength; if (total > 65536) return refuse(); chunks.push(chunk.value);
      }
    } finally { await reader.cancel().catch(() => {}); }
    const bytes = new Uint8Array(total); let at = 0;
    for (const chunk of chunks) { bytes.set(chunk, at); at += chunk.byteLength; }
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch { return refuse(); }
  finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); controller.abort(); }
}
export function paperAPI(token: string, publicKey: string, workerOrigin: string) {
  const parsed = new URL(workerOrigin);
  if (parsed.protocol !== 'https:' || parsed.origin !== workerOrigin || parsed.username || parsed.password) return refuse();
  return {
    read: (name: string, args: unknown, signal?: AbortSignal) => {
      if (!READS.has(name)) return refuse();
      return boundedRequest(`https://fxpxsciltakyypunglzr.supabase.co/rest/v1/rpc/${name}`,
        token, publicKey, args, signal, 'vn_read');
    },
    worker: (name: string, args?: unknown, signal?: AbortSignal) => {
      if (!['status', 'controls', 'start', 'stop', 'settle'].includes(name)) return refuse();
      return boundedRequest(`${workerOrigin}/v5/${name}`, token, null, args, signal);
    },
  };
}
export type PaperAPI = ReturnType<typeof paperAPI>;
async function readDeadline<T>(signal: AbortSignal, operation: (s: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) abort();
  const timer = setTimeout(abort, HISTORY_READ_TIMEOUT_MS);
  let cancelled!: () => void;
  const interruption = new Promise<never>((_, reject) => {
    cancelled = () => reject(new Error('Paper history request interrupted.'));
    controller.signal.addEventListener('abort', cancelled, { once: true });
  });
  try {
    if (controller.signal.aborted) return refuse();
    return await Promise.race([operation(controller.signal), interruption]);
  } finally {
    clearTimeout(timer); signal.removeEventListener('abort', abort);
    controller.signal.removeEventListener('abort', cancelled); controller.abort();
  }
}
export type RunDirectoryRow = { runId: string; revision: number; data: Record<string, unknown>; archive: Record<string, unknown> | null };
export function discoverRuns(api: PaperAPI, owner: string, signal: AbortSignal) {
  identity(owner); return readDeadline(signal, s => directoryPages(api, owner, s));
}
async function directoryPages(api: PaperAPI, owner: string, signal: AbortSignal) {
  const rows: RunDirectoryRow[] = []; let after: string | null = null, through: string | null = null;
  for (let i = 0; i < 500; i++) {
    if (signal.aborted) return refuse();
    const page = record(await api.read('discover', { after_id: after, through_id: through, max_rows: 100, max_bytes: 65536 }, signal));
    if (page.version !== 1 || page.owner_id !== owner || !Array.isArray(page.records) || page.records.length > 100 || typeof page.has_more !== 'boolean') return refuse();
    const cutoff = page.through_id === null ? null : identity(page.through_id);
    if (i > 0 && cutoff !== through) return refuse(); through = cutoff;
    for (const raw of page.records) {
      const row = record(raw), runId = identity(row.run_id), data = record(row.data);
      if (through === null || runId > through || (after !== null && runId <= after) || data.id !== runId || data.account_currency !== 'USD' || data.durability_version !== 5) return refuse();
      const archive = row.archive_receipt === null ? null : record(row.archive_receipt);
      if (archive && (archive.owner_id !== owner || archive.run_id !== runId || archive.archived !== true)) return refuse();
      rows.push({ runId, revision: integer(row.revision, 1), data, archive }); after = runId;
      if (rows.length > 50000) return refuse();
    }
    if (page.next_id !== (page.records.length ? after : null) || (page.has_more && page.records.length === 0)) return refuse();
    if (!page.has_more) return rows;
  }
  return refuse();
}
export function runSnapshot(api: PaperAPI, owner: string, run: string, signal: AbortSignal) {
  identity(owner); identity(run); return readDeadline(signal, s => projectionSnapshot(api, owner, run, s));
}
async function projectionSnapshot(api: PaperAPI, owner: string, run: string, signal: AbortSignal) {
  const rpc = (args: unknown, s: AbortSignal) => api.read('page', args, s);
  const runs = await collectProjectionPages(rpc, owner, run, 'runs', signal);
  const kinds: ProjectionKind[] = ['probes', 'trades', 'samples', 'evaluations'];
  const others = await Promise.all(kinds.map(kind => collectProjectionPages(rpc, owner, run, kind, signal, runs.throughRevision)));
  for (const row of runs.records) {
    if (row.data.id !== run || row.data.durability_version !== 5) return refuse();
    displayUSD(row.data.initial_cash); displayUSD(row.data.reserve);
    if (row.data.reference_equity !== null) displayUSD(row.data.reference_equity);
  }
  for (const row of others[0].records) probeBalances(row.data);
  for (const row of others[1].records) tradeDetails(row.data);
  for (const row of others[3].records) evaluationDetails(row.data);
  return { revision: runs.throughRevision, runs: runs.records, probes: others[0].records,
    trades: others[1].records, samples: others[2].records, evaluations: others[3].records };
}
/** Curated display adapters never convert monetary amounts to floating point. */
export function tradeDetails(value: unknown) {
  const row = record(value), entry = record(row.entry);
  const exit = row.exit === null ? null : record(row.exit);
  // The v5 ledger retains 18-place quantities; keep the exact string for display.
  if (row.account_currency !== 'USD' || typeof row.closed !== 'boolean' || row.closed !== (exit !== null)
    || typeof row.asset !== 'string' || typeof row.quantity !== 'string'
    || !/^(0|[1-9]\d{0,12})(\.\d{1,18})?$/.test(row.quantity)) return refuse();
  return { id: identity(row.id), account: identity(row.account_id), asset: row.asset, quantity: row.quantity,
    closed: row.closed, opened: String(row.opened_at), closedAt: row.closed_at === null ? null : String(row.closed_at),
    entryPrice: displayUSD(entry.fill_price, 6), entryNotional: displayUSD(entry.notional), entryFee: displayUSD(entry.fee, 6),
    exitPrice: exit === null ? null : displayUSD(exit.fill_price, 6),
    exitFee: exit === null ? null : displayUSD(exit.fee, 6),
    netPnl: exit === null ? null : displayUSD(exit.net_pnl), exitReason: row.exit_reason === null ? null : String(row.exit_reason) };
}
export function evaluationDetails(value: unknown) {
  const row = record(value), cohort = record(row.cohort);
  if (row.account_currency !== 'USD' || !['completed', 'aborted'].includes(String(cohort.phase))
    || !Array.isArray(cohort.evaluations) || cohort.evaluations.length > 16
    || typeof cohort.iteration_id !== 'string' || !Array.isArray(cohort.member_ids)) return refuse();
  const seen = new Set<string>();
  const members = cohort.member_ids;
  const results = cohort.evaluations.map(raw => {
    const result = record(raw), member = identity(result.probe_id);
    if (seen.has(member) || !members.includes(member) || result.iteration_id !== cohort.iteration_id
      || !['completed', 'aborted'].includes(String(result.status))) return refuse();
    seen.add(member);
    return { member, status: String(result.status), reason: String(result.reason), trades: integer(result.num_trades),
      fitness: result.fitness === null ? null : taggedFloat64(result.fitness) };
  });
  return { iteration: cohort.iteration_id, phase: String(cohort.phase), results };
}
export type DurableEvent = { sequence: number; revision: number; commandId: string; eventId: string; event: Record<string, unknown> };
/** Full bounded replay before publication. Reconnects repeat the same identities. */
export function eventSnapshot(api: PaperAPI, owner: string, run: string, signal: AbortSignal) {
  identity(owner); identity(run); return readDeadline(signal, s => eventPages(api, owner, run, s));
}
async function eventPages(api: PaperAPI, owner: string, run: string, signal: AbortSignal) {
  const events: DurableEvent[] = []; const identities = new Set<string>(); let after = 0, through: number | null = null;
  for (let i = 0; i < 500; i++) {
    if (signal.aborted) return refuse();
    const page = record(await api.read('events', { run, after_sequence: after, through_sequence: through, max_rows: 100, max_bytes: 65536 }, signal));
    if (page.version !== 1 || page.owner_id !== owner || page.run_id !== run || !Array.isArray(page.records) || page.records.length > 100 || typeof page.has_more !== 'boolean') return refuse();
    const cutoff = integer(page.through_sequence); if (through !== null && cutoff !== through) return refuse(); through = cutoff;
    for (const raw of page.records) {
      const row = record(raw), data = record(row.data), seq = integer(row.sequence, 1), command = identity(row.command_id), index = integer(data.event_index);
      const id = `${run}:${command}:${index}`;
      if (index > 1024 || seq !== after + 1 || seq > cutoff || data.event_id !== id || identities.has(id)) return refuse();
      identities.add(id); events.push({ sequence: seq, revision: integer(row.revision, 1), commandId: command, eventId: id, event: record(data.event) }); after = seq;
      if (events.length > 50000) return refuse();
    }
    if (page.next_sequence !== after || (page.has_more && page.records.length === 0)) return refuse();
    if (!page.has_more) { if (after !== through) return refuse(); return events; }
  }
  return refuse();
}
