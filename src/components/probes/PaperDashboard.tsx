"use client";
import * as React from 'react';
import { paperAPI, discoverRuns, runSnapshot, eventSnapshot, record, tradeDetails, evaluationDetails,
  probeDetails, executionDetails, sourceTime, displayROI, workerStatus, workerControls, PaperWorkerClosedError,
  type PaperAPI, type RunDirectoryRow } from '@/lib/probes/paper-api';
import { displayUSD, latestEntities } from '@/lib/probes/durable-read-model';
import { fetchColonyRuns } from '@/lib/probes/probes-supabase';
import type { ColonyRun } from '@/lib/probes/types';

type Props = { owner: string; token: string; apiOverride?: PaperAPI; legacyReader?: typeof fetchColonyRuns };
export function PaperDashboard(props: Props) {
  // Account replacement remounts all private history and retained control state before paint.
  return <PaperDashboardSession key={props.owner} {...props} />;
}
export function PaperDashboardSession({ owner, token, apiOverride, legacyReader = fetchColonyRuns }: Props) {
  const [runs, setRuns] = React.useState<RunDirectoryRow[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [snapshot, setSnapshot] = React.useState<Awaited<ReturnType<typeof runSnapshot>> | null>(null);
  const [eventCount, setEventCount] = React.useState<number | null>(null);
  const [legacy, setLegacy] = React.useState<ColonyRun[]>([]);
  const [status, setStatus] = React.useState<Record<string, unknown> | null>(null);
  const [controls, setControls] = React.useState<ReturnType<typeof workerControls> | null>(null);
  const verified = React.useRef<ReturnType<typeof workerControls> | null>(null);
  const [closed, setClosed] = React.useState(false);
  const [follow, setFollow] = React.useState<{ run: string; browse: number } | null>(null);
  const browse = React.useRef(0);
  const controlEpoch = React.useRef(0);
  const intent = React.useRef<{ action: 'start' | 'stop' | 'settle'; run: string; start: string; stop: string; browse: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [workerError, setWorkerError] = React.useState<string | null>(null);
  const [historyError, setHistoryError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState<string | null>(null);
  const [refresh, setRefresh] = React.useState(0);
  const archive = React.useRef<{ run: string; revision: number; request: string } | null>(null);
  const operation = React.useRef<object | null>(null);
  const credentials = React.useMemo(() => ({ active: true, owner, token }), [owner, token]);
  React.useLayoutEffect(() => { credentials.active = true; return () => { credentials.active = false; }; }, [credentials]);
  const api = React.useMemo(() => {
    try { return apiOverride ?? paperAPI(token, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '',
      process.env.NEXT_PUBLIC_VN_API_URL || ''); }
    catch { return null; }
  }, [token, apiOverride]);
  React.useEffect(() => {
    if (!api) { verified.current = null; setControls(null); setStatus(null); setClosed(false); setWorkerError('The paper worker endpoint is not configured.'); return; }
    const client = api;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const current = () => !controller.signal.aborted;
    async function worker() {
      const epoch = controlEpoch.current;
      try {
        const responses = await Promise.allSettled([client.worker('status', undefined, controller.signal),
          client.worker('controls', undefined, controller.signal)]);
        if (responses.every(r => r.status === 'rejected' && r.reason instanceof PaperWorkerClosedError)) {
          if (current() && epoch === controlEpoch.current) { verified.current = null; setStatus(null); setControls(null); setClosed(true); setWorkerError(null); }
          return;
        }
        const [rawStatus, rawControls] = responses;
        if (rawStatus.status !== 'fulfilled' || rawControls.status !== 'fulfilled') throw Error();
        const ids = workerControls(rawControls.value, owner), s = workerStatus(rawStatus.value, owner, ids.run);
        if (s.request_id !== ids.start) throw Error();
        if (current() && epoch === controlEpoch.current) {
          verified.current = ids; setStatus(s); setControls(ids); setClosed(false); setWorkerError(null);
          const original = intent.current;
          if (!operation.current && original && original.run === ids.run && original.start === ids.start && original.stop === ids.stop
            && ((original.action !== 'stop' && ['running', 'stopped'].includes(String(s.phase))) || (original.action === 'stop' && s.phase === 'stopped'))) {
            if (original.action !== 'stop' && original.browse === browse.current) setFollow({ run: ids.run, browse: original.browse });
            intent.current = null; setPending(null); setError(null);
          }
        }
      } catch { if (current() && epoch === controlEpoch.current) { verified.current = null; setStatus(null); setControls(null); setClosed(false); setWorkerError('Unable to verify the paper worker. Committed history is still available; controls require verified worker status.'); } }
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
        const next = follow && follow.browse === browse.current && directory.some(r => r.runId === follow.run) ? follow.run : null;
        const run = next ?? selected ?? (directory.find(r => !r.archive)?.runId || null);
        if (!run) { if (current()) setHistoryError(null); return; }
        const [data, events] = await Promise.all([runSnapshot(client, owner, run, controller.signal), eventSnapshot(client, owner, run, controller.signal)]);
        if (current()) { setSelected(run); setSnapshot(data); setEventCount(events.length); setHistoryError(null); if (next) setFollow(null); }
      } catch { if (current()) setHistoryError('Unable to refresh committed history. The last complete snapshot remains shown; refresh to retry reads.'); }
    }
    async function poll() {
      await history();
      if (current()) timer = setTimeout(() => void poll(), 10000);
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [api, owner, selected, refresh, legacyReader, follow]);
  const sameTarget = !intent.current || (controls !== null && intent.current.run === controls.run
    && intent.current.start === controls.start && intent.current.stop === controls.stop);
  async function command(action: 'start' | 'stop' | 'settle') {
    if (!api || !controls || operation.current || archive.current || !sameTarget
      || !verified.current || verified.current.run !== controls.run || verified.current.start !== controls.start
      || verified.current.stop !== controls.stop) return;
    if (action === 'settle' && (status?.busy === true || !['pending', 'drained'].includes(String(status?.phase)) || intent.current?.action === 'stop')) return;
    if (intent.current && action !== 'settle' && action !== intent.current.action) return;
    const original = intent.current ?? { action, ...controls, browse: browse.current };
    intent.current = original;
    controlEpoch.current += 1;
    const flight = {}; operation.current = flight;
    const originalCredentials = credentials;
    setPending(action); setError(null);
    try {
      const result = workerStatus(await api.worker(action, { request_id: action === 'stop' ? original.stop : original.start }), owner, original.run);
      if (!originalCredentials.active) return;
      if (!verified.current || verified.current.run !== original.run || verified.current.start !== original.start
        || verified.current.stop !== original.stop || result.request_id !== original.start) throw Error();
      controlEpoch.current += 1;
      setStatus(result);
      if (action !== 'stop' && browse.current === original.browse) setFollow({ run: original.run, browse: original.browse });
      if (['pending', 'drained'].includes(String(result.phase))) setPending(original.action);
      else { intent.current = null; setPending(null); }
      setRefresh(n => n + 1);
    } catch { if (originalCredentials.active) setError('Control acknowledgment is uncertain. Inspect status before settlement; no new run or control ID has been generated.'); }
    finally { if (operation.current === flight) operation.current = null; }
  }
  async function archiveRun() {
    if (!api || !selected || !snapshot || operation.current || intent.current) return;
    if (archive.current && archive.current.run !== selected) return;
    archive.current ??= { run: selected, revision: snapshot.revision, request: crypto.randomUUID() };
    const original = archive.current;
    const flight = {}; operation.current = flight;
    const originalCredentials = credentials;
    setPending('archive');
    try {
      const receipt = record(await api.read('archive_run', { run: original.run, expected_revision: original.revision, request_id: original.request }));
      if (!originalCredentials.active) return;
      if (receipt.owner_id !== owner || receipt.run_id !== original.run || receipt.request_id !== original.request || receipt.revision !== original.revision || receipt.archived !== true) throw Error();
      archive.current = null; setPending(null); setError(null); setRefresh(n => n + 1);
    } catch { if (originalCredentials.active) setError('Archive outcome is uncertain. Refresh to inspect the original receipt; holdings and history remain retained.'); }
    finally { if (operation.current === flight) operation.current = null; }
  }
  const run = snapshot?.runs.at(-1)?.data;
  const members = React.useMemo(() => snapshot ? latestEntities(snapshot.probes).map(row => ({ row, details: probeDetails(row.data) })) : [], [snapshot]);
  const trades = React.useMemo(() => snapshot ? latestEntities(snapshot.trades).map(row => tradeDetails(row.data)) : [], [snapshot]);
  const evaluations = React.useMemo(() => snapshot ? snapshot.evaluations.map(row => evaluationDetails(row.data)) : [], [snapshot]);
  const costs = run ? executionDetails(run.execution_policy) : null;
  const names = React.useMemo(() => new Map(members.map(m => [m.details.balance.id, String(m.row.data.name)])), [members]);
  return <div className="space-y-6">
    <h1 className="text-2xl font-semibold">Evolutionary paper pilot</h1>
    <p className="text-sm text-muted-foreground">Two EMA genes · eight candidates · SOL/USD reference · one evaluation window. Costs are an uncalibrated scenario. Paper balances are research records.</p>
    <div className="rounded-lg border p-4 space-y-3">
      <p>Worker: {closed ? 'closed by configuration' : String(status?.phase ?? 'unverified')}. Stop requested: {status ? (status.stop_requested === true ? 'yes' : 'no') : 'unavailable'}.</p>
      <p className="break-all text-sm">Configured worker run: {controls?.run ?? 'unavailable; no verified control target'}.</p>
      <p className="break-all text-sm">Selected history: {selected ?? 'none'}.</p>
      {controls && selected && controls.run !== selected && <p role="status">You are viewing a different historical run. Start and Stop address only the configured worker run shown above.</p>}
      {closed && <p role="status">Both worker read endpoints report a closed paper service. Controls are disabled. Retained history can still be inspected; this does not verify a configured owner or run.</p>}
      {follow && <p role="status" className="break-all">Acknowledged worker run {follow.run}; waiting for owner-bound discovery and a complete snapshot before switching history.</p>}
      {!sameTarget && <p role="alert">The configured worker changed while an original request was retained. Settlement is blocked for the new target; the original run and IDs remain retained.</p>}
      {status?.requires_reconciliation === true && <p role="status">The worker requires reconciliation. Committed history may precede the failure; a new worker cannot resume this run.</p>}
      <div className="flex flex-wrap gap-3">
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!controls || !sameTarget || !!operation.current || (pending !== null && pending !== 'start') || status?.phase !== 'fresh'} onClick={() => void command('start')}>Start configured pilot</button>
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!controls || !!pending} onClick={() => void command('stop')}>Stop and retain holdings</button>
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!controls || !sameTarget || !!operation.current || !['pending', 'drained'].includes(String(status?.phase)) || status?.busy === true || (pending !== null && pending !== 'start' && pending !== 'settle')} onClick={() => void command('settle')}>Settle original operation</button>
        <button className="rounded border px-3 py-2" onClick={() => setRefresh(n => n + 1)}>Refresh status and history</button>
      </div>
      <p className="text-sm">Stopping preserves positions and cash. A restart requires reconciliation; automatic resume is unavailable.</p>
      {pending && <p role="status">Original {pending} request retained; inspect status before continuing.</p>}
      {intent.current && <p className="break-all text-sm">Original control run: {intent.current.run}.</p>}
      {error && <p role="alert" className="text-red-400">{error}</p>}
      {workerError && <p role="alert" className="text-red-400">{workerError}</p>}
      {historyError && <p role="alert" className="text-red-400">{historyError}</p>}
    </div>
    <label className="block">Run history
      <select className="ml-3 rounded border bg-background p-2" value={selected ?? ''} onChange={e => { browse.current += 1; setFollow(null); setSnapshot(null); setEventCount(null); setSelected(e.target.value || null); }}>
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
      <p className="text-sm">Scenario cost policy: {costs?.version ?? 'not recorded'}. Fee {costs?.fee ?? 'not recorded'} bps · slippage {costs?.slippage ?? 'not recorded'} bps · half-spread {costs?.halfSpread ?? 'not recorded'} bps. These assumptions have not been calibrated to executable fills.</p>
      <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={run.status !== 'stopped' || !!operation.current || (pending !== null && pending !== 'archive')} onClick={() => void archiveRun()}>Archive stopped run, retain history</button>
    </div>}
    {members.length > 0 && <div className="overflow-auto"><table className="w-full text-sm"><caption className="text-left mb-2">Committed candidate balances in USD · frozen at revision {snapshot?.revision}</caption><thead><tr><th scope="col" className="text-left">Candidate</th><th scope="col">Generation</th><th scope="col">Fast / slow EMA</th><th scope="col">Account cash</th><th scope="col">Reference equity</th><th scope="col">Terminal capital</th><th scope="col">State</th></tr></thead><tbody>
      {members.map(({ row, details: d }) => { const b = d.balance; return <tr key={b.id} className="border-t"><th scope="row" className="py-2 text-left font-normal">{String(row.data.name)}</th><td className="text-center">{d.generation ?? 'Not recorded'}</td><td className="text-center">{d.genes ? `${d.genes.fast} / ${d.genes.slow}` : 'Not recorded'}</td><td className="text-center">${displayUSD(b.economicCash)}</td><td className="text-center">{b.equity === null ? 'Unavailable' : `$${displayUSD(b.equity)}`}</td><td className="text-center">{b.terminalCash === null ? 'Unavailable' : `$${displayUSD(b.terminalCash)}`}</td><td className="text-center">{b.retired ? 'Retired' : run?.status === 'running' ? 'Current cohort member' : 'Retained, worker not running'}</td></tr>; })}
    </tbody></table></div>}
    {snapshot && <details className="rounded-lg border p-4"><summary>Candidate risk and ancestry ({members.length} accounts)</summary>
      <p className="my-2 text-sm text-muted-foreground">Observed drawdown uses accepted reference marks. Retired records carry the last observation before replacement, including the peak and closed-trade count. This can precede the final close; completed evaluation counts are shown below, and final-score drawdown is not independently stored.</p>
      {members.map(({ row, details: d }) => <div key={d.balance.id} className="border-t py-3 text-sm">
        <p className="break-all">{String(row.data.name)} · {d.balance.id} · generation {d.generation ?? 'not recorded'} · EMA {d.genes ? `${d.genes.fast} / ${d.genes.slow}` : 'not recorded'}</p>
        <p>Observed maximum drawdown {d.drawdown ?? 'not recorded'} · observed peak {d.peak === null ? 'not recorded' : `$${d.peak}`} · last observed closed-trade count {d.trades ?? 'not recorded'}. Basis: {d.balance.metricsBasis}; equity: {String(row.data.equity_basis)}.</p>
        <p className="break-all">Ancestry: {d.lineage ? `${d.lineage.operation} · ${d.lineage.strategy} · version ${d.lineage.version}${d.lineage.supported ? '' : ' (unrecognized version; no semantic interpretation)'}` : 'not recorded'}. Source window: {d.lineage?.iteration ?? 'none recorded'}.</p>
        {d.lineage?.sources.map((s, i) => <p key={`${s.role}:${i}`} className="break-all">{s.role}: {names.get(s.id) ?? 'Unnamed candidate'} · {s.id}</p>)}
      </div>)}
    </details>}
    {snapshot && <details className="rounded-lg border p-4"><summary>Trade details ({trades.length} positions)</summary>
      <p className="my-2 text-sm text-muted-foreground">Scenario fills and fees in USD. Open positions have no realized exit P&amp;L.</p>
      {trades.map(t => <div key={t.id} className="border-t py-3 text-sm">
        <p>{t.asset} · candidate {t.account.slice(0, 8)} · {t.closed ? 'Closed' : 'Open, retained'} · quantity {t.quantity}</p>
        <p>Entry ${t.entryPrice} · notional ${t.entryNotional} · entry fee ${t.entryFee}. Opened {t.opened}.</p>
        <p>{t.netPnl === null ? 'Realized P&L unavailable while open.' : `Exit $${t.exitPrice} · exit fee $${t.exitFee} · realized scenario P&L $${t.netPnl} · ${t.exitReason}. Closed ${t.closedAt}.`}</p>
      </div>)}
    </details>}
    {snapshot && <details className="rounded-lg border p-4"><summary>Evaluation details ({evaluations.length} windows)</summary>
      <p className="my-2 text-sm text-muted-foreground">Only completed common windows supply parent selection. An early terminal result is retained through the deadline; an aborted cohort is withheld from selection, including any early terminal score already recorded. Selection does not establish profitability or promotion to live trading.</p>
      <p className="my-2 text-sm">Reviewed current worker policy: equity-roi-historical-dd-v1, provisional heuristic. Fitness = portfolio ROI − 2 × observed historical maximum drawdown. Trade count and Sharpe do not add a reward. Formula/version metadata and final-score drawdown are not persisted per window in these older records; this explanation does not re-score or assign the current formula to an unknown policy.</p>
      {evaluations.map(e => <div key={e.iteration} className="border-t py-3 text-sm"><p className="break-all">Generation {e.generation} · {e.iteration} · {e.phase}</p>
        <p>Common start: {sourceTime(e.started)}. Deadline: {sourceTime(e.ends)}. {e.phase === 'completed' ? 'Completed' : 'Aborted'} at: {sourceTime(e.completed)}. Horizon: {e.horizon ?? 'not recorded'} source seconds.</p>
        <p className="break-all">Window policy: {e.windowPolicy ?? 'not recorded'} · score format: {e.scoringPolicy ?? 'not recorded'} · selection policy: {e.selectionPolicy ?? 'none recorded'}{e.abortReason ? ` · abort reason: ${e.abortReason}` : ''}.</p>
        {e.windowPolicy !== 'common-market-window-v1' && <p>Window policy is missing or unrecognized. Current window semantics have not been assigned to this record.</p>}
        {e.results.map(r => <div key={r.member} className="mt-2"><p className="break-all">{names.get(r.member) ?? r.member} · {r.status}{r.early ? ' (early terminal)' : ''} · {r.eligible ? 'completed cohort; selection input' : e.phase === 'aborted' ? 'withheld from selection' : 'selection provenance unverified'} · {r.reason}</p>
          <p>Recorded ROI {displayROI(r.roi)} · fitness {r.fitness === null ? 'unavailable' : r.fitness.toFixed(6)} · {r.trades} trades · terminal at {sourceTime(r.terminated)}.</p>
        </div>)}
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
