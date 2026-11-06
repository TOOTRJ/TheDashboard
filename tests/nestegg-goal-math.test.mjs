import assert from 'node:assert/strict';
import test from 'node:test';
import { transpile, harness, mc } from './helpers/nestegg-harness.mjs';
import { componentHarness } from './helpers/nestegg-component-harness.mjs';
const fv = transpile('src/lib/nestegg/future-value.ts', {});
const base = { currentBalance: 0, goalAmount: 12_001, monthsToGoal: 12, annualReturnPercent: 0, annualEscalationPercent: 0 };
const project = (overrides = {}) => fv.buildGoalProjectionSeries({ ...base, currentMonthly: 1000, ...overrides });

test('zero-return saving rounds upward to a feasible $5 step without overshooting exact steps', () => {
  assert.equal(fv.computeRequiredMonthlySavings(base), 1005);
  assert.equal(fv.computeRequiredMonthlySavings({ ...base, goalAmount: 12_000 }), 1000);
  assert.ok(1005 * 12 >= base.goalAmount);
  assert.ok(1000 * 12 < base.goalAmount);
  const p = project();
  assert.equal(p.requiredMonthly, 1005);
  assert.equal(p.totalContributed, 12060);
  assert.equal(p.totalGrowth, 0);
  assert.equal(p.currentPathEndBalance, 12000);
});

test('annual contribution escalation begins after the first twelve month-end deposits', () => {
  const p = project({ goalAmount: 25_200, monthsToGoal: 24, annualEscalationPercent: 10 });
  assert.equal(p.requiredMonthly, 1000);
  assert.equal(p.totalContributed, 12 * 1000 + 12 * 1100);
  assert.equal(p.currentPathEndBalance, 25_200);
  assert.equal(p.totalGrowth, 0);
});

test('positive-return solution meets an independent annuity formula at the selected $5 step', () => {
  const annual = (1.01 ** 12 - 1) * 100;
  const req = fv.computeRequiredMonthlySavings({ ...base, goalAmount: 1000, annualReturnPercent: annual });
  const coefficient = (1.01 ** 12 - 1) / 0.01;
  assert.equal(req, 80);
  assert.ok(req * coefficient >= 1000);
  assert.ok((req - 5) * coefficient < 1000);
});

test('search-cap exhaustion is explicit in all goal-derived fields and sensitivity rows', () => {
  const p = project({ goalAmount: 1e12 });
  assert.equal(p.status, 'above-limit');
  for (const key of ['requiredMonthly', 'extraSavingsNeeded', 'totalContributed', 'totalGrowth']) assert.equal(p[key], null, key);
  assert.ok(p.series.length > 1);
  assert.ok(p.series.every(row => row.goalPath === null));
  assert.ok(p.timelineSensitivity.every(row => row.requiredMonthly === null));
  assert.ok(p.returnSensitivity.every(row => row.requiredMonthly === null));
  assert.equal(p.currentPathEndBalance, 12000);
  assert.equal(fv.computeRequiredMonthlySavings({ ...base, goalAmount: 2_400_000 }), 200_000);
  assert.equal(fv.computeRequiredMonthlySavings({ ...base, goalAmount: 2_400_001 }), -1);
});

test('growth alone can reach a goal with zero contributions, while zero return preserves cash', () => {
  const p = project({ currentBalance: 1000, goalAmount: 1100, annualReturnPercent: 10, currentMonthly: 0 });
  assert.equal(p.requiredMonthly, 0);
  assert.equal(p.yearsAtCurrentPace, 1);
  assert.equal(p.currentPathEndBalance, 1100);
  const cash = project({ currentBalance: 1000, goalAmount: 2000, currentMonthly: 0 });
  assert.equal(cash.currentPathEndBalance, 1000);
  assert.equal(cash.yearsAtCurrentPace, null);
});

