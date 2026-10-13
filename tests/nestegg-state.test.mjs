import assert from 'node:assert/strict';
import test from 'node:test';
import * as identity from '../src/lib/nestegg/result-identity.ts';
import { createNesteggWorkspaceScope } from '../src/lib/nestegg/session-scope.ts';
import { harness, transpile, A, constants, deferred, row, mc } from './helpers/nestegg-harness.mjs';
import { componentHarness } from './helpers/nestegg-component-harness.mjs';

function assertNoStaleConsumers(h) {
  assert.equal(h.component('NesteggExportMenu').monteCarlo, null);
  assert.equal(h.component('NesteggProjectionChart').monteCarloBands, null);
  assert.equal(h.component('NesteggChartTabs').goalProbability, null);
  assert.deepEqual([...h.component('NesteggInsightsPanel').insights], []);
  assert.ok(h.components('NesteggProbabilityCards').every(props => props.mc === null));
  assert.equal(h.component('NesteggComparisonTable'), undefined);
  assert.equal(h.component('NesteggSavedCompare').workspaceMonteCarlo, null);
  assert.deepEqual([...h.component('NesteggHeroInsight').highlights], []);
}

test('result envelopes refuse mismatched input/workspace/model/seed/purpose/path/generation identities', () => {
  const source = identity.captureNesteggCalculationSource('opaque', constants.DEFAULT_NESTEGG_INPUTS, 'base', 4);
  const policy = { modelVersion: 'v1', seedPolicy: 'seed', purpose: 'light', pathCount: 200 };
  const envelope = { identity: identity.nesteggCalculationIdentity(source, policy, 2), value: 'accepted' };
  assert.equal(identity.currentNesteggCalculation(envelope, source, policy, 2), 'accepted');
  for (const [key, value] of Object.entries({ workspaceKey: 'another', inputKey: 'another', inputGeneration: 5, scenario: 'aggressive', modelVersion: 'v2', seedPolicy: 'another', purpose: 'full-bundle', pathCount: 1100, requestGeneration: 3 })) {
    assert.equal(identity.currentNesteggCalculation({ ...envelope, identity: { ...envelope.identity, [key]: value } }, source, policy, 2), null, key);
  }
  const inputs = { ...constants.DEFAULT_NESTEGG_INPUTS };
  const captured = identity.captureNesteggCalculationSource('opaque', inputs, 'base', 1);
  inputs.currentSavings += 7;
  assert.notEqual(captured.inputs.currentSavings, inputs.currentSavings);
  assert.ok(Object.isFrozen(captured.inputs));
});

test('X → Y immediately removes every old result consumer during the 800ms debounce', async () => {
  const h = harness(); await h.flush(); await h.clickFull(); await h.flush();
  assert.equal(h.component('NesteggExportMenu').monteCarlo.paths, 1100);
  h.component('NesteggQuickWhatIf').onPatch({ currentSavings: 77 }); await h.flush();
  assertNoStaleConsumers(h); assert.equal(h.component('NesteggExportMenu').inputs.currentSavings, 77);
  h.advance(799); await h.flush(); assertNoStaleConsumers(h);
  h.advance(1); await h.flush(); assert.equal(h.component('NesteggExportMenu').monteCarlo.mark, 77);
  assert.equal(h.component('NesteggComparisonTable'), undefined); h.dispose();
});

test('X → Y → X does not resurrect retained X results or full analysis', async () => {
  const h = harness(); await h.flush(); await h.clickFull(); await h.flush();
  const x = h.component('NesteggExportMenu').inputs.currentSavings;
  h.component('NesteggQuickWhatIf').onPatch({ currentSavings: 11 }); await h.flush();
  h.component('NesteggQuickWhatIf').onPatch({ currentSavings: x }); await h.flush();
  assertNoStaleConsumers(h); h.advance(800); await h.flush();
  assert.equal(h.component('NesteggExportMenu').monteCarlo.paths, 200); h.dispose();
});

