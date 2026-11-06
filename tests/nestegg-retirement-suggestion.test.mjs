import assert from 'node:assert/strict';
import test from 'node:test';
import { constants, transpile } from './helpers/nestegg-harness.mjs';
import { componentHarness } from './helpers/nestegg-component-harness.mjs';

const modules = {
  './retirement-cashflow': transpile('src/lib/nestegg/retirement-cashflow.ts', {}),
  './rmd': transpile('src/lib/nestegg/rmd.ts', {}),
};
const projections = transpile('src/lib/nestegg/projections.ts', modules);
const { runProjection } = projections;
// Suppress only the random shock, leaving the actual base return, cash flows,
// classification, and aggregation in both Monte Carlo entry points intact.
const noShockMath = Object.assign(Object.create(Math), { cos: () => 0 });
const { runMonteCarlo, runMonteCarloBatched } = transpile('src/lib/nestegg/monte-carlo.ts', {
  ...modules, './projections': projections, './constants': constants,
}, { Math: noShockMath, requestAnimationFrame: fn => setImmediate(fn) });

const base = {
  ...constants.DEFAULT_NESTEGG_INPUTS,
  currentAge: 64, retirementAge: 65, lifeExpectancy: 66,
  annualReturnPercent: 0.5, inflationPercent: 0, salaryGrowthPercent: 0,
  monthlyRetirementSpending: 120,
};

function survives(inputs, extra) {
  return runProjection({ ...inputs, monthlyContribution: inputs.monthlyContribution + extra }, {
    skipSuggestedExtra: true,
  }).lastsThroughLifeExpectancy;
}

function expectFirstFeasibleStep(inputs, step) {
  assert.equal(survives(inputs, step - 25), false, 'previous $25 step is insufficient');
  assert.equal(survives(inputs, step), true, 'suggested step meets the same modeled target');
  const result = runProjection(inputs);
  assert.equal(result.lastsThroughLifeExpectancy, false);
  assert.equal(result.suggestedExtraMonthly, step);
}

test('the retirement suggestion never rounds down to an insufficient $25 step', () => {
  expectFirstFeasibleStep(base, 125);
});

test('a small positive modeled saving need remains a positive suggestion', () => {
  expectFirstFeasibleStep({ ...base, monthlyRetirementSpending: 10 }, 25);
});

test('the existing $20,000 search cap is inclusive and no result is invented above it', () => {
  expectFirstFeasibleStep({ ...base, monthlyRetirementSpending: 20_090 }, 20_000);
  for (const spending of [21_910, 50_000]) {
    const infeasible = { ...base, monthlyRetirementSpending: spending };
    assert.equal(survives(infeasible, 20_000), false);
    assert.equal(runProjection(infeasible).suggestedExtraMonthly, null);
  }
});

test('already funded plans and plans with no remaining contributions do not suggest extra saving', () => {
  assert.equal(runProjection({ ...base, monthlyContribution: 125 }).suggestedExtraMonthly, null);
  const immediate = { ...base, retirementAge: 64 };
  assert.equal(survives(immediate, 20_000), false);
  assert.equal(runProjection(immediate).suggestedExtraMonthly, null);
});

const finalShortfall = { ...base, monthlyContribution: 110 };
const fullyFundedWithZero = { ...base, socialSecurityMonthly: 120 };

test('an unpaid final month is a deterministic failure and can trigger the existing savings solver', () => {
  const result = runProjection(finalShortfall, { skipSuggestedExtra: true });
  assert.equal(result.depletionAge, 66);
  assert.equal(result.series.at(-1).balance, 0);
  assert.equal(result.lastsThroughLifeExpectancy, false);
  assert.doesNotMatch(result.heroMessage, /on track|before your planned horizon/);
  expectFirstFeasibleStep(finalShortfall, 25);
});

test('a fully paid final month with exactly zero assets remains a success', () => {
  // No assets or contributions; income exactly funds every retirement bill.
  // The exact ending zero is not a rounded negative amount.
  const result = runProjection(fullyFundedWithZero);
  assert.equal(result.series.at(-1).age, 66);
  assert.equal(result.series.at(-1).balance, 0);
  assert.equal(result.depletionAge, null);
  assert.equal(result.lastsThroughLifeExpectancy, true);
  const mc = runMonteCarlo(fullyFundedWithZero, 'base', { paths: 100 });
  assert.equal(mc.successRate, 1);
  assert.equal(mc.medianEndingBalance, 0);
  assert.equal(mc.medianDepletionAgeAmongFailures, null);
});

test('both Monte Carlo entry points count a final-month shortfall as a failure', async () => {
  const options = { paths: 100, chunkSize: 25 };
  for (const result of [runMonteCarlo(finalShortfall, 'base', options),
    await runMonteCarloBatched(finalShortfall, 'base', options)]) {
    assert.equal(result.paths, 100);
    assert.equal(result.successRate, 0);
    assert.equal(result.chanceRunOut, 1);
    assert.equal(result.medianEndingBalance, 0);
    assert.equal(result.medianDepletionAgeAmongFailures, 66);
    assert.equal(result.worstCaseDepletionAge, 66);
  }
});

test('the longevity card describes funding coverage without confusing it with a positive balance', () => {
  const h = componentHarness('src/components/nestegg/NesteggSummaryCards.tsx', 'NesteggSummaryCards', {
    result: runProjection(fullyFundedWithZero), lifeExpectancy: 66, tier: 'primary',
  }, { '@/lib/formatters': { formatCurrency: n => `$${n}` }, '@/lib/utils': { cn: (...args) => args.join(' ') } });
  assert.match(h.text(), /No funding shortfall in this simulation/);
  assert.doesNotMatch(h.text(), /above zero/);
  h.update({ result: runProjection(finalShortfall, { skipSuggestedExtra: true }) });
  assert.match(h.text(), /Funding falls short during the modeled period/);
  assert.doesNotMatch(h.text(), /Through age 66|before your horizon/);
  h.dispose();
});
