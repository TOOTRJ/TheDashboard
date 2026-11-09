import assert from 'node:assert/strict';
import test from 'node:test';
import { A, constants, harness, row, transpile } from './helpers/nestegg-harness.mjs';
import { componentHarness } from './helpers/nestegg-component-harness.mjs';

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


const zeroMonths = { ...base, lifeExpectancy: 65 };

test('the recorded first-year coverage follows actual modeled months, including a sub-month horizon', () => {
  const result = project(zeroMonths);
  assert.equal(result.firstYearRetirementMonths, 0);
  assert.equal(result.series.at(-1).age, 65);
  assert.equal(result.series.at(-1).balance, 100_000);
  assert.equal(result.series.at(-1).phase, 'accumulation');
  assert.equal(project({ ...base, lifeExpectancy: 65 + 1 / 24 }).firstYearRetirementMonths, 0);
  assert.equal(project({ ...base, lifeExpectancy: 65.5 }).firstYearRetirementMonths, 6);
  assert.equal(project(base).firstYearRetirementMonths, 12);
});

test('cash-flow displays distinguish an unmodeled retirement from modeled zero and partial years', () => {
  const formatCurrency = value => `$${value}`;
  const summary = componentHarness('src/components/nestegg/NesteggSummaryCards.tsx', 'NesteggSummaryCards', {
    result: project(zeroMonths), lifeExpectancy: 65,
  }, { '@/lib/formatters': { formatCurrency }, '@/lib/utils': { cn: (...classes) => classes.join(' ') } });
  assert.match(summary.text(), /Retirement cash flow \(year one\) Not available/);
  assert.match(summary.text(), /Plan readiness Not evaluated/);
  assert.doesNotMatch(summary.text(), /\$500|\/ 100|No funding shortfall/);
  summary.update({ result: project({ ...base, lifeExpectancy: 65.5 }), lifeExpectancy: 65.5 });
  assert.match(summary.text(), /\$500 \/ mo shortfall/);
  assert.match(summary.text(), /6 modeled retirement months/);
  summary.update({ result: project({ ...base, monthlyRetirementSpending: 1_000 }) });
  assert.match(summary.text(), /\$0 \/ mo surplus/);
  summary.dispose();

  const cashflow = componentHarness('src/components/nestegg/NesteggSecondaryChart.tsx', 'NesteggSecondaryChart', {
    data: chart(zeroMonths, 15),
  }, { '@/lib/formatters': { formatCurrency } });
  assert.match(cashflow.text(), /No retirement months are modeled/);
  assert.throws(() => cashflow.find(node => node.type === 'BarChart'));
  const data = chart({ ...base, lifeExpectancy: 65.5 }, 15);
  cashflow.update({ data });
  assert.doesNotMatch(cashflow.text(), /No retirement months are modeled/);
  assert.equal(cashflow.find(node => node.type === 'BarChart').data, data);
  cashflow.dispose();
});

test('a saved plan without retirement coverage suppresses workspace odds until a modeled month exists', async () => {
  const app = harness({
    planRead: () => [{ ...row(A, 100_000), inputs: zeroMonths }],
    projectionResult: project,
  });
  try {
    await app.flush();
    assert.equal(app.component('NesteggHeroInsight').message, 'No retirement months are modeled in this plan.');
    assert.match(app.text(), /Full retirement analysis requires at least one modeled retirement month/);
    assert.deepEqual(app.components('NesteggProbabilityCards'), []);
    assert.equal(app.mcCalls.length, 0);
    await app.clickFull();
    assert.equal(app.mcCalls.length, 0);

    app.component('NesteggQuickInputsPanel').onChange({ lifeExpectancy: 66 });
    await app.flush();
    assert.equal(app.mcCalls.length, 1);
    assert.equal(app.component('NesteggProbabilityCards').deterministic.firstYearRetirementMonths, 12);
    assert.equal(app.component('NesteggProbabilityCards').deterministic.monthlyGapOrSurplus, -500);
    assert.match(app.component('NesteggHeroInsight').message, /on track/);

    await app.clickFull();
    await app.flush();
    assert.equal(app.mcCalls.length, 3);
    app.component('NesteggQuickInputsPanel').onChange({ lifeExpectancy: 65 + 1 / 24 });
    await app.flush();
    app.advance(800);
    await app.flush();
    assert.equal(app.mcCalls.length, 3);
    assert.deepEqual(app.components('NesteggProbabilityCards'), []);
    assert.doesNotMatch(app.text(), /re-run for updated results/i);
  } finally {
    app.dispose();
  }
});