test('old light completion cannot publish after an edit even before the new effect', async () => {
  const calls = [], h = harness({ mcController: call => { const gate = deferred(); calls.push({ ...call, gate }); return gate.promise; } });
  await h.flush(); assert.equal(calls.length, 1);
  h.component('NesteggQuickWhatIf').onPatch({ currentSavings: 44 });
  calls[0].gate.resolve(mc(800456)); await h.flush(); assertNoStaleConsumers(h);
  h.advance(800); await h.flush(); calls[1].gate.resolve(mc(44)); await h.flush();
  assert.equal(h.component('NesteggExportMenu').monteCarlo.mark, 44); h.dispose();
});

test('a current quick-simulation failure is unavailable rather than indefinitely preparing', async () => {
  const h = harness({ mcController: () => Promise.reject(new Error('synthetic')) }); await h.flush();
  assert.match(h.text(), /Quick simulation is unavailable/);
  assert.equal(h.components('NesteggProbabilityCards').length, 0);
  assert.equal(h.component('NesteggSavedCompare').workspaceSimulationStatus, 'unavailable');
  assert.equal(h.component('NesteggExportMenu').monteCarlo, null); h.dispose();
});

test('full main/comparison/conservative results publish only as one complete captured-input bundle', async () => {
  const comparison = deferred(), conservative = deferred();
  const h = harness({ comparisonController: call => { assert.equal(call.inputs.currentSavings, 800456); return comparison.promise; },
    mcController: call => call.args.paths === 320 ? conservative.promise : Promise.resolve(mc(call.inputs.currentSavings, call.args.paths)) });
  await h.flush(); const pending = h.clickFull(); await h.flush();
  assert.equal(h.component('NesteggExportMenu').monteCarlo.paths, 200); assert.equal(h.component('NesteggComparisonTable'), undefined);
  comparison.resolve([{ scenarioId: 'base', label: 'captured', successRate: 0.5 }]); await h.flush();
  assert.equal(h.component('NesteggComparisonTable'), undefined);
  conservative.resolve(mc(800456, 320)); await pending; await h.flush();
  assert.equal(h.component('NesteggExportMenu').monteCarlo.paths, 1100);
  assert.equal(h.component('NesteggComparisonTable').rows[0].label, 'captured'); h.dispose();
});

for (const failureStage of ['comparison', 'conservative']) test(`a ${failureStage} failure cannot leave partially published full results or a stuck running state`, async () => {
  const h = harness({ comparisonController: () => failureStage === 'comparison' ? Promise.reject(new Error('synthetic')) : Promise.resolve([]),
    mcController: call => failureStage === 'conservative' && call.args.paths === 320 ? Promise.reject(new Error('synthetic')) : Promise.resolve(mc(call.inputs.currentSavings, call.args.paths)) });
  await h.flush(); await h.clickFull(); await h.flush();
  assert.equal(h.component('NesteggExportMenu').monteCarlo.paths, 200); assert.equal(h.component('NesteggComparisonTable'), undefined);
  assert.match(h.text(), /Analysis unavailable/); assert.doesNotMatch(h.text(), /Running…/); h.dispose();
});

test('identical-input overlapping full runs reject old progress, result, error and completion', async () => {
  const calls = [], h = harness({ mcController: call => {
    if (call.args.paths !== 1100) return Promise.resolve(mc(call.inputs.currentSavings, call.args.paths));
    const gate = deferred(); calls.push({ ...call, gate }); return gate.promise;
  } });
  await h.flush(); const old = h.clickFull(), newest = h.clickFull(); await h.flush();
  calls[0].args.onProgress(0.99); await h.flush();
  calls[1].gate.resolve(mc(2, 1100)); await newest; await h.flush();
  calls[0].gate.resolve(mc(1, 1100)); await old; await h.flush();
  calls[1].args.onProgress(0.2); await h.flush(); assert.doesNotMatch(h.text(), /Running…/);
  assert.equal(h.component('NesteggExportMenu').monteCarlo.mark, 2); assert.equal(h.toasts.length, 0); h.dispose();
});

