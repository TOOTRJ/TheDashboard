import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import { webcrypto, createHash } from 'node:crypto';
import ts from 'typescript';

const exports = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/lib/probes/portable-checkpoint-inspector.ts', 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText,
{ exports, TextEncoder, crypto: webcrypto, Uint8Array });
const { inspectPortableCheckpoint: inspect } = exports;
const fixtures = JSON.parse(fs.readFileSync('tests/probes/fixtures/portable-checkpoint-inspector.json', 'utf8')).records;
const native = fixtures.native_lab, two = fixtures.two_windows, held = fixtures.held_positions;
const sha = value => createHash('sha256').update(value).digest('hex');
const canonical = value => {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
};
const inspectRecord = fixture => inspect(fixture.wire, fixture.binding, fixture.binding.owner_id);

test('actual native envelope preserves original model/source/version and all thirteen pins without authority', async () => {
  const value = await inspectRecord(native);
  assert.equal(value.model, 'ga-portable-provider-model-research-v2');
  assert.equal(value.source, 'synthetic-exact-fixture-v1'); assert.equal(value.status, 'stopped');
  assert.equal(value.currency, 'USD'); assert.equal(value.dependencyPins, 13); assert.equal(value.accounts.length, 8);
  assert.equal(value.restorationAuthority, false); assert.equal(value.hostedAuthority, false); assert.equal(value.runningAuthority, false);
  assert.equal(value.initialCash, '1000'); assert.equal(value.holdings.length, 0);
  assert.equal(Object.hasOwn(value, 'optimizer'), false); assert.equal(Object.hasOwn(value, 'history'), false);
});
test('two completed synthetic windows display original generation and gene periods without native relabeling', async () => {
  const value = await inspectRecord(two);
  assert.equal(value.generation, '2'); assert.equal(value.source, 'synthetic-exact-fixture-v1');
  assert.ok(value.accounts.every(account => account.fastPeriod >= 3 && account.fastPeriod <= 12 && account.slowPeriod >= 15 && account.slowPeriod <= 60));
  assert.equal(value.runningAuthority, false); assert.match(two.evidence, /no native acceptance/);
});
test('held positions keep every exact 18-place quantity and 36-place cash amount', async () => {
  const value = await inspectRecord(held);
  const raw = JSON.parse(JSON.parse(held.wire).manifest_wire);
  assert.equal(value.holdings.length, 8);
  assert.equal(value.holdings[0].quantity, raw.positions[0].entry.quantity);
  assert.equal(value.holdings[0].cashDebit, raw.positions[0].entry.cash_debit);
  assert.equal(value.accounts[0].cash, raw.accounts.find(account => account.id === value.accounts[0].id).cash);
  assert.equal(value.currency, 'USD'); assert.equal(value.asset, 'SOL/USD');
  assert.equal(value.holdings[0].cashDebit.split('.')[1].length, 36);
});
test('owner replacement refuses the entire previous checkpoint', async () => {
  await assert.rejects(inspect(native.wire, native.binding, '00000000-0000-0000-0000-000000000007'), /unavailable or incompatible/);
});
test('unknown envelope/model/status and any claimed authority are refused', async () => {
  for (const [key, value] of [['format', 'v3'], ['current_status', 'idle'], ['pending_command_authority', true],
    ['restoration_authority', true], ['hosted_authority', true]]) {
    const row = JSON.parse(native.wire); row[key] = value;
    await assert.rejects(inspect(JSON.stringify(row), native.binding, native.binding.owner_id));
  }
  for (const [key, value] of [['model_format', 'v3'], ['assessment_format', 'v3'], ['record_observed', false],
    ['pending_until_commit', true], ['final_visible_instant_freshness', true], ['restoration_authority', true],
    ['guard_observed_at', null], ['guard_observed_at', '2026-13-12T01:02:03.000123+00:00'],
    ['guard_observed_at', '0000-10-12T01:02:03.000123+00:00']]) {
    const row = JSON.parse(native.wire); row.receipt[key] = value;
    await assert.rejects(inspect(JSON.stringify(row), native.binding, native.binding.owner_id));
  }
});
test('foreign scope and original command/semantic/catalog/hash differences are refused', async () => {
  for (const key of ['owner_id', 'run_id', 'command_id', 'revision', 'manifest_sha256', 'command_sha256', 'semantic_validator_sha256', 'native_package_sha256']) {
    const row = JSON.parse(native.wire); row.receipt[key] = 'different';
    await assert.rejects(inspect(JSON.stringify(row), native.binding, native.binding.owner_id));
  }
});
test('missing, duplicate, reordered, changed or oversized original component wires are refused', async () => {
  for (const mode of ['missing', 'duplicate', 'reordered', 'changed', 'oversized']) {
    const row = JSON.parse(native.wire);
    if (mode === 'missing') row.component_wires.pop();
    if (mode === 'duplicate') row.component_wires[1] = row.component_wires[0];
    if (mode === 'reordered') [row.component_wires[0], row.component_wires[1]] = [row.component_wires[1], row.component_wires[0]];
    if (mode === 'changed') row.component_wires[0] += ' ';
    if (mode === 'oversized') row.component_wires[0] = 'x'.repeat(196609);
    await assert.rejects(inspect(JSON.stringify(row), native.binding, native.binding.owner_id));
  }
});
test('duplicate keys, raw numbers, malformed/truncated JSON and byte caps fail closed', async () => {
  const row = JSON.parse(native.wire); row.current_revision = Number(native.binding.revision);
  for (const raw of ['{"format":"x","format":"x"}', '{"x":', JSON.stringify(row), 'x'.repeat(589825),
    '{"'.repeat(70), native.wire.replace('"format":', '"extra":false,"format":')]) {
    await assert.rejects(inspect(raw, native.binding, native.binding.owner_id));
  }
});
test('historical checkpoint is clearly marked and never grants continuation or running authority', async () => {
  const row = JSON.parse(native.wire); row.current_revision = (BigInt(native.binding.revision) + BigInt(1)).toString();
  const value = await inspect(JSON.stringify(row), native.binding, native.binding.owner_id);
  assert.equal(value.historical, true); assert.equal(value.revision, native.binding.revision);
  assert.equal(value.currentRevision, row.current_revision); assert.equal(value.runningAuthority, false);
});
test('decimal revision above JavaScript safe integer is preserved byte-for-byte', async () => {
  const row = JSON.parse(native.wire), manifest = JSON.parse(row.manifest_wire);
  const revision = '9007199254740993'; manifest.revision = { $integer: revision };
  row.manifest_wire = canonical(manifest); row.current_revision = revision; row.receipt.revision = revision;
  row.receipt.manifest_sha256 = sha(row.manifest_wire);
  const binding = { ...native.binding, revision, manifest_sha256: row.receipt.manifest_sha256 };
  const value = await inspect(JSON.stringify(row), binding, binding.owner_id);
  assert.equal(value.revision, revision); assert.equal(value.currentRevision, revision);
});
test('browser implementation has no API, optimizer restoration, signing or worker controls', () => {
  const parser = fs.readFileSync('src/lib/probes/portable-checkpoint-inspector.ts', 'utf8');
  const component = fs.readFileSync('src/components/probes/PortableCheckpointInspector.tsx', 'utf8');
  for (const source of [parser, component]) assert.doesNotMatch(source, /\b(fetch|createClient|localStorage|sessionStorage|randomUUID|signTransaction|paperAPI)\s*[.(]/);
  assert.doesNotMatch(component, /<button|onClick=/);
  assert.match(component, /publication\.raw === raw/); assert.match(component, /publication\.bindingKey === bindingKey/);
});

function publicationHarness() {
  const pending = [], effects = [];
  let publication = null, dirty = false, cleanup = null, previousDeps = null, tree;
  let props = { owner: native.binding.owner_id, scopeKey: 'session-A-1', raw: native.wire,
    binding: native.binding, evidenceLabel: 'Public synthetic test' };
  const react = {
    useState() { return [publication, next => { publication = next; dirty = true; }]; },
    useEffect(effect, deps) {
      if (!previousDeps || deps.some((value, index) => value !== previousDeps[index])) {
        previousDeps = deps; effects.push(() => { cleanup?.(); cleanup = effect(); });
      }
    },
  };
  const modules = {
    react, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    '@/lib/probes/durable-read-model': { displayUSD: value => value },
    '@/lib/probes/portable-checkpoint-inspector': { inspectPortableCheckpoint(raw, binding, owner) {
      let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
      pending.push({ raw, binding, owner, resolve, reject }); return promise;
    } },
  };
  const loaded = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/components/probes/PortableCheckpointInspector.tsx', 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText,
  { exports: loaded, require: name => { assert.ok(Object.hasOwn(modules, name), name); return modules[name]; } });
  function render() { dirty = false; tree = loaded.PortableCheckpointInspector(props); while (effects.length) effects.shift()(); }
  const text = node => {
    if (typeof node === 'string' || typeof node === 'number') return String(node);
    if (!node || typeof node !== 'object') return '';
    return [node.props?.children].flat(Infinity).map(text).join(' ');
  };
  render();
  return { pending, text: () => text(tree), update: next => { props = { ...props, ...next }; render(); },
    async resolve(index, value) { pending[index].resolve(value); await new Promise(setImmediate); if (dirty) render(); },
    async reject(index) { pending[index].reject(Error('private obsolete detail')); await new Promise(setImmediate); if (dirty) render(); },
    dispose() { cleanup?.(); },
  };
}
test('component render gate clears published data immediately for replacement and A→B→A sessions', async () => {
  const view = await inspectRecord(native), h = publicationHarness();
  await h.resolve(0, view); assert.match(h.text(), /Eight active checkpoint accounts/);
  h.update({ owner: '00000000-0000-0000-0000-000000000007', scopeKey: 'session-B-2' });
  assert.doesNotMatch(h.text(), /Eight active checkpoint accounts/);
  h.update({ owner: native.binding.owner_id, scopeKey: 'session-A-3' });
  assert.match(h.text(), /Checking portable checkpoint/); assert.doesNotMatch(h.text(), /Eight active checkpoint accounts/);
  await h.resolve(1, view); assert.match(h.text(), /Checking portable checkpoint/);
  await h.resolve(2, view); assert.match(h.text(), /Eight active checkpoint accounts/); h.dispose();
});
test('component late success/error cannot publish across logout, scope refresh or identical overlapping inputs', async () => {
  const view = await inspectRecord(native), h = publicationHarness();
  h.update({ owner: null, scopeKey: null }); await h.resolve(0, view);
  assert.match(h.text(), /No scoped portable checkpoint/); assert.doesNotMatch(h.text(), /Eight active checkpoint accounts/);
  h.update({ owner: native.binding.owner_id, scopeKey: 'session-A-2' });
  h.update({ scopeKey: 'session-A-3' }); await h.reject(1);
  assert.match(h.text(), /Checking portable checkpoint/); assert.doesNotMatch(h.text(), /unavailable or incompatible|private obsolete detail/);
  await h.resolve(2, view); assert.match(h.text(), /Eight active checkpoint accounts/); h.dispose();
});
test('component changing the manifest/input clears old fields while failed new parsing publishes only a generic error', async () => {
  const view = await inspectRecord(native), h = publicationHarness(); await h.resolve(0, view);
  h.update({ raw: '{unknown', binding: { ...native.binding, manifest_sha256: 'c'.repeat(64) } });
  assert.doesNotMatch(h.text(), /Eight active checkpoint accounts/); await h.reject(1);
  assert.match(h.text(), /unavailable or incompatible/); assert.doesNotMatch(h.text(), /Eight active checkpoint accounts|private obsolete detail/); h.dispose();
});
