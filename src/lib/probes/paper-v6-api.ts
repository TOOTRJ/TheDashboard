/** Owner-bound controls and bounded committed history for prospective paper trading. */
import { displayDrawdownPct, taggedFloat64 } from './durable-read-model';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const PHASES = new Set(['idle', 'recovering', 'warming_up', 'waiting_data', 'running', 'stopping', 'stopped', 'risk_halted', 'pending', 'failed']);
const AMOUNT = /^(0|[1-9]\d{0,12})(\.\d{1,18})?$/;
function unavailable(): never { throw new Error('The prospective paper service is unavailable or returned incompatible data.'); }
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return unavailable();
  return value as Record<string, unknown>;
}
function identity(value: unknown): string {
  if (typeof value !== 'string' || !UUID.test(value)) return unavailable();
  return value;
}
function integer(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) return unavailable();
  return value;
}
function text(value: unknown, max = 128): string {
  if (typeof value !== 'string' || value.length === 0 || value.length > max) return unavailable();
  return value;
}
function amount(value: unknown): string {
  if (typeof value !== 'string' || !AMOUNT.test(value)) return unavailable();
  return value;
}
function scope(value: unknown, owner: string, run?: string) {
  const row = object(value);
  if (row.version !== 6 || row.owner_id !== identity(owner) || (run !== undefined && row.run_id !== run)) return unavailable();
  identity(row.run_id);
  return row;
}

export type PaperV6Member = { id: string; name: string; generation: number; fast: number; slow: number;
  cash: string; initialCash: string; equity: string | null; parents: string[] | null; closedTrades: number | null; drawdown: string | null };
export type PaperV6Projection = { reserveCash: string; totalEquity: string | null; asset: string;
  population: number; members: PaperV6Member[]; openPositions: number };
export type PaperV6Status = { owner: string; run: string; phase: string; sequence: number;
  revision: number | null; generation: number; epoch: number; busy: boolean; requiresReconciliation: boolean;
  lastRequest: string | null; recoverySequence: number; projection: PaperV6Projection | null;
  warmup: { observed: number; required: number; historyGap: boolean } | null };
export type PaperV6Assessment = { probe: string; generation: number; status: string;
  eligible: boolean; reason: string; fitness: number | null; roi: number | null; closedTrades: number | null; drawdown: string | null };
export type PaperV6HistoryRow = { sequence: number; kind: string; assessments: PaperV6Assessment[] };
export type PaperV6History = { run: string; through: number; next: number; hasMore: boolean; records: PaperV6HistoryRow[] };

function projection(value: unknown): PaperV6Projection | null {
  if (value === null) return null;
  const row = object(value);
  if (Object.keys(row).length === 0) return null;
  if (!Array.isArray(row.members) || row.members.length > 8 || !Array.isArray(row.positions) || row.positions.length > 512) return unavailable();
  const members = row.members.map(raw => {
    const member = object(raw), fast = integer(member.ema_fast), slow = integer(member.ema_slow);
    if (fast < 1 || fast >= slow || slow > 10000) return unavailable();
    let parents: string[] | null = null;
    if (member.parent_ids !== undefined) {
      if (!Array.isArray(member.parent_ids) || member.parent_ids.length > 5) return unavailable();
      parents = member.parent_ids.map(identity);
      if (new Set(parents).size !== parents.length || parents.includes(String(member.id))) return unavailable();
    }
    return { id: identity(member.id), name: text(member.name), generation: integer(member.generation),
      fast, slow, cash: amount(member.cash), initialCash: amount(member.initial_cash),
      equity: member.equity === null || member.equity === undefined ? null : amount(member.equity), parents,
      closedTrades: member.num_trades === undefined ? null : integer(member.num_trades),
      drawdown: member.max_drawdown === undefined ? null : displayDrawdownPct(member.max_drawdown, 4) };
  });
  if (new Set(members.map(member => member.id)).size !== members.length || integer(row.population) !== 8) return unavailable();
  return { reserveCash: amount(row.reserve_cash), totalEquity: row.total_equity === null ? null : amount(row.total_equity),
    asset: text(row.asset, 32), population: 8, members,
    openPositions: row.positions.filter(raw => { const position = object(raw);
      if (typeof position.closed !== 'boolean') return unavailable(); return !position.closed; }).length };
}

export function parsePaperV6Status(value: unknown, owner: string, run?: string): PaperV6Status {
  const row = scope(value, owner, run);
  if (!PHASES.has(String(row.phase)) || typeof row.busy !== 'boolean' || typeof row.requires_reconciliation !== 'boolean') return unavailable();
  const warmup = row.warmup === null || row.warmup === undefined ? null : object(row.warmup);
  if (warmup?.history_gap !== undefined && typeof warmup.history_gap !== 'boolean') return unavailable();
  return { owner, run: identity(row.run_id), phase: String(row.phase), sequence: integer(row.sequence),
    revision: row.revision === null ? null : integer(row.revision), generation: integer(row.generation), epoch: integer(row.epoch),
    busy: row.busy, requiresReconciliation: row.requires_reconciliation,
    lastRequest: row.last_request_id === null ? null : identity(row.last_request_id),
    recoverySequence: integer(row.recovery_sequence ?? row.sequence), projection: projection(row.projection),
    warmup: warmup === null ? null : { observed: integer(warmup.observed_minutes), required: integer(warmup.required_minutes), historyGap: warmup.history_gap === true } };
}