test('edited input retires full progress and failure while allowing a new full request immediately', async () => {
  const calls = [], h = harness({ mcController: call => {
    if (call.args.paths !== 1100) return Promise.resolve(mc(call.inputs.currentSavings, call.args.paths));
    const gate = deferred(); calls.push({ ...call, gate }); return gate.promise;
  } });
  await h.flush(); const old = h.clickFull(); await h.flush();
  h.component('NesteggQuickWhatIf').onPatch({ currentSavings: 97 }); await h.flush(); assertNoStaleConsumers(h);
  calls[0].args.onProgress(1); calls[0].gate.resolve(mc(800456, 1100)); await old; await h.flush();
  assert.doesNotMatch(h.text(), /Running…/); assertNoStaleConsumers(h);
  const newest = h.clickFull(); await h.flush(); calls[1].gate.resolve(mc(97, 1100)); await newest; await h.flush();
  assert.equal(h.component('NesteggExportMenu').monteCarlo.mark, 97); h.dispose();
});

test('a rejected superseded full run cannot show an error or clear the newer running state', async () => {
  const calls = [], h = harness({ mcController: call => {
    if (call.args.paths !== 1100) return Promise.resolve(mc(call.inputs.currentSavings, call.args.paths));
    const gate = deferred(); calls.push({ ...call, gate }); return gate.promise;
  } });
  await h.flush(); const old = h.clickFull(), newest = h.clickFull(); await h.flush();
  calls[0].gate.resolve(Promise.reject(new Error('retired failure'))); await old; await h.flush();
  assert.match(h.text(), /Running…/); assert.doesNotMatch(h.text(), /Analysis unavailable/); assert.equal(h.toasts.length, 0);
  calls[1].gate.resolve(mc(9, 1100)); await newest; await h.flush();
  assert.equal(h.component('NesteggExportMenu').monteCarlo.mark, 9); h.dispose();
});

test('two refreshes publish only the latest list and old completion cannot clear its pending state', async () => {
  const first = deferred(), second = deferred();
  const h = harness({ planRead: (scope, number) => number === 1 ? [row(A, 1)] : number === 2 ? first.promise : second.promise });
  await h.flush(); const refresh = h.component('NesteggSavedPlanTabsToolbar').onRefreshCloud;
  const old = refresh(), current = refresh(); await h.flush();
  first.resolve([row(A, 111)]); await old; await h.flush();
  assert.equal(h.component('NesteggSavedPlanTabsToolbar').cloudRefreshing, true);
  second.resolve([row(A, 222)]); await current; await h.flush();
  assert.equal(h.component('NesteggSavedPlanTabsToolbar').cloudScenarios[0].inputs.currentSavings, 222);
  assert.equal(h.component('NesteggSavedPlanTabsToolbar').cloudRefreshing, false); h.dispose();
});

test('save A → select B does not replace B inputs, label, selection or dirty baseline', async () => {
  const gate = deferred(), h = harness({ saveGate: gate }); await h.flush();
  const b = { ...row(A, 123), id: 'plan-b', name: 'Plan B' };
  h.component('NesteggSavedPlanTabsToolbar').cloudScenarios.push(b);
  const saved = h.component('NesteggSavedPlanTabsToolbar').onSaveActivePlan();
  h.component('NesteggSavedPlanTabsToolbar').onLoadScenario(b); await h.flush();
  gate.resolve(); await saved; await h.flush();
  const toolbar = h.component('NesteggSavedPlanTabsToolbar');
  assert.equal(toolbar.activeSavedScenarioId, b.id); assert.equal(toolbar.inputs.currentSavings, 123);
  assert.equal(toolbar.activePlanLabelPreview, 'Plan B'); assert.equal(toolbar.dirtyActivePlan, false);
  assert.equal(toolbar.savingActivePlan, false); assert.equal(h.toasts.length, 0); h.dispose();
});

