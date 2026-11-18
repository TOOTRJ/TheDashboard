"use client";

import * as React from 'react';
import { displayUSD } from '@/lib/probes/durable-read-model';
import { paperV6API, parsePaperV6History, parsePaperV6Status, PaperV6ClosedError,
  type PaperV6API, type PaperV6History, type PaperV6Status } from '@/lib/probes/paper-v6-api';

type Props = { owner: string; token: string; apiOverride?: PaperV6API };
type Intent = { run: string; action: 'start' | 'stop'; request: string };
type Credentials = { owner: string; token: string; api: PaperV6API | null };
type Observation = { credentials: Credentials; status: PaperV6Status; history: PaperV6History | null; after: number };

export function PaperV6Dashboard(props: Props) {
  return <PaperV6DashboardSession key={props.owner} {...props} />;
}

export function PaperV6DashboardSession({ owner, token, apiOverride }: Props) {
  const api = React.useMemo(() => {
    try { return apiOverride ?? paperV6API(token, process.env.NEXT_PUBLIC_VN_API_URL || ''); }
    catch { return null; }
  }, [token, apiOverride]);
  const credentials = React.useMemo(() => ({ owner, token, api }), [owner, token, api]);
  const active = React.useRef<Credentials | null>(null);
  const commandEpoch = React.useRef(0);
  const operation = React.useRef<{ controller: AbortController; credentials: Credentials } | null>(null);
  const intent = React.useRef<Intent | null>(null);
  const [retainedIntent, setIntent] = React.useState<Intent | null>(null);
  const [earlierStart, setEarlierStart] = React.useState<Intent | null>(null);
  const [observation, setObservation] = React.useState<Observation | null>(null);
  const [pageAfter, setPageAfter] = React.useState<number | null>(null);
  const [refresh, setRefresh] = React.useState(0);
  const [inFlight, setInFlight] = React.useState<Credentials | null>(null);
  const [verifiedFor, setVerifiedFor] = React.useState<Credentials | null>(null);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [readProblem, setReadProblem] = React.useState<string | null>(null);
  const [closed, setClosed] = React.useState(false);

  React.useLayoutEffect(() => {
    active.current = credentials;
    return () => {
      if (active.current === credentials) active.current = null;
      if (operation.current?.credentials === credentials) operation.current.controller.abort();
    };
  }, [credentials]);

  React.useEffect(() => {
    if (!api) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const current = () => !controller.signal.aborted && active.current === credentials;
    async function poll() {
      const originalEpoch = commandEpoch.current;
      try {
        const status = parsePaperV6Status(await api!.status(controller.signal), owner);
        if (!current() || commandEpoch.current !== originalEpoch) return;
        const after = pageAfter === null ? Math.max(0, status.sequence - 25) : Math.min(pageAfter, status.sequence);
        setObservation(previous => {
          if (previous?.credentials === credentials && previous.status.run === status.run && previous.status.sequence > status.sequence) return previous;
          return { credentials, status,
            history: previous?.credentials === credentials && previous.status.run === status.run ? previous.history : null, after };
        });
        setVerifiedFor(credentials); setClosed(false); setReadProblem(null);
        if (intent.current && status.run === intent.current.run && status.lastRequest === intent.current.request
          && !status.requiresReconciliation && status.phase !== 'pending') {
          intent.current = null; setIntent(null); setProblem(null);
        }
        // A complete replay may take longer than an HTTP request. Its verified
        // status enables Stop while historical projections remain unavailable.
        if (status.phase === 'recovering') return;
        let history: PaperV6History | null = null;
        let historyFailed = false;
        try { history = parsePaperV6History(await api!.history(after, 25, controller.signal), owner, status.run, after, 25); }
        catch { historyFailed = true; }
        if (!current() || commandEpoch.current !== originalEpoch) return;
        setObservation(previous => {
          if (previous?.credentials === credentials && previous.status.run === status.run && previous.status.sequence > status.sequence) return previous;
          return { credentials, status, history: history ?? (previous?.credentials === credentials && previous.status.run === status.run ? previous.history : null), after };
        });
        setClosed(false);
        setReadProblem(historyFailed ? 'Worker status is verified. Committed history could not refresh; the last complete page remains shown.' : null);
      } catch (error) {
        if (current()) {
          setVerifiedFor(null);
          setClosed(error instanceof PaperV6ClosedError);
          setReadProblem(error instanceof PaperV6ClosedError ? 'The worker is closed by configuration. Start and Stop are unavailable.'
            : 'Unable to verify worker status. Refresh to retry; previously committed observations remain shown.');
        }
      } finally {
        if (current()) timer = setTimeout(() => void poll(), 10000);
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [api, owner, credentials, pageAfter, refresh]);

  const observed = observation?.credentials === credentials ? observation : null;
  const status = observed?.status ?? null;
  const history = observed?.history ?? null;
  const projection = status?.projection ?? null;
  const busy = inFlight === credentials;
  const verified = status !== null && verifiedFor === credentials && !closed;
  const sameTarget = retainedIntent === null || retainedIntent.run === status?.run;
  const stoppedBeforeSeeding = status?.phase === 'stopped' && projection === null && status.sequence === 0;
  const canStart = verified && !busy && retainedIntent === null && !status?.busy
    && !status?.requiresReconciliation && (status?.phase === 'idle' || stoppedBeforeSeeding);

  async function command(action: 'start' | 'stop') {
    if (!api || !status || active.current !== credentials || operation.current || !verified || !sameTarget) return;
    if (intent.current && intent.current.action !== action && !(intent.current.action === 'start' && action === 'stop')) return;
    const interruptedStart = action === 'stop' && intent.current?.action === 'start' ? intent.current : null;
    if (interruptedStart) setEarlierStart(interruptedStart);
    const original = (interruptedStart ? null : intent.current) ?? { run: status.run, action, request: crypto.randomUUID() };
    intent.current = original; setIntent(original);
    const flight = { controller: new AbortController(), credentials };
    operation.current = flight; commandEpoch.current += 1; setInFlight(credentials); setProblem(null);
    try {
      const result = parsePaperV6Status(await api.command(action, original.request, flight.controller.signal), owner, original.run);
      if (active.current !== credentials) return;
      if (result.lastRequest !== original.request || (action === 'stop' && !['stopping', 'stopped', 'pending'].includes(result.phase))) throw Error();
      commandEpoch.current += 1;
      setObservation(previous => ({ credentials, status: result,
        history: previous?.credentials === credentials && previous.status.run === result.run ? previous.history : null,
        after: previous?.after ?? 0 }));
      if (!result.requiresReconciliation && result.phase !== 'pending') { intent.current = null; setIntent(null); }
      setVerifiedFor(credentials); setReadProblem(null); setClosed(false); setRefresh(n => n + 1);
    } catch {
      if (active.current === credentials) setProblem('The control acknowledgment is uncertain. Refresh status or retry the retained original request; its identity is preserved.');
    } finally {
      if (operation.current === flight) operation.current = null;
      if (active.current === credentials) setInFlight(null);
    }
  }

  return <div className="space-y-6">
    <h1 className="text-2xl font-semibold">Evolutionary paper trading</h1>
    <p className="text-sm text-muted-foreground">Two EMA genes · eight candidates · SOL/USD reference prices. Completed common evaluation windows drive the next generation. Paper fills use an uncalibrated cost scenario.</p>
    <section aria-label="Paper worker controls" className="space-y-3 rounded-lg border p-4">
      <p role="status">Worker: {closed ? 'closed by configuration' : status?.phase.replaceAll('_', ' ') ?? 'unverified'}.</p>
      <p className="break-all text-sm">Run: {status?.run ?? 'awaiting verified owner-bound status'}.</p>
      {status && <p>Generation {status.generation} · source epoch {status.epoch} · committed transition {status.sequence}.</p>}
      <div className="flex flex-wrap gap-3">
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!canStart} onClick={() => void command('start')}>Start paper trading</button>
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!verified || busy || !sameTarget || retainedIntent?.action === 'stop' || (!['recovering', 'warming_up', 'waiting_data', 'running', 'risk_halted', 'failed', 'pending'].includes(status?.phase ?? '') && retainedIntent?.action !== 'start')} onClick={() => void command('stop')}>Stop and retain holdings</button>
        {retainedIntent && <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!verified || busy || !sameTarget} onClick={() => void command(retainedIntent.action)}>Retry original {retainedIntent.action}</button>}
        <button className="rounded border px-3 py-2" onClick={() => setRefresh(n => n + 1)}>Refresh status and history</button>
      </div>
      {retainedIntent && <p role="status">Original {retainedIntent.action} request retained. Refreshing does not create another request.</p>}
      {earlierStart && <p role="status" className="break-all">Earlier uncertain Start retained as {earlierStart.request}. The independent Stop addresses the same run and does not issue another Start.</p>}
      {!sameTarget && <p role="alert">The worker run changed while a control was unresolved. Inspect the original run before sending another control.</p>}
      {status?.requiresReconciliation && <p role="alert">The original durable operation requires reconciliation before evolution or Start can continue. An independent Stop remains available for this verified run.</p>}
      {status?.phase === 'recovering' && <p>Replaying saved transitions before evolution resumes. Verified replay progress: {status.recoverySequence} transitions. Stop remains available during recovery.</p>}
      {status?.phase === 'warming_up' && <p>Collecting an uninterrupted history of reference prices before seeding candidates. A restart uses verified retained source data.</p>}
      {status?.phase === 'waiting_data' && <p>Waiting for the next valid provider observation. Failed or stale observations do not advance evolution.</p>}
      {status?.warmup && <p>Accepted warmup observations: {status.warmup.observed} of {status.warmup.required} required one-minute observations.</p>}
      {status?.warmup?.historyGap && <p role="status">A minute is missing from the retained source history. This run cannot reconstruct it; evolution remains blocked. Stop this run and configure a new paper pilot.</p>}
      {status?.phase === 'risk_halted' && <p role="alert">The paper risk boundary halted this run. Inspect the committed balances and assessments; Stop retains the recorded holdings.</p>}
      {status?.phase === 'stopped' && (stoppedBeforeSeeding
        ? <p>Paper trading stopped before candidates were seeded. Retained reference observations remain available.{canStart ? ' Start paper trading again to continue collecting for this run.' : ' Start remains unavailable until the worker state and original controls are verified.'}</p>
        : <p>Paper trading is stopped. Cash, open holdings and evaluation history remain retained. Another pilot requires a separately configured run.</p>)}
      {problem && <p role="alert" className="text-red-400">{problem}</p>}
      {readProblem && <p role="alert" className="text-red-400">{readProblem}</p>}
      {!api && <p role="alert">The paper worker endpoint is unavailable in this deployment.</p>}
    </section>
    {projection && <section aria-label="Committed paper balances" className="space-y-2 rounded-lg border p-4">
      <h2 className="text-lg font-semibold">Committed paper balances</h2>
      <p>Reference equity {projection.totalEquity === null ? 'unavailable until a reference mark is recorded' : `$${displayUSD(projection.totalEquity)}`} · reserve ${displayUSD(projection.reserveCash)} · {projection.openPositions} retained open positions.</p>
      <p className="text-sm text-muted-foreground">These balances reflect committed observations. They do not provide a current executable market quote.</p>
      <div className="overflow-auto"><table className="w-full text-sm"><caption className="mb-2 text-left">Current generation · {projection.asset} · {projection.population} candidates</caption>
        <thead><tr><th scope="col" className="text-left">Candidate</th><th scope="col">Generation</th><th scope="col">Fast / slow EMA</th><th scope="col">Paper cash</th><th scope="col">Reference equity</th></tr></thead>
        <tbody>{projection.members.map(member => <tr key={member.id} className="border-t"><th scope="row" className="py-2 text-left font-normal">{member.name}</th><td className="text-center">{member.generation}</td><td className="text-center">{member.fast} / {member.slow}</td><td className="text-center">${displayUSD(member.cash)}</td><td className="text-center">{member.equity === null ? 'Unavailable' : `$${displayUSD(member.equity)}`}</td></tr>)}</tbody>
      </table></div>
      <details><summary>Candidate ancestry and observed risk</summary>
        {projection.members.map(member => <div key={member.id} className="mt-2 border-t py-2 text-sm">
          <p>{member.name} · observed drawdown {member.drawdown ?? 'unavailable'} · closed trades {member.closedTrades ?? 'unavailable'}.</p>
          <p className="break-all">Parents: {member.parents === null ? 'not recorded' : member.parents.length === 0 ? 'founding candidate' : member.parents.join(', ')}.</p>
        </div>)}
      </details>
    </section>}
    <section aria-label="Committed paper history" className="space-y-3 rounded-lg border p-4">
      <h2 className="text-lg font-semibold">Committed history and assessments</h2>
      <p className="text-sm">Fitness uses portfolio ROI minus twice observed historical maximum drawdown. Complete common windows supply selection. Aborted windows retain their economics and are excluded from selection.</p>
      {history && <p>Showing {history.records.length} committed transitions through {history.next}, of {history.through} available at this read.</p>}
      <div className="flex flex-wrap gap-3">
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={!observed || observed.after === 0} onClick={() => setPageAfter(Math.max(0, (observed?.after ?? 0) - 25))}>Earlier history</button>
        <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={pageAfter === null} onClick={() => setPageAfter(null)}>Latest history</button>
      </div>
      {history?.records.map(row => <details key={row.sequence} className="border-t py-2 text-sm"><summary>Transition {row.sequence} · {row.kind.replaceAll('_', ' ')} · {row.assessments.length} finalized candidate assessments</summary>
        {row.assessments.map(assessment => <div key={assessment.probe} className="mt-2 border-l pl-3"><p>Candidate {assessment.probe.slice(0, 8)} · generation {assessment.generation} · {assessment.status} · {assessment.eligible ? 'eligible for selection' : 'withheld from selection'}.</p>
          <p>Recorded ROI {assessment.roi === null ? 'unavailable' : `${(assessment.roi * 100).toFixed(4)}%`} · fitness {assessment.fitness === null ? 'unavailable' : assessment.fitness.toFixed(6)} · {assessment.reason.replaceAll('_', ' ')}.</p>
          <p>Assessment drawdown {assessment.drawdown ?? 'unavailable'} · closed trades {assessment.closedTrades ?? 'unavailable'}.</p></div>)}
      </details>)}
      {history?.records.length === 0 && <p>No durable transitions have been committed for this run.</p>}
    </section>
  </div>;
}
