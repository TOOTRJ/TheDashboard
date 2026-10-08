"use client";
import * as React from 'react';
import { paperAPI, discoverRuns, runSnapshot, eventSnapshot, record, identity, tradeDetails, evaluationDetails,
  type PaperAPI, type RunDirectoryRow } from '@/lib/probes/paper-api';
import { displayUSD, latestEntities, probeBalances } from '@/lib/probes/durable-read-model';
import { fetchColonyRuns } from '@/lib/probes/probes-supabase';
import type { ColonyRun } from '@/lib/probes/types';

export function PaperDashboard({ owner, token, apiOverride, legacyReader = fetchColonyRuns }:
  { owner: string; token: string; apiOverride?: PaperAPI; legacyReader?: typeof fetchColonyRuns }) {
  const [runs, setRuns] = React.useState<RunDirectoryRow[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [snapshot, setSnapshot] = React.useState<Awaited<ReturnType<typeof runSnapshot>> | null>(null);
  const [eventCount, setEventCount] = React.useState<number | null>(null);
  const [legacy, setLegacy] = React.useState<ColonyRun[]>([]);
  const [status, setStatus] = React.useState<Record<string, unknown> | null>(null);
  const [controls, setControls] = React.useState<{ start: string; stop: string } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [workerError, setWorkerError] = React.useState<string | null>(null);
  const [historyError, setHistoryError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState<string | null>(null);
  const [refresh, setRefresh] = React.useState(0);
  const archive = React.useRef<{ run: string; revision: number; request: string } | null>(null);
  const operation = React.useRef<string | null>(null);
  const credentials = React.useMemo(() => ({ active: true, owner, token }), [owner, token]);
  React.useLayoutEffect(() => { credentials.active = true; return () => { credentials.active = false; }; }, [credentials]);
  const api = React.useMemo(() => {
    try { return apiOverride ?? paperAPI(token, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '',
      process.env.NEXT_PUBLIC_VN_API_URL || ''); }
    catch { return null; }
  }, [token, apiOverride]);
  React.useEffect(() => {
    if (!api) { setControls(null); setStatus(null); setWorkerError('The paper worker endpoint is not configured.'); return; }
    const client = api;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const current = () => !controller.signal.aborted;
    async function worker() {
      try {
        const [rawStatus, rawControls] = await Promise.all([client.worker('status', undefined, controller.signal),
          client.worker('controls', undefined, controller.signal)]);
        const s = record(rawStatus), c = record(rawControls);
        if (s.owner_id !== owner || c.owner_id !== owner || s.version !== 1 || c.version !== 1 || s.run_id !== c.run_id) throw Error('Incompatible worker identity.');
        identity(c.run_id);
        const ids = { start: identity(c.start_id), stop: identity(c.stop_id) };
        if (current()) { setStatus(s); setControls(ids); setWorkerError(null); }
      } catch { if (current()) { setStatus(null); setControls(null); setWorkerError('Unable to verify the paper worker. Committed history is still available; controls require verified worker status.'); } }
    }
    async function poll() {
      await worker();
      if (current()) timer = setTimeout(() => void poll(), 10000);
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [api, owner, refresh]);
  React.useEffect(() => {
    if (!api) return;
    const client = api;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const current = () => !controller.signal.aborted;
    async function history() {
      try {
        const [directory, old] = await Promise.all([discoverRuns(client, owner, controller.signal), legacyReader(owner, controller.signal)]);
        if (current()) { setRuns(directory); setLegacy(old); }
        const run = selected ?? (directory.find(r => !r.archive)?.runId || null);
        if (!run) { if (current()) setHistoryError(null); return; }
        const [data, events] = await Promise.all([runSnapshot(client, owner, run, controller.signal), eventSnapshot(client, owner, run, controller.signal)]);
        if (current()) { setSelected(run); setSnapshot(data); setEventCount(events.length); setHistoryError(null); }
      } catch { if (current()) setHistoryError('Unable to refresh committed history. The last complete snapshot remains shown; refresh to retry reads.'); }
    }
    async function poll() {
      await history();
      if (current()) timer = setTimeout(() => void poll(), 10000);
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [api, owner, selected, refresh, legacyReader]);
  React.useEffect(() => { setPending(null); archive.current = null; setSnapshot(null); setEventCount(null); setRuns([]); setLegacy([]); }, [owner]);
  async function command(action: 'start' | 'stop' | 'settle') {
    if (!api || !controls || operation.current) return;
    operation.current = action;
    const originalCredentials = credentials;
    setPending(action); setError(null);
    try {
      const result = record(await api.worker(action, { request_id: action === 'stop' ? controls.stop : controls.start }));
      if (!originalCredentials.active) return;
      if (result.owner_id !== owner || result.run_id !== status?.run_id) throw Error();
      setStatus(result); setPending(null); operation.current = null; setRefresh(n => n + 1);
    } catch { if (originalCredentials.active) setError('Control acknowledgment is uncertain. Inspect status before settlement; no new run or control ID has been generated.'); }
  }
  async function archiveRun() {
    if (!api || !selected || !snapshot || operation.current) return;
    if (archive.current && archive.current.run !== selected) return;
    archive.current ??= { run: selected, revision: snapshot.revision, request: crypto.randomUUID() };
    const original = archive.current;
    operation.current = 'archive';
    const originalCredentials = credentials;
    setPending('archive');
    try {
      const receipt = record(await api.read('archive_run', { run: original.run, expected_revision: original.revision, request_id: original.request }));
      if (!originalCredentials.active) return;
      if (receipt.owner_id !== owner || receipt.run_id !== original.run || receipt.request_id !== original.request || receipt.revision !== original.revision || receipt.archived !== true) throw Error();
      archive.current = null; setPending(null); operation.current = null; setRefresh(n => n + 1);
    } catch { if (originalCredentials.active) setError('Archive outcome is uncertain. Refresh to inspect the original receipt; holdings and history remain retained.'); }
  }
  const run = snapshot?.runs.at(-1)?.data;
  const members = snapshot ? latestEntities(snapshot.probes).map(row => ({ row, balance: probeBalances(row.data) })) : [];
  const trades = snapshot ? latestEntities(snapshot.trades).map(row => tradeDetails(row.data)) : [];
  const evaluations = snapshot ? snapshot.evaluations.map(row => evaluationDetails(row.data)) : [];
  return <div className="space-y-6">
    <h1 className="text-2xl font-semibold">Evolutionary paper pilot</h1>
    <p className="text-sm text-muted-foreground">Two EMA genes · eight candidates · SOL/USD reference · one evaluation window. Costs are an uncalibrated scenario. Paper balances are research records.</p>
    <div className="rounded-lg border p-4 space-y-3">
      <p>Worker: {String(status?.phase ?? 'unverified')}. Stop requested: {status?.stop_requested === true ? 'yes' : 'no'}.</p>
      {status?.requires_reconciliation === true && <p role="status">The worker requires reconciliation. Committed history may precede the failure; a new worker cannot resume this run.</p>}
      <div className="flex flex-wrap gap-3">
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!controls || !!pending || status?.phase !== 'fresh'} onClick={() => void command('start')}>Start configured pilot</button>
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!controls || !!pending} onClick={() => void command('stop')}>Stop and retain holdings</button>
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!controls || !['pending', 'drained'].includes(String(status?.phase)) || status?.busy === true || (pending !== null && pending !== 'start' && pending !== 'settle')} onClick={() => { operation.current = null; setPending(null); void command('settle'); }}>Settle original operation</button>
        <button className="rounded border px-3 py-2" onClick={() => { operation.current = null; setPending(null); setRefresh(n => n + 1); }}>Refresh status and history</button>
      </div>
      <p className="text-sm">Stopping preserves positions and cash. A restart requires reconciliation; automatic resume is unavailable.</p>
      {pending && <p role="status">Original {pending} request retained; inspect status before continuing.</p>}
      {error && <p role="alert" className="text-red-400">{error}</p>}
      {workerError && <p role="alert" className="text-red-400">{workerError}</p>}
      {historyError && <p role="alert" className="text-red-400">{historyError}</p>}
    </div>
    <label className="block">Run history
      <select className="ml-3 rounded border bg-background p-2" value={selected ?? ''} onChange={e => { setSnapshot(null); setSelected(e.target.value || null); }}>
        <option value="">Select a run</option>
        {runs.map(r => <option key={r.runId} value={r.runId}>{r.runId.slice(0, 8)} · {String(r.data.status)}{r.archive ? ' · archived' : ''}</option>)}
      </select>
    </label>
    {run && <div className="rounded-lg border p-4 space-y-2">
      <p>Committed revision {snapshot?.revision} · {String(run.status)} · generation {String(run.generation ?? 'not seeded')}</p>
      <p>Initial USD ${displayUSD(run.initial_cash)} · reserve ${displayUSD(run.reserve)} · reference equity {run.reference_equity === null ? 'unavailable' : `$${displayUSD(run.reference_equity)}`}</p>
      <p>Retained open positions: {String(run.open_position_count)}. Reconciliation: {run.requires_reconciliation === true ? 'required' : 'not flagged'}.</p>
      <p className="text-sm">Committed at {String(run.committed_at)}. Source at {String(run.source_at ?? 'unavailable')}. These are committed observations, not a current market mark.</p>
      <p>{eventCount ?? 'Unverified'} durable events · {snapshot?.trades.length} trade versions · {snapshot?.evaluations.length} evaluations.</p>
      <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={run.status !== 'stopped' || !!pending} onClick={() => void archiveRun()}>Archive stopped run, retain history</button>
    </div>}
    {members.length > 0 && <div className="overflow-auto"><table className="w-full text-sm"><caption className="text-left mb-2">Committed candidate balances in USD</caption><thead><tr><th className="text-left">Candidate</th><th>Account cash</th><th>Reference equity</th><th>Terminal capital</th><th>State</th></tr></thead><tbody>
      {members.map(({ row, balance: b }) => <tr key={b.id} className="border-t"><td className="py-2">{String(row.data.name)}</td><td className="text-center">${displayUSD(b.economicCash)}</td><td className="text-center">{b.equity === null ? 'Unavailable' : `$${displayUSD(b.equity)}`}</td><td className="text-center">{b.terminalCash === null ? 'Unavailable' : `$${displayUSD(b.terminalCash)}`}</td><td className="text-center">{b.retired ? 'Retired' : 'Active'}</td></tr>)}
    </tbody></table></div>}
    {snapshot && <details className="rounded-lg border p-4"><summary>Trade details ({trades.length} positions)</summary>
      <p className="my-2 text-sm text-muted-foreground">Scenario fills and fees in USD. Open positions have no realized exit P&amp;L.</p>
      {trades.map(t => <div key={t.id} className="border-t py-3 text-sm">
        <p>{t.asset} · candidate {t.account.slice(0, 8)} · {t.closed ? 'Closed' : 'Open, retained'} · quantity {t.quantity}</p>
        <p>Entry ${t.entryPrice} · notional ${t.entryNotional} · entry fee ${t.entryFee}. Opened {t.opened}.</p>
        <p>{t.netPnl === null ? 'Realized P&L unavailable while open.' : `Exit $${t.exitPrice} · exit fee $${t.exitFee} · realized scenario P&L $${t.netPnl} · ${t.exitReason}. Closed ${t.closedAt}.`}</p>
      </div>)}
    </details>}
    {snapshot && <details className="rounded-lg border p-4"><summary>Evaluation details ({evaluations.length} windows)</summary>
      <p className="my-2 text-sm text-muted-foreground">Fitness is a research score from completed common windows. Interrupted windows stay unscored.</p>
      {evaluations.map(e => <div key={e.iteration} className="border-t py-3 text-sm"><p>{e.iteration} · {e.phase}</p>
        {e.results.map(r => <p key={r.member}>{r.member.slice(0, 8)} · {r.status} · fitness {r.fitness === null ? 'unavailable' : r.fitness.toFixed(6)} · {r.trades} trades · {r.reason}</p>)}
      </div>)}
    </details>}
    <details className="rounded-lg border p-4"><summary>Legacy history ({legacy.length} runs)</summary>
      <p className="my-2 text-sm text-muted-foreground">Earlier records retain their original policy and precision. They have no v5 control or resume path.</p>
      {legacy.map(r => <details key={r.run_id} className="border-t py-2 text-sm"><summary>{r.run_id.slice(0, 8)} · {r.mode} · {r.status ?? 'unknown'} · {r.strategy ?? 'unknown strategy'}</summary>
        <p>Started {r.started_at}. Ended {r.ended_at ?? 'not recorded'}. {r.probe_count} recorded candidates.</p>
        <p>Original best fitness {r.best_fitness}. History source {r.history_source ?? 'legacy'}.</p>
        <p>Open positions: {r.runtime?.open_positions ?? 'not recorded'}. Reconciliation: {r.runtime?.requires_reconciliation === undefined ? 'not recorded' : r.runtime.requires_reconciliation ? 'required' : 'not flagged'}.</p>
        <p>Signal policy {r.runtime?.signal_policy?.version ?? 'not recorded'} · execution policy {r.runtime?.execution_policy?.version ?? 'not recorded'}. Legacy scores and balances are not comparable to the v5 USD pilot.</p>
      </details>)}
    </details>
  </div>;
}