test('save then input/name edits retains newer edits and cannot mark them clean', async () => {
  const gate = deferred(), h = harness({ saveGate: gate }); await h.flush();
  const saved = h.component('NesteggSavedPlanTabsToolbar').onSaveActivePlan();
  h.component('NesteggQuickWhatIf').onPatch({ currentSavings: 88 });
  h.input('scenario-label').onChange({ target: { value: 'New unsaved label' } }); await h.flush();
  gate.resolve(); await saved; await h.flush();
  const toolbar = h.component('NesteggSavedPlanTabsToolbar');
  assert.equal(toolbar.inputs.currentSavings, 88); assert.equal(toolbar.activePlanLabelPreview, 'New unsaved label');
  assert.equal(toolbar.dirtyActivePlan, true); assert.equal(toolbar.savingActivePlan, false); h.dispose();
});

test('metadata-only rename preserves unsaved financial inputs and their dirty baseline', async () => {
  const h = harness(); await h.flush(); h.component('NesteggQuickWhatIf').onPatch({ currentSavings: 66 }); await h.flush();
  const toolbar = h.component('NesteggSavedPlanTabsToolbar'), request = toolbar.captureWorkspaceIntent();
  toolbar.onCloudRenamed({ ...row(A, 500123), name: 'Renamed' }, request); await h.flush();
  const current = h.component('NesteggSavedPlanTabsToolbar');
  assert.equal(current.inputs.currentSavings, 66); assert.equal(current.activePlanLabelPreview, 'Renamed');
  assert.equal(current.dirtyActivePlan, true); h.dispose();
});

test('CSV and print explicitly label exports without a current Monte Carlo result', () => {
  let html = '';
  const report = transpile('src/lib/nestegg/export-report.ts', {
    '@/lib/formatters': { formatCurrency: String }, './constants': constants,
  }, { window: { open: () => ({ document: { write: value => { html = value; }, close() {} } }) } });
  const deterministic = { nestEggAtRetirement: 44, readinessScore: 50, readiness: 'Strong', depletionAge: null };
  const csv = report.buildNesteggScenarioCsv(constants.DEFAULT_NESTEGG_INPUTS, 'base', deterministic, null);
  assert.match(csv, /Deterministic only - current simulation unavailable/); assert.doesNotMatch(csv, /Monte Carlo summary/);
  report.openNesteggPrintReport({ title: 'Test', inputs: constants.DEFAULT_NESTEGG_INPUTS, marketScenario: 'base', deterministic, mc: null });
  assert.match(html, /Deterministic only/); assert.doesNotMatch(html, /Chance of success/);
  const analysis = { modelVersion: 'monthly-v1', seedPolicy: 'fnv-mulberry-v1', purpose: 'light', pathCount: 200 };
  assert.match(report.buildNesteggScenarioCsv(constants.DEFAULT_NESTEGG_INPUTS, 'base', deterministic, mc(44), analysis), /Model version,monthly-v1\nSeed policy,fnv-mulberry-v1/);
});

function savedCompareHarness() {
  const calls = [], scope = createNesteggWorkspaceScope(A, 'test-session'); scope.activate();
  const x = { ...row(A, 10), id: 'saved-x', name: 'X' }, y = { ...row(A, 20), id: 'saved-y', name: 'Y' };
  const props = { workspaceKey: 'opaque', workspaceScope: scope, workspaceInputs: constants.DEFAULT_NESTEGG_INPUTS,
    workspaceMarketScenario: 'base', cloudScenarios: [x, y], activeSavedId: null, workspaceMonteCarlo: null };
  const h = componentHarness('src/components/nestegg/NesteggSavedCompare.tsx', 'NesteggSavedCompare', props, {
    '@/lib/nestegg/result-identity': identity, '@/lib/nestegg/constants': constants,
    '@/lib/nestegg/monte-carlo': { NESTEGG_MC_MODEL_VERSION: 'v1', NESTEGG_MC_SEED_POLICY: 'seed', runMonteCarloBatched: (inputs, scenario) => {
      const gate = deferred(); calls.push({ inputs, scenario, gate }); return gate.promise;
    } }, '@/lib/nestegg/plan-diff': { buildPlanDiff: () => [] }, '@/lib/formatters': { formatCurrency: String }, '@/lib/utils': { cn: () => '' },
  });
  const select = id => { h.find(n => n.type === 'Select').onValueChange(id); h.render(); };
  return { ...h, calls, scope, x, y, select };
}

