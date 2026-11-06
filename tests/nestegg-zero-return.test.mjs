import assert from 'node:assert/strict';
import test from 'node:test';
import { A, constants, transpile } from './helpers/nestegg-harness.mjs';
import { componentHarness } from './helpers/nestegg-component-harness.mjs';

const modules = {
  './retirement-cashflow': transpile('src/lib/nestegg/retirement-cashflow.ts', {}),
  './rmd': transpile('src/lib/nestegg/rmd.ts', {}),
};
const projections = transpile('src/lib/nestegg/projections.ts', modules);
const monteModules = { ...modules, './projections': projections, './constants': constants };
const monte = transpile('src/lib/nestegg/monte-carlo.ts', monteModules);
const controlled = transpile('src/lib/nestegg/monte-carlo.ts', monteModules, {
  // Hold only random shocks at zero so the modeled baseline remains observable.
  Math: Object.assign(Object.create(Math), { cos: () => 0 }),
  requestAnimationFrame: callback => setImmediate(callback),
});
const inputs = {
  ...constants.DEFAULT_NESTEGG_INPUTS,
  currentAge: 64, retirementAge: 65, lifeExpectancy: 66,
  currentSavings: 100_000, annualReturnPercent: 0,
};

const normalize = annualReturnPercent => constants.normalizeNesteggInputs({ annualReturnPercent }).annualReturnPercent;
const firstYear = p => projections.runProjection(p, { skipSuggestedExtra: true }).series[0].balance;

test('explicit numeric and legacy string zero survive draft save and hydration', () => {
  const values = new Map();
  const draft = transpile('src/lib/nestegg/storage.ts', { './constants': constants }, {
    window: { localStorage: { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) } },
  });
  for (const annualReturnPercent of [0, '0', ' 0.0 ']) {
    assert.equal(draft.saveNesteggDraft(A, { inputs: { ...inputs, annualReturnPercent },
      marketScenario: 'base', compareOverlay: false }), true);
    assert.equal(draft.loadNesteggDraft(A).draft.inputs.annualReturnPercent, 0);
  }
});

test('missing and malformed returns use the default, while finite legacy nonzero values survive', () => {
  for (const value of [undefined, null, '', '   ', 'invalid', NaN, Infinity, 'Infinity', false, true, {}, [], [1]]) {
    assert.equal(normalize(value), 7, String(value));
  }
  assert.equal(normalize(' 6.25 '), 6.25);
  assert.equal(normalize(-2), -2);
});

test('the deterministic base preserves an explicit zero for each risk profile', () => {
  for (const riskProfile of ['moderate', 'conservative', 'aggressive']) {
    const base = constants.applyScenarioToInputs({ ...inputs, riskProfile }, 'base');
    assert.equal(firstYear(base), 100_000, riskProfile);
  }
});

test('legacy nonzero growth, risk offsets and clamps retain the existing behavior', () => {
  for (const [riskProfile, firstYearBalance] of [['conservative', 106_500], ['moderate', 107_000], ['aggressive', 107_500]]) {
    assert.equal(firstYear({ ...inputs, annualReturnPercent: 7, riskProfile }), firstYearBalance);
  }
  assert.equal(firstYear({ ...inputs, annualReturnPercent: 0.25 }), 100_500);
  assert.equal(firstYear({ ...inputs, annualReturnPercent: 20 }), 115_000);
});

test('both Monte Carlo entry points preserve a zero baseline when random shocks are held at zero', async () => {
  const plan = { ...inputs, riskProfile: 'aggressive' };
  const options = { paths: 100, chunkSize: 25 };
  const results = [controlled.runMonteCarlo(plan, 'base', options),
    await controlled.runMonteCarloBatched(plan, 'base', options)];
  for (const result of results) {
    assert.equal(result.paths, 100);
    assert.equal(result.medianNestEggAtRetirement, 100_000);
    assert.equal(result.medianEndingBalance, 100_000);
  }
});

test('a zero baseline still allows real Monte Carlo volatility', () => {
  const result = monte.runMonteCarlo(inputs, 'base', { paths: 100 });
  assert.equal(monte.effectiveAnnualVolatilityPercent(inputs), 13);
  assert.ok(result.bandSeries[0].p10 < result.bandSeries[0].p90);
});

test('a lower-return preset cannot raise a low assumption; Aggressive remains a deliberate increase', () => {
  for (const annualReturnPercent of [0, 0.25, 0.75]) {
    const result = constants.applyScenarioToInputs({ ...inputs, annualReturnPercent }, 'conservative');
    assert.equal(result.annualReturnPercent, annualReturnPercent);
    assert.equal(result.inflationPercent, inputs.inflationPercent + 0.5);
  }
  assert.equal(constants.applyScenarioToInputs({ ...inputs, annualReturnPercent: 7 }, 'conservative').annualReturnPercent, 5);
  assert.equal(constants.applyScenarioToInputs(inputs, 'aggressive').annualReturnPercent, 2);
});

test('the two lower-return quick actions preserve zero', () => {
  const calls = [];
  const h = componentHarness('src/components/nestegg/NesteggQuickWhatIf.tsx', 'NesteggQuickWhatIf', {
    inputs, onPatch: patch => calls.push(patch),
  });
  for (const label of [/Returns down|Lower return/, /More conservative mix/]) {
    const action = h.find(node => node.type === 'Button' && label.test(node.props.children));
    action.onClick();
  }
  assert.deepEqual(calls.map(patch => patch.annualReturnPercent), [0, 0]);
  h.dispose();
});

test('active return controls admit zero without converting an empty advanced input into zero', () => {
  const changes = [];
  const quick = componentHarness('src/components/nestegg/NesteggQuickInputsPanel.tsx', 'NesteggQuickInputsPanel', {
    inputs, onChange: patch => changes.push(patch),
  });
  assert.equal(quick.find(node => node.props?.field?.id === 'qa-annualReturn').field.min, 0);
  const all = componentHarness('src/components/nestegg/NesteggAllInputsPanel.tsx', 'NesteggAllInputsPanel', {
    inputs, onChange: patch => changes.push(patch), scenario: 'base', compareOverlay: false,
  }, { '@/lib/nestegg/monte-carlo': monte, '@/lib/formatters': { formatPercent: String } });
  const field = all.find(node => node.props?.id === 'ai-annualReturn');
  assert.equal(field.min, 0);
  const change = (value, valueAsNumber) => field.onChange({ target: { value }, currentTarget: { value, valueAsNumber } });
  change('', NaN);
  assert.equal(changes.length, 0);
  change('0', 0);
  assert.deepEqual(changes.map(patch => patch.annualReturnPercent), [0]);
  quick.dispose();
  all.dispose();
});
