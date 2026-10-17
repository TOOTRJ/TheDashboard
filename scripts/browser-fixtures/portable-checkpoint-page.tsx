"use client";

// Copied only into an owned loopback snapshot; never a production route.
import * as React from 'react';
import { PortableCheckpointInspector } from '@/components/probes/PortableCheckpointInspector';
import type { PortableDisplayBinding } from '@/lib/probes/portable-checkpoint-inspector';
import fixture from '@/../tests/probes/fixtures/portable-checkpoint-inspector.json';

const records = fixture.records;
type RecordName = keyof typeof records;
type Fault = 'none' | 'unknown format' | 'unknown status' | 'missing pin' | 'pending receipt' | 'historical';

function admitted() {
  try {
    const url = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? '');
    return url.protocol === 'http:' && url.hostname === '127.0.0.1'
      && url.origin === process.env.NEXT_PUBLIC_SUPABASE_URL
      && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY === 'dashboard-browser-fixture-public-key';
  } catch { return false; }
}

export default function PortableCheckpointBrowserFixture() {
  const [record, setRecord] = React.useState<RecordName>('native_lab');
  const [scope, setScope] = React.useState<'original owner' | 'foreign owner' | 'signed out'>('original owner');
  const [scopeSequence, setScopeSequence] = React.useState(0);
  const [fault, setFault] = React.useState<Fault>('none');
  const selected = records[record];
  const raw = React.useMemo(() => {
    if (fault === 'none') return selected.wire;
    const value = JSON.parse(selected.wire);
    if (fault === 'unknown format') value.format = 'unreviewed-v3';
    if (fault === 'unknown status') value.current_status = 'idle';
    if (fault === 'missing pin') value.component_wires.pop();
    if (fault === 'pending receipt') value.receipt.pending_until_commit = true;
    if (fault === 'historical') value.current_revision = (BigInt(selected.binding.revision) + BigInt(1)).toString();
    return JSON.stringify(value);
  }, [selected, fault]);
  const owner = scope === 'signed out' ? null : scope === 'original owner'
    ? selected.binding.owner_id : '00000000-0000-0000-0000-000000000007';
  if (!admitted()) return <p role="alert">Portable fixture refused: exact synthetic loopback configuration is required.</p>;
  return <main className="space-y-6 p-4">
    <section aria-label="Portable inspector fixture controls" className="space-y-3 rounded border p-4">
      <h1 className="text-xl font-semibold">Portable checkpoint browser fixture</h1>
      <p role="status">Fixture scope: {scope}. Record: {selected.label}. Fault: {fault}.</p>
      <p>Public synthetic owner identities only. One record preserves actual owned native laboratory readback;
        the two-window and held-position records are pure synthetic demonstrations. No API or worker is contacted.</p>
      <label className="block">Fixture record <select value={record} className="rounded border p-2 bg-background"
        onChange={event => setRecord(event.target.value as RecordName)}>
        {(Object.keys(records) as RecordName[]).map(name => <option key={name} value={name}>{records[name].label}</option>)}
      </select></label>
      <label className="block">Fixture scope <select value={scope} className="rounded border p-2 bg-background"
        onChange={event => { setScope(event.target.value as typeof scope); setScopeSequence(value => value + 1); }}>
        {(['original owner', 'foreign owner', 'signed out'] as const).map(name => <option key={name}>{name}</option>)}
      </select></label>
      <label className="block">Fixture fault <select value={fault} className="rounded border p-2 bg-background"
        onChange={event => setFault(event.target.value as Fault)}>
        {(['none', 'unknown format', 'unknown status', 'missing pin', 'pending receipt', 'historical'] as const).map(name => <option key={name}>{name}</option>)}
      </select></label>
    </section>
    <PortableCheckpointInspector owner={owner} scopeKey={owner ? scope + ':' + scopeSequence : null}
      raw={raw} binding={selected.binding as PortableDisplayBinding}
      evidenceLabel={selected.label + ': ' + selected.evidence} />
  </main>;
}