test('saved comparison hides the previous row immediately and discards its late result', async () => {
  const h = savedCompareHarness(); h.select('saved-x'); await h.flush();
  h.calls[0].gate.resolve(mc(10)); await h.flush(); assert.match(h.text(), /Nest egg \(median\)/);
  h.select('saved-y'); assert.doesNotMatch(h.text(), /Success 50%/);
  h.calls[1].gate.resolve({ ...mc(20), medianNestEggAtRetirement: 20 }); await h.flush();
  assert.match(h.text(), /20/); h.dispose();
});

test('saved row refresh, failure, retry and retired session cannot leave stale data or indefinite loading', async () => {
  const h = savedCompareHarness(); h.select('saved-x'); await h.flush();
  h.update({ cloudScenarios: [{ ...h.x, updatedAt: 'new', inputs: { ...h.x.inputs, currentSavings: 33 } }, h.y] }); await h.flush();
  h.calls[0].gate.resolve(mc(10)); await h.flush(); assert.doesNotMatch(h.text(), /Success 50%/);
  h.calls[1].gate.resolve(Promise.reject(new Error('synthetic'))); await h.flush();
  assert.match(h.text(), /Comparison unavailable/); assert.doesNotMatch(h.text(), /Running comparison/);
  h.find(n => n.type === 'Button' && n.props.children === 'Retry comparison').onClick(); h.render(); await h.flush(); assert.equal(h.calls.length, 3);
  h.scope.dispose(); h.calls[2].gate.resolve(mc(33)); await h.flush(); assert.doesNotMatch(h.text(), /Success 50%/); h.dispose();
});

function toolbarHarness() {
  const calls = [], notifications = [], scope = createNesteggWorkspaceScope(A, 'session'), intents = identity.createNesteggPublicationClock();
  scope.activate();
  const saved = row(A, 10);
  const props = { workspaceScope: scope, inputs: saved.inputs, marketScenario: 'base', cloudScenarios: [saved], activeSavedScenarioId: saved.id,
    captureWorkspaceIntent: () => { const intent = intents.next(); return { generation: intent.generation, isCurrent: () => scope.isCurrent() && intent.isCurrent() }; },
    onLoadScenario: value => calls.push({ kind: 'load', value }), onCloudSaved: value => calls.push({ kind: 'published-new', value }),
    onCloudRenamed: value => calls.push({ kind: 'published-rename', value }), onRefreshCloud: async () => calls.push({ kind: 'refresh' }),
    onCloudScenarioDeleted: async () => calls.push({ kind: 'published-delete' }) };
  const operation = (kind, value) => {
    const gate = deferred(); calls.push({ kind, value, gate }); return gate.promise;
  };
  const h = componentHarness('src/components/nestegg/NesteggSavedPlanTabsToolbar.tsx', 'NesteggSavedPlanTabsToolbar', props, {
    '@/components/auth/AuthProvider': { useAuth: () => ({ user: { id: A }, loading: false }) },
    '@/lib/nestegg/result-identity': identity, '@/lib/utils': { cn: () => '' },
    sonner: { toast: Object.fromEntries(['success', 'error', 'message'].map(name => [name, (...args) => notifications.push({ name, args })])) },
    '@/lib/nestegg/scenarios-supabase': {
      insertNesteggScenarioToSupabase: (name, inputs, scenario) => operation('insert', { name, inputs, scenario }),
      updateNesteggScenarioNameInSupabase: (id, name) => operation('rename', { id, name }),
      deleteNesteggScenarioFromSupabase: id => operation('delete', { id }),
    },
  });
  const click = label => { h.find(n => n.type === 'Button' && [n.props.children].flat().some(c => c === label)).onClick(); h.render(); };
  const input = (id, value) => { h.find(n => n.props.id === id).onChange({ target: { value } }); h.render(); };
  const rename = () => { h.find(n => n.props['aria-label'] === `Rename ${saved.name}`).onClick(); h.render(); };
  return { ...h, calls, notifications, scope, saved, intents, click, input, rename };
}