function score(value: unknown): number | null {
  return value === null ? null : taggedFloat64({ float64: value });
}
export function parsePaperV6History(value: unknown, owner: string, run: string, after: number, limit: number): PaperV6History {
  const row = scope(value, owner, run), through = integer(row.through_sequence), next = integer(row.next_sequence);
  if (!Array.isArray(row.records) || row.records.length > limit || typeof row.has_more !== 'boolean' || through < after) return unavailable();
  const records = row.records.map((raw, index) => {
    const entry = object(raw), sequence = integer(entry.sequence), data = object(entry.data);
    if (sequence !== after + index + 1 || sequence > through) return unavailable();
    const rawAssessments = data.assessments ?? [];
    if (!Array.isArray(rawAssessments) || rawAssessments.length > 8) return unavailable();
    const assessments = rawAssessments.map(rawAssessment => {
      const assessment = object(rawAssessment);
      if (assessment.owner_id !== owner || assessment.run_id !== run || typeof assessment.selection_eligible !== 'boolean'
        || !['completed', 'aborted'].includes(String(assessment.status))) return unavailable();
      const fitness = score(assessment.fitness_float64), roi = score(assessment.roi_float64);
      if (assessment.status === 'aborted' && (fitness !== null || roi !== null || assessment.selection_eligible)) return unavailable();
      const metrics = assessment.metrics === undefined ? null : object(assessment.metrics);
      return { probe: identity(assessment.probe_id), generation: integer(assessment.generation),
        status: String(assessment.status), eligible: assessment.selection_eligible, reason: text(assessment.reason), fitness, roi,
        closedTrades: metrics === null ? null : integer(metrics.closed_trade_count),
        drawdown: metrics === null ? null : displayDrawdownPct(metrics.max_drawdown, 4) };
    });
    return { sequence, kind: text(entry.kind, 64), assessments };
  });
  const last = records.at(-1)?.sequence ?? after;
  if (next !== last || row.has_more !== (last < through) || (row.has_more && records.length === 0)) return unavailable();
  return { run, through, next, hasMore: row.has_more, records };
}

export class PaperV6ClosedError extends Error {
  constructor() { super('The prospective paper worker is closed by configuration.'); }
}
async function request(url: string, token: string, args: unknown, signal?: AbortSignal): Promise<unknown> {
  const controller = new AbortController(), abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  const timer = setTimeout(abort, 8000);
  try {
    const response = await fetch(url, { method: args === undefined ? 'GET' : 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: args === undefined ? undefined : JSON.stringify(args), signal: controller.signal,
      redirect: 'error', cache: 'no-store', credentials: 'omit' });
    if (!response.body) return unavailable();
    const reader = response.body.getReader(), chunks: Uint8Array[] = [];
    let length = 0;
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        length += chunk.value.byteLength;
        if (length > 262144) return unavailable();
        chunks.push(chunk.value);
      }
    } finally { await reader.cancel().catch(() => {}); }
    const bytes = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    if (!response.ok) {
      if (response.status === 503 && response.headers.get('content-type')?.split(';')[0] === 'application/json'
        && value && Object.keys(value).length === 1 && value.detail === 'Paper service is closed') throw new PaperV6ClosedError();
      return unavailable();
    }
    return value;
  } catch (error) { if (error instanceof PaperV6ClosedError) throw error; return unavailable(); }
  finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); controller.abort(); }
}

export function paperV6API(token: string, workerOrigin: string) {
  const origin = new URL(workerOrigin);
  if (origin.protocol !== 'https:' || origin.origin !== workerOrigin || origin.username || origin.password) return unavailable();
  return {
    status: (signal?: AbortSignal) => request(`${workerOrigin}/v6/status`, token, undefined, signal),
    command: (action: 'start' | 'stop', requestId: string, signal?: AbortSignal) => {
      if (!['start', 'stop'].includes(action)) return unavailable();
      return request(`${workerOrigin}/v6/${action}`, token, { request_id: identity(requestId) }, signal);
    },
    history: (after: number, limit = 25, signal?: AbortSignal) => {
      integer(after); integer(limit);
      if (limit < 1 || limit > 100) return unavailable();
      return request(`${workerOrigin}/v6/history?after_sequence=${after}&limit=${limit}`, token, undefined, signal);
    },
  };
}
export type PaperV6API = ReturnType<typeof paperV6API>;
