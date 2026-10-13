"use client";

// This file is copied into an owned loopback snapshot; it is never an application route.
import * as React from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { PaperDashboard } from '@/components/probes/PaperDashboard';
import { createClient } from '@/lib/supabase/client';
import { createPaperFixtureController, PAPER_FIXTURE_SCENARIOS, type PaperFixtureController,
  type PaperFixtureScenario } from './paper-data';

function fixtureConfiguration() {
  try {
    const url = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? '');
    return url.protocol === 'http:' && url.hostname === '127.0.0.1'
      && url.origin === process.env.NEXT_PUBLIC_SUPABASE_URL
      && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY === 'dashboard-browser-fixture-public-key';
  } catch { return false; }
}

export default function PaperBrowserFixturePage() {
  const { user, session, loading, signOut } = useAuth();
  const admitted = fixtureConfiguration();
  const client = React.useMemo(() => admitted ? createClient() : null, [admitted]);
  const owner = user?.id ?? null;
  const controller = React.useMemo(() => admitted && owner ? createPaperFixtureController(owner) : null, [admitted, owner]);
  const [controllers, setControllers] = React.useState<PaperFixtureController[]>([]);
  const retained = React.useRef<PaperFixtureController[]>([]);
  const mounted = React.useRef(false);
  const [, redraw] = React.useState(0);
  const [authError, setAuthError] = React.useState(false);
  const [authBusy, setAuthBusy] = React.useState(false);

  React.useEffect(() => {
    if (!controller) return;
    retained.current = [...retained.current, controller];
    setControllers(previous => previous.includes(controller) ? previous : [...previous, controller]);
  }, [controller]);
  React.useEffect(() => {
    const subscriptions = controllers.map(actor => actor.subscribe(() => redraw(revision => revision + 1)));
    return () => { for (const unsubscribe of subscriptions) unsubscribe(); };
  }, [controllers]);
  React.useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      // Strict Mode can reestablish this effect synchronously; only actual retirement
      // disposes owned promise barriers after the component subscriptions retire.
      queueMicrotask(() => { if (!mounted.current) for (const actor of retained.current) actor.dispose(); });
    };
  }, []);

  async function login(name: 'alice' | 'bob') {
    if (!client || authBusy) return;
    setAuthBusy(true); setAuthError(false);
    try {
      const result = await client.auth.signInWithPassword({ email: `${name}@dashboard.invalid`, password: 'fixture-password' });
      if (result.error) setAuthError(true);
    } catch { setAuthError(true); }
    finally { setAuthBusy(false); }
  }
  if (!admitted) return <p role="alert">Paper fixture refused: exact synthetic loopback configuration is required.</p>;
  const snapshots = controllers.map(actor => ({ actor, snapshot: actor.snapshot() }));
  return <div className="space-y-6">
    <section className="rounded border p-4 space-y-3" aria-label="Synthetic paper fixture controls">
      <h1 className="text-xl font-semibold">Synthetic paper browser fixture</h1>
      <p role="status">Fixture actor: {controller?.label ?? 'signed out'}. Scenario: {controller?.snapshot().scenario ?? 'none'}.</p>
      <p>This uses the real PaperDashboard and AuthProvider with synthetic owner-bound data and controls.
        No RPC, wallet, transaction, real worker or cloud database is contacted by the Paper APIOverride.</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={authBusy} onClick={() => void login('alice')} className="rounded border px-3 py-2">Sign in fixture Alice</button>
        <button type="button" disabled={authBusy} onClick={() => void login('bob')} className="rounded border px-3 py-2">Sign in fixture Bob</button>
        <button type="button" disabled={authBusy || !user} onClick={() => void signOut()} className="rounded border px-3 py-2">Sign out fixture account</button>
      </div>
      {authError ? <p role="alert">Synthetic authentication failed.</p> : null}
      {controller ? <>
        <label className="block">Synthetic paper scenario
          <select value={controller.snapshot().scenario} className="ml-3 rounded border p-2 bg-background"
            onChange={event => controller.setScenario(event.target.value as PaperFixtureScenario)}>
            {PAPER_FIXTURE_SCENARIOS.map(scenario => <option key={scenario} value={scenario}>{scenario}</option>)}
          </select>
        </label>
        <p>After changing a scenario or resetting the synthetic worker, use the real dashboard’s
          “Refresh status and history” button below. A scenario change does not remount the dashboard.</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => controller.resetWorker()} className="rounded border px-3 py-2">Reset synthetic worker</button>
          <button type="button" onClick={() => controller.holdNext('read', 'discover')} className="rounded border px-3 py-2">Hold next fixture discovery</button>
          <button type="button" onClick={() => controller.holdNext('read', 'page')} className="rounded border px-3 py-2">Hold next fixture history page</button>
          <button type="button" onClick={() => controller.holdNext('worker', 'status')} className="rounded border px-3 py-2">Hold next fixture worker status</button>
          <button type="button" onClick={() => controller.holdNext('worker', 'start')} className="rounded border px-3 py-2">Hold next fixture Start acknowledgment</button>
          <button type="button" onClick={() => controller.holdNext('worker', 'stop')} className="rounded border px-3 py-2">Hold next fixture Stop acknowledgment</button>
        </div>
      </> : null}
      <details open className="rounded border p-3">
        <summary>Explicit captured-response barriers</summary>
        <p>Responses are frozen under the actor and original IDs that produced them. Release/reject
          can occur after another actor signs in; abort status is observable. Barriers reject after 90 seconds.</p>
        {snapshots.flatMap(({ actor, snapshot }) => snapshot.pending.map(pending => <div key={pending.id} className="border-t py-2 space-y-2">
          <p className="break-all">Barrier {pending.id} · actor {snapshot.label} · {pending.trace.kind} {pending.trace.action}
            {' · '}original request {pending.trace.requestId ?? 'read'} · signal aborted {String(pending.signalAborted)}.</p>
          <button type="button" onClick={() => actor.release(pending.id)} className="rounded border px-3 py-2">Release fixture barrier {pending.id}</button>
          <button type="button" onClick={() => actor.reject(pending.id)} className="ml-2 rounded border px-3 py-2">Reject fixture barrier {pending.id}</button>
        </div>))}
        {!snapshots.some(({ snapshot }) => snapshot.pending.length) ? <p>No pending fixture barriers.</p> : null}
      </details>
      <details className="rounded border p-3">
        <summary>Fixture original-ID request trace</summary>
        {snapshots.map(({ snapshot }, index) => <div key={`${snapshot.owner}:${index}`} className="border-t py-2">
          <p>Actor {snapshot.label} · configured run {snapshot.controlRun} · synthetic phase {snapshot.phase}.</p>
          <ol>{snapshot.traces.slice(-24).map(trace => <li key={trace.sequence} className="break-all">
            #{trace.sequence} {trace.kind} {trace.action} · run {trace.run ?? 'directory'} · original request {trace.requestId ?? 'none'}
            {trace.projection ? ` · projection ${trace.projection}` : ''}
          </li>)}</ol>
        </div>)}
      </details>
    </section>
    {loading ? <p role="status">Checking synthetic paper session…</p> : !user || !session || !controller ?
      <p role="status">Sign in a fixture actor to inspect paper history.</p> :
      <PaperDashboard key={user.id} owner={user.id} token={session.access_token}
        apiOverride={controller.api} legacyReader={controller.legacyReader} />}
  </div>;
}
