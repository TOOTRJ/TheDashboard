import assert from 'node:assert/strict';
import test from 'node:test';
import { constants, transpile } from './helpers/nestegg-harness.mjs';

const { runProjection, buildRetirementCashflowYears } = transpile('src/lib/nestegg/projections.ts', {
  './retirement-cashflow': transpile('src/lib/nestegg/retirement-cashflow.ts', {}),
  './rmd': transpile('src/lib/nestegg/rmd.ts', {}),
});

const base = {
  ...constants.DEFAULT_NESTEGG_INPUTS,
  currentAge: 64, retirementAge: 65, lifeExpectancy: 68,
  currentSavings: 100_000, annualReturnPercent: 0, inflationPercent: 0,
  monthlyRetirementSpending: 1_500, socialSecurityMonthly: 1_000,
};

const couple = {
  ...base,
  householdMode: 'couple', spouseCurrentAge: 60, spouseRetirementAge: 63,
  spouseLifeExpectancy: 66, spouseSocialSecurityMonthly: 1_000,
};

const project = inputs => runProjection(inputs, { skipSuggestedExtra: true });
const chart = (inputs, years) => Array.from(buildRetirementCashflowYears(inputs, years), row => ({ ...row }));

test('first-year card and chart omit a spouse benefit the projection has not started', () => {
  const result = project(couple);
  assert.equal(result.series.find(row => row.age === 66).balance, 94_000);
  assert.equal(result.monthlyGapOrSurplus, -500);
  assert.equal(result.heroTone, 'caution');
  assert.equal(result.readinessScore, 75);
  assert.deepEqual(chart(couple, 3), [
    { year: 'Yr 1', expenses: 18_000, income: 12_000 },
    { year: 'Yr 2', expenses: 18_000, income: 12_000 },
    { year: 'Yr 3', expenses: 18_000, income: 24_000 },
  ]);
});

test('a midyear benefit starts only after the spouse work cutoff', () => {
  // Primary stops at month 12. Spouse stops at month 18, so months 13–18
  // receive only primary income and months 19–24 receive both benefits.
  const inputs = { ...couple, spouseRetirementAge: 61.5 };
  const result = project(inputs);
  assert.equal(result.series.find(row => row.age === 66).balance, 100_000);
  assert.equal(result.monthlyGapOrSurplus, 0);
  assert.deepEqual(chart(inputs, 1), [{ year: 'Yr 1', expenses: 18_000, income: 18_000 }]);
});

test('the first-year aggregates follow the existing month of survivor transition', () => {
  // Retirement begins at month 13 and the existing survivor phase starts at
  // month 18. Five months use full spending and both benefits, then seven
  // use half spending and the larger benefit. Other income remains $100.
  const inputs = {
    ...couple, lifeExpectancy: 65.5,
    spouseRetirementAge: 60, spouseLifeExpectancy: 67, spouseSocialSecurityMonthly: 800,
    otherRetirementIncomeMonthly: 100, enableSurvivorModeling: true,
    survivorSpendingRatioPercent: 50,
  };
  const result = project(inputs);
  assert.equal(result.series.find(row => row.age === 66).balance, 104_450);
  assert.equal(result.monthlyGapOrSurplus, 4_450 / 12);
  assert.deepEqual(chart(inputs, 2), [
    { year: 'Yr 1', expenses: 12_750, income: 17_200 },
    { year: 'Yr 2', expenses: 9_000, income: 13_200 },
  ]);
});

test('immediate retirement starts in month one and uses existing year-two inflation', () => {
  const inputs = { ...base, retirementAge: 64, lifeExpectancy: 66, inflationPercent: 10 };
  const result = project(inputs);
  assert.equal(result.series[0].balance, 94_000);
  assert.equal(result.monthlyGapOrSurplus, -500);
  assert.deepEqual(chart(inputs, 1), [{ year: 'Yr 1', expenses: 18_000, income: 12_000 }]);
  assert.deepEqual(chart(inputs, 2), [
    { year: 'Yr 1', expenses: 18_000, income: 12_000 },
    { year: 'Yr 2', expenses: 19_800, income: 13_200 },
  ]);
});

test('partial and empty retirement windows do not invent additional chart months', () => {
  const partial = { ...base, lifeExpectancy: 65.5 };
  assert.equal(project(partial).monthlyGapOrSurplus, -500);
  assert.equal(project(partial).series.at(-1).balance, 97_000);
  assert.deepEqual(chart(partial, 15), [{ year: 'Yr 1 (6 mo)', expenses: 9_000, income: 6_000 }]);
  assert.deepEqual(chart({ ...base, lifeExpectancy: 65 }, 15), []);
  assert.deepEqual(chart(base, 0), []);
});

test('recurring chart totals exclude one-time flows that do change modeled balance', () => {
  const withOneTimeFlows = { ...base, oneTimeIncome: 12_000, oneTimeExpense: 2_000 };
  assert.equal(project(withOneTimeFlows).series.at(-1).balance - project(base).series.at(-1).balance, 10_000);
  assert.deepEqual(chart(withOneTimeFlows, 1), chart(base, 1));
  assert.equal(project(withOneTimeFlows).monthlyGapOrSurplus, project(base).monthlyGapOrSurplus);
});