test('save-new captures its inputs but cannot publish over a newer workspace selection', async () => {
  const h = toolbarHarness(); h.click('Duplicate'); h.input('nestegg-new-plan-name', 'Captured'); h.click('Create saved plan');
  const pending = h.calls[0]; assert.equal(pending.value.inputs.currentSavings, 10); assert.equal(pending.value.name, 'Captured');
  h.intents.invalidate(); h.update({ activeSavedScenarioId: 'new-plan', inputs: { ...h.saved.inputs, currentSavings: 88 } });
  pending.gate.resolve({ ...h.saved, name: 'Captured' }); await h.flush();
  assert.deepEqual(h.calls.map(c => c.kind), ['insert']); assert.equal(h.notifications.length, 0); h.dispose();
});

test('save-new replies cannot close or erase a newer dialog name', async () => {
  const h = toolbarHarness(); h.click('Duplicate'); h.input('nestegg-new-plan-name', 'Old'); h.click('Create saved plan');
  h.input('nestegg-new-plan-name', 'New unsaved name'); h.calls[0].gate.resolve(h.saved); await h.flush();
  assert.equal(h.find(n => n.props.id === 'nestegg-new-plan-name').value, 'New unsaved name');
  assert.deepEqual(h.calls.map(c => c.kind), ['insert']); assert.equal(h.notifications.length, 0); h.dispose();
});

test('late rename cannot replace a newer selection, edited name or financial inputs', async () => {
  const h = toolbarHarness(); h.rename(); h.input('rename-plan-inline', 'Old rename'); h.click('Apply name');
  h.input('rename-plan-inline', 'New unsaved rename'); h.calls[0].gate.resolve({ ...h.saved, name: 'Old rename' }); await h.flush();
  assert.equal(h.find(n => n.props.id === 'rename-plan-inline').value, 'New unsaved rename');
  assert.deepEqual(h.calls.map(c => c.kind), ['rename']); assert.equal(h.notifications.length, 0);
  h.click('Apply name'); h.intents.invalidate(); h.update({ activeSavedScenarioId: 'another' });
  h.calls[1].gate.resolve({ ...h.saved, name: 'New unsaved rename' }); await h.flush();
  assert.deepEqual(h.calls.map(c => c.kind), ['rename', 'rename']); assert.equal(h.notifications.length, 0); h.dispose();
});

test('current rename publishes metadata through its dedicated callback without loading stored inputs', async () => {
  const h = toolbarHarness(); h.rename(); h.input('rename-plan-inline', 'Current rename'); h.click('Apply name');
  h.calls[0].gate.resolve({ ...h.saved, name: 'Current rename' }); await h.flush();
  assert.deepEqual(h.calls.map(c => c.kind), ['rename', 'published-rename', 'refresh']);
  assert.equal(h.notifications[0].name, 'success'); h.dispose();
});

test('identical save-new overlapping requests publish only the newest reply', async () => {
  const h = toolbarHarness(); h.click('Duplicate'); h.input('nestegg-new-plan-name', 'Same');
  h.click('Create saved plan'); h.click('Create saved plan');
  h.calls[0].gate.resolve({ ...h.saved, id: 'old-new-plan' }); await h.flush();
  assert.deepEqual(h.calls.map(c => c.kind), ['insert', 'insert']);
  h.calls[1].gate.resolve({ ...h.saved, id: 'current-new-plan' }); await h.flush();
  assert.deepEqual(h.calls.map(c => c.kind), ['insert', 'insert', 'published-new', 'refresh']);
  assert.equal(h.calls[2].value.id, 'current-new-plan'); h.dispose();
});