test('a negative return remains an investment loss rather than clamped zero growth', () => {
  const p = project({ currentBalance: 1000, goalAmount: 1000, currentMonthly: 0, annualReturnPercent: -10 });
  assert.equal(p.currentPathEndBalance, 900);
  assert.ok(p.totalGrowth < 0);
  assert.ok(p.series.at(-1).goalPath >= 1000);
});

test('partial-year endpoints retain their elapsed-month location and zero-month goals are unavailable', () => {
  const p = project({ monthsToGoal: 6, goalAmount: 6000 });
  assert.equal(p.series.at(-1).year - p.series[0].year, 0.5);
  assert.equal(p.currentPathEndBalance, 6000);
  const past = project({ monthsToGoal: 0 });
  assert.equal(past.status, 'past-deadline');
  assert.equal(past.requiredMonthly, null);
});

test('invalid or unsupported numerical input cannot publish a fabricated savings plan', () => {
  for (const overrides of [{ currentBalance: NaN }, { goalAmount: Infinity }, { monthsToGoal: 1.5 }, { monthsToGoal: 1201 }, { annualReturnPercent: -100 }, { annualReturnPercent: Infinity }, { annualEscalationPercent: -101 }, { currentMonthly: -1 }, { inflationPercent: NaN }, { currentMonthly: 1e308 }, { currentBalance: 1e308, annualReturnPercent: 100 }, { inflationPercent: -99.999, monthsToGoal: 1200 }]) {
    const p = project(overrides);
    assert.equal(p.status, 'invalid-input', JSON.stringify(overrides));
    assert.equal(p.requiredMonthly, null);
    assert.deepEqual([...p.series], []);
  }
});

test('an unavailable goal renders no zero-savings, on-track or made-up probability claim', () => {
  const h = componentHarness('src/components/nestegg/NesteggGoalChart.tsx', 'NesteggGoalChart', {
    projection: project({ goalAmount: 1e12 }), goalAmount: 1e12, targetYear: new Date().getFullYear() + 1,
    currentMonthly: 1000, escalationPercent: 0, goalProbability: 0.95,
  }, { '@/lib/formatters': { formatCurrency: n => `$${n}` }, '@/lib/utils': { cn: (...args) => args.join(' ') } });
  assert.match(h.text(), /Above calculation limit/);
  assert.match(h.text(), /Unavailable/);
  assert.doesNotMatch(h.text(), /\$0\/mo|On track|Goal probability|95%/);
  h.dispose();
});

 test('retirement-age bands cannot be converted into an unrelated goal-date probability', async () => {
  const h = harness({ mcController: async () => ({ ...mc(1), bandSeries: [{ age: 90, p10: 1e12, p25: 1e12, p50: 1e12, p75: 1e12, p90: 1e12 }] }) });
  await h.flush();
  assert.equal(h.component('NesteggChartTabs').goalProbability, null);
  h.dispose();
});

test('above-limit progress uses the actual balance, while invalid goals publish no computed metrics', () => {
  const replacements = { '@/lib/formatters': { formatCurrency: n => `$${n}` }, '@/lib/utils': { cn: (...args) => args.join(' ') } };
  const props = { projection: project({ currentBalance: 10_000_000, goalAmount: 1e9 }), goalAmount: 1e9, targetYear: new Date().getFullYear() + 1, currentMonthly: 1000, escalationPercent: 0 };
  const h = componentHarness('src/components/nestegg/NesteggGoalChart.tsx', 'NesteggGoalChart', props, replacements);
  assert.match(h.text(), /1\s*% of goal/);
  assert.match(h.text(), /\$10000000\s*\/\s*\$1000000000/);
  assert.doesNotMatch(h.text(), /\$0\s*\/\s*\$1000000000/);
  h.update({ projection: project({ currentBalance: 1000, goalAmount: 12000, annualReturnPercent: -100 }) });
  assert.match(h.text(), /Check goal inputs/);
  assert.doesNotMatch(h.text(), /At current rate|Gap|today.s dollars|80 years|Required monthly/);
  h.dispose();
});
