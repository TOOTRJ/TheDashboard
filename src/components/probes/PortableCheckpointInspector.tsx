"use client";

import * as React from 'react';
import { inspectPortableCheckpoint, type PortableDisplayBinding, type PortableCheckpointView } from '@/lib/probes/portable-checkpoint-inspector';
import { displayUSD } from '@/lib/probes/durable-read-model';

type Props = { owner: string | null; scopeKey: string | null; raw: string | null; binding: PortableDisplayBinding | null; evidenceLabel: string };
type Publication = { owner: string; scopeKey: string; raw: string; bindingKey: string; view: PortableCheckpointView | null };

/** Inert versioned inspector. It never selects a worker or contacts a provider.
 * Every displayed result belongs to the exact current owner/input/binding.
 */
export function PortableCheckpointInspector({ owner, scopeKey, raw, binding, evidenceLabel }: Props) {
  const bindingKey = binding ? JSON.stringify(binding) : '';
  const [publication, setPublication] = React.useState<Publication | null>(null);
  React.useEffect(() => {
    if (!owner || !scopeKey || !raw || !bindingKey) return;
    let current = true;
    const captured = JSON.parse(bindingKey) as PortableDisplayBinding;
    void inspectPortableCheckpoint(raw, captured, owner).then(view => {
      if (current) setPublication({ owner, scopeKey, raw, bindingKey, view });
    }, () => {
      if (current) setPublication({ owner, scopeKey, raw, bindingKey, view: null });
    });
    return () => { current = false; };
  }, [owner, scopeKey, raw, bindingKey]);
  const visible = publication?.owner === owner && publication.scopeKey === scopeKey
    && publication.raw === raw && publication.bindingKey === bindingKey
    ? publication : null;
  if (!owner || !scopeKey || !raw || !binding) return <p role="status">No scoped portable checkpoint is selected.</p>;
  if (!visible) return <p role="status">Checking portable checkpoint scope, version and all 13 original dependency wires…</p>;
  if (!visible.view) return <p role="alert">Portable checkpoint is unavailable or incompatible. No checkpoint data is shown.</p>;
  const view = visible.view;
  return <section aria-label="Original portable checkpoint inspector" className="space-y-4 rounded border p-4">
    <h2 className="text-xl font-semibold">Original portable model v2 · guarded laboratory</h2>
    <p>{evidenceLabel}</p>
    <p className="rounded border p-3">This inspector checks bytes against the supplied binding. It does not authenticate
      a database reader, replay evolution, prove provider authenticity, restore a lease or authorize a worker to run.</p>
    <dl className="grid gap-2 sm:grid-cols-2">
      <div><dt className="font-semibold">Checkpoint status</dt><dd>{view.status} · revision {view.revision}
        {view.historical ? ` · historical; current native revision ${view.currentRevision}` : ' · supplied current head'}</dd></div>
      <div><dt className="font-semibold">Generation</dt><dd>{view.generation}. Cumulative completed-window history is unavailable in this checkpoint.</dd></div>
      <div><dt className="font-semibold">Original source profile</dt><dd>{view.source}</dd></div>
      <div><dt className="font-semibold">Dependencies</dt><dd>{view.dependencyPins} original ordered wires verified against their SHA256 references.</dd></div>
      <div><dt className="font-semibold">Source sequence / EMA bars</dt><dd>{view.sourceSequence} / {view.emaCount}</dd></div>
      <div><dt className="font-semibold">Risk / restart</dt><dd>Risk active: {String(view.riskActive)} · restart required: {String(view.restartRequired)}</dd></div>
      <div><dt className="font-semibold">Accounting</dt><dd>{view.currency} reference accounting for {view.asset}; execution costs are an uncalibrated scenario.</dd></div>
      <div><dt className="font-semibold">Reserve</dt><dd>${displayUSD(view.reserve)} USD · exact stored amount <code>{view.reserve}</code></dd></div>
    </dl>
    <p>Model <code>{view.model}</code>; assessment <code>{view.assessment}</code>.</p>
    <p>Recorded native guard observation: {view.guardObservedAt}. This is not a current freshness or final visible-instant guarantee.</p>
    <div className="overflow-x-auto"><table className="w-full text-left text-sm">
      <caption className="text-left font-semibold mb-2">Eight active checkpoint accounts and original EMA genes</caption>
      <thead><tr><th scope="col">Account</th><th scope="col">EMA fast / slow</th><th scope="col">Cash USD</th><th scope="col">Closed trades</th><th scope="col">Decision state</th></tr></thead>
      <tbody>{view.accounts.map(account => <tr key={account.id} className="border-t">
        <th scope="row" className="py-2 font-normal">{account.name}</th>
        <td>{account.fastPeriod} / {account.slowPeriod}</td>
        <td>${displayUSD(account.cash)}<br /><code>{account.cash}</code></td>
        <td>{account.trades}</td><td>{account.terminal ? 'terminal' : account.pending ? 'pending decision' : 'no pending decision'}</td>
      </tr>)}</tbody>
    </table></div>
    <p>Held positions: {view.holdings.length}. A stopped checkpoint can retain positions; Stop does not imply a sale.</p>
    {view.holdings.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm">
      <caption className="text-left font-semibold mb-2">Original held positions · exact stored quantities and amounts</caption>
      <thead><tr><th scope="col">Position</th><th scope="col">Asset / quantity</th><th scope="col">Reference entry USD</th><th scope="col">Cash debited USD</th></tr></thead>
      <tbody>{view.holdings.map(position => <tr key={position.id} className="border-t">
        <th scope="row" className="py-2 font-normal break-all">{position.id}</th>
        <td>{position.asset} · <code>{position.quantity}</code></td><td><code>{position.referencePrice}</code></td>
        <td><code>{position.cashDebit}</code></td>
      </tr>)}</tbody>
    </table></div> : null}
    <p>Restoration authority: false · hosted authority: false · running authority: false.
      The optimizer graph and cumulative private history are not rendered or trusted by this inspector.</p>
  </section>;
}
