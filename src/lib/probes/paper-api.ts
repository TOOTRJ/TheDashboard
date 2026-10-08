/** Fixed-project, user-authenticated reads and original-ID paper controls. */
import { collectProjectionPages, displayUSD, displayDrawdownPct, probeBalances, taggedFloat64, HISTORY_READ_TIMEOUT_MS, type ProjectionKind } from './durable-read-model';
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
export class PaperWorkerClosedError extends Error {
  constructor() { super('The paper endpoint reports that its service is closed.'); }
}
async function boundedRequest(url: string, token: string, key: string | null,
  args: unknown, signal?: AbortSignal, schema?: string, closedRead = false): Promise<unknown> {
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
    if (!response.body || (!response.ok && !(closedRead && response.status === 503))) return refuse();
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
    const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    if (!response.ok) {
      if (response.headers.get('content-type')?.split(';')[0] === 'application/json'
        && value && Object.keys(value).length === 1 && value.detail === 'Paper service is closed') throw new PaperWorkerClosedError();
      return refuse();
    }
    return value;
  } catch (error) { if (error instanceof PaperWorkerClosedError) throw error; return refuse(); }
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
      return boundedRequest(`${workerOrigin}/v5/${name}`, token, null, args, signal, undefined,
        (name === 'status' || name === 'controls') && args === undefined);
    },
  };
}
export type PaperAPI = ReturnType<typeof paperAPI>;
export function workerStatus(value: unknown, owner: string, run?: string) {
  const s = record(value);
  if (s.version !== 1 || s.owner_id !== owner || (run !== undefined && s.run_id !== run)
    || !['fresh', 'starting', 'running', 'pending', 'drained', 'failed', 'stopped', 'risk_halted'].includes(String(s.phase))
    || typeof s.busy !== 'boolean' || typeof s.stop_requested !== 'boolean' || typeof s.requires_reconciliation !== 'boolean') return refuse();
  identity(s.run_id);
  identity(s.request_id);
  return s;
}
export function workerControls(value: unknown, owner: string) {
  const c = record(value);
  if (c.version !== 1 || c.owner_id !== owner) return refuse();
  const ids = { run: identity(c.run_id), start: identity(c.start_id), stop: identity(c.stop_id) };
  if (ids.start === ids.stop) return refuse(); return ids;
}
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
    executionDetails(row.data.execution_policy);
  }
  const candidates = others[0].records.map(row => probeDetails(row.data));
  const memberIds = new Set(candidates.map(details => details.balance.id));
  const generations = new Map(candidates.map(details => [details.balance.id, details.generation]));
  const evaluations = others[3].records.map(row => evaluationDetails(row.data));
  const iterations = new Set(evaluations.map(e => e.iteration));
  for (const details of candidates) {
    if (details.lineage?.sources.some(source => !memberIds.has(source.id))
      || (details.lineage?.iteration && !iterations.has(details.lineage.iteration))) return refuse();
  }
  for (const row of others[1].records) tradeDetails(row.data);
  for (const evaluation of evaluations) {
    if (!evaluation.iteration.startsWith(`${run}:`) || evaluation.results.some(result => !memberIds.has(result.member)
      || (generations.get(result.member) !== null && generations.get(result.member) !== evaluation.generation))) return refuse();
  }
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
function textField(value: unknown): string {
  if (typeof value !== 'string' || !value || value.length > 256) return refuse(); return value;
}
function optionalTime(value: unknown): number | null {
  if (value === undefined || value === null) return null;
  const time = typeof value === 'number' ? integer(value) : taggedFloat64(value);
  if (time < 0 || time > 253402300799) return refuse(); return time;
}
export function sourceTime(value: number | null) {
  return value === null ? 'not recorded' : new Date(value * 1000).toISOString().replace('T', ' ').replace('Z', ' UTC');
}
export function displayROI(value: number | null) {
  if (value === null) return 'unavailable';
  const percent = value * 100;
  return Number.isFinite(percent) ? `${percent.toFixed(4)}%` : 'outside percentage display range';
}
/** Optional fields preserve older read records; supplied malformed evidence fails the complete read. */
export function probeDetails(value: unknown) {
  const row = record(value), balance = probeBalances(row);
  const generation = row.generation === undefined ? null : integer(row.generation);
  const genome = row.genome === undefined ? null : record(row.genome);
  let genes: { fast: number; slow: number } | null = null;
  if (genome) {
    const fast = taggedFloat64({ float64: genome.ema_fast }), slow = taggedFloat64({ float64: genome.ema_slow });
    if (!Number.isSafeInteger(fast) || !Number.isSafeInteger(slow) || fast < 1 || fast >= slow || slow > 10000
      || integer(genome.generation) !== generation || !Array.isArray(genome.parent_ids)
      || genome.parent_ids.length > 5 || new Set(genome.parent_ids.map(identity)).size !== genome.parent_ids.length) return refuse();
    genes = { fast, slow };
  }
  let lineage: { version: number; strategy: string; operation: string; iteration: string | null;
    sources: { role: string; id: string }[]; supported: boolean } | null = null;
  if (row.lineage !== undefined && row.lineage !== null) {
    const l = record(row.lineage), version = integer(l.version, 1);
    if (identity(l.child_id) !== balance.id || !Array.isArray(l.sources) || l.sources.length > 5) return refuse();
    const sources = l.sources.map(value => { const s = record(value); integer(s.ordinal);
      const id = identity(s.source_id); if (id === balance.id) return refuse();
      return { role: textField(s.role), id }; });
    lineage = { version, strategy: textField(l.strategy), operation: textField(l.operation),
      iteration: l.source_iteration_id === null ? null : textField(l.source_iteration_id), sources, supported: version === 1 || version === 2 };
    if (lineage.supported && lineage.strategy === 'genetic_algorithm') {
      const roles = l.sources.map(value => { const s = record(value); return `${s.role}:${s.ordinal}`; });
      const expected = version === 2 && lineage.operation === 'restart_clone' ? ['clone_source:0', 'asset_template:0']
        : version === 1 && lineage.operation === 'founder' ? []
        : version === 1 && lineage.operation === 'crossover_mutation' ? ['genetic_parent:0', 'genetic_parent:1']
        : version === 1 && ['clone_mutation', 'no_active_clone', 'fixed_repair_clone'].includes(lineage.operation) ? ['genetic_parent:0'] : null;
      if (!expected || roles.length !== expected.length || roles.some((role, i) => role !== expected[i])) return refuse();
      const parentIds = genome?.parent_ids as string[] | undefined;
      const sourceIds = [...new Set(sources.map(s => s.id))];
      if (version === 1 && sourceIds.length !== sources.length) return refuse();
      if (version === 2 && sourceIds.length !== 1) return refuse();
      if (parentIds && (parentIds.length !== sourceIds.length || parentIds.some(id => !sourceIds.includes(id)))) return refuse();
      if (lineage.operation === 'founder' && (sources.length || lineage.iteration !== null)) return refuse();
    }
  }
  const drawdown = row.max_drawdown === undefined ? null : displayDrawdownPct(row.max_drawdown, 4);
  const peak = row.peak_equity === undefined ? null : displayUSD(row.peak_equity);
  return { balance, generation, genes, lineage, drawdown, peak,
    trades: row.closed_trades === undefined ? null : integer(row.closed_trades) };
}
export function executionDetails(value: unknown) {
  if (value === undefined) return null;
  const policy = record(value);
  const config = policy.config === undefined ? null : record(policy.config);
  if (policy.account_currency !== undefined && policy.account_currency !== 'USD') return refuse();
  const rates = ['fee_bps', 'slippage_bps', 'half_spread_bps'].map(key => {
    if (!config || config[key] === undefined) return null;
    const value = config[key];
    if (typeof value !== 'string' || !/^(0|[1-9]\d{0,3})(\.\d{1,6})?$/.test(value)) return refuse();
    return value;
  });
  return { version: policy.version === undefined ? 'not recorded' : textField(policy.version),
    fee: rates[0], slippage: rates[1], halfSpread: rates[2] };
}
export function evaluationDetails(value: unknown) {
  const row = record(value), cohort = record(row.cohort);
  if (row.account_currency !== 'USD' || !['completed', 'aborted'].includes(String(cohort.phase))
    || !Array.isArray(cohort.evaluations) || cohort.evaluations.length > 16
    || typeof cohort.iteration_id !== 'string' || !/^[0-9a-f-]{36}:\d{1,9}$/.test(cohort.iteration_id)
    || !Array.isArray(cohort.member_ids)) return refuse();
  identity(cohort.iteration_id.split(':')[0]);
  const seen = new Set<string>();
  const members = cohort.member_ids.map(identity);
  if (!members.length || members.length > 16 || new Set(members).size !== members.length
    || cohort.evaluations.length !== members.length) return refuse();
  const policy = cohort.policy === undefined ? null : record(cohort.policy);
  const windowPolicy = policy === null ? null : textField(policy.version);
  const selectionPolicy = row.selection === undefined || row.selection === null ? null : textField(record(row.selection).selection_policy);
  const knownSelection = windowPolicy === 'common-market-window-v1' && row.scoring_policy === 'tagged_worker_evaluation_v1'
    && selectionPolicy === 'completed-window-generational-ga-v1';
  const started = optionalTime(cohort.started_at), ends = optionalTime(cohort.ends_at), completed = optionalTime(cohort.completed_at);
  const horizon = optionalTime(cohort.horizon_seconds);
  if ((started === null) !== (ends === null) || (started !== null && ends !== null && ends <= started)
    || (horizon !== null && horizon <= 0) || (started !== null && ends !== null && horizon !== null && ends - started !== horizon)
    || (completed !== null && started !== null && completed < started)
    || (cohort.phase === 'completed' && completed !== null && ends !== null && completed < ends)) return refuse();
  const results = cohort.evaluations.map(raw => {
    const result = record(raw), member = identity(result.probe_id);
    if (seen.has(member) || !members.includes(member) || result.iteration_id !== cohort.iteration_id
      || !['completed', 'aborted'].includes(String(result.status))) return refuse();
    const fitness = result.fitness === null ? null : taggedFloat64(result.fitness);
    const roi = result.roi === undefined || result.roi === null ? null : taggedFloat64(result.roi);
    if ((result.status === 'aborted' && (fitness !== null || roi !== null))
      || (result.status === 'completed' && fitness === null)
      || (cohort.phase === 'completed' && result.status !== 'completed')
      || (result.cohort_complete !== undefined && result.cohort_complete !== (cohort.phase === 'completed'))
      || (result.window_started_at !== undefined && optionalTime(result.window_started_at) !== started)
      || (result.window_ends_at !== undefined && optionalTime(result.window_ends_at) !== ends)) return refuse();
    const terminated = optionalTime(result.terminated_at);
    if (terminated !== null && ((started !== null && terminated < started) || (completed !== null && terminated > completed))) return refuse();
    seen.add(member);
    return { member, status: String(result.status), reason: textField(result.reason), trades: integer(result.num_trades),
      fitness, roi, terminated, eligible: cohort.phase === 'completed' && knownSelection,
      early: result.status === 'completed' && ends !== null && terminated !== null && terminated < ends };
  });
  if (cohort.member_count !== undefined && cohort.member_count !== members.length) return refuse();
  if (cohort.completed_count !== undefined && cohort.completed_count !== results.filter(r => r.status === 'completed').length) return refuse();
  return { iteration: cohort.iteration_id, generation: Number(cohort.iteration_id.split(':')[1]), phase: String(cohort.phase), results, windowPolicy, started, ends, completed, horizon,
    scoringPolicy: row.scoring_policy === undefined ? null : textField(row.scoring_policy),
    selectionPolicy,
    abortReason: cohort.abort_reason === undefined || cohort.abort_reason === null ? null : textField(cohort.abort_reason) };
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
