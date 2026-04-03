import type { NesteggInputs, NesteggScenarioId } from "./types";
import type { MonteCarloResult } from "./monte-carlo";
import type { ProjectionResult } from "./types";
import { formatCurrency } from "@/lib/formatters";
import { SCENARIO_LABELS } from "./constants";

function csvEscape(s: string): string {
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function buildNesteggScenarioCsv(
  inputs: NesteggInputs,
  marketScenario: NesteggScenarioId,
  deterministic: ProjectionResult,
  mc: MonteCarloResult | null
): string {
  const lines: string[] = [];
  lines.push("Nestegg export", `Market preset,${SCENARIO_LABELS[marketScenario]}`);
  lines.push("");
  lines.push("Field,Value");
  const rows: [string, string][] = [
    ["Current age", String(inputs.currentAge)],
    ["Retirement age", String(inputs.retirementAge)],
    ["Life expectancy", String(inputs.lifeExpectancy)],
    ["Current savings", String(inputs.currentSavings)],
    ["Monthly contribution", String(inputs.monthlyContribution)],
    ["Annual return %", String(inputs.annualReturnPercent)],
    ["Monthly retirement spending", String(inputs.monthlyRetirementSpending)],
    ["Inflation %", String(inputs.inflationPercent)],
    ["Social Security (monthly)", String(inputs.socialSecurityMonthly)],
    ["Risk profile", inputs.riskProfile],
    ["Household", inputs.householdMode],
    ["MC volatility % (custom or auto)", inputs.monteCarloVolatilityPercent == null ? "auto" : String(inputs.monteCarloVolatilityPercent)],
    ["Survivor modeling", String(inputs.enableSurvivorModeling)],
    ["Survivor spending %", String(inputs.survivorSpendingRatioPercent)],
  ];
  for (const [k, v] of rows) {
    lines.push(`${csvEscape(k)},${csvEscape(v)}`);
  }
  lines.push("");
  lines.push("Deterministic summary");
  lines.push("Metric,Value");
  lines.push(`Nest egg at retirement,${deterministic.nestEggAtRetirement}`);
  lines.push(`Readiness score,${deterministic.readinessScore}`);
  lines.push(`Depletion age,${deterministic.depletionAge ?? ""}`);
  if (mc) {
    lines.push("");
    lines.push("Monte Carlo summary");
    lines.push("Metric,Value");
    lines.push(`Paths,${mc.paths}`);
    lines.push(`Success rate,${(mc.successRate * 100).toFixed(1)}%`);
    lines.push(`Median ending balance,${mc.medianEndingBalance}`);
  }
  return lines.join("\n");
}

export function downloadNesteggCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function openNesteggPrintReport(opts: {
  title: string;
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
  deterministic: ProjectionResult;
  mc: MonteCarloResult | null;
}): void {
  const { title, inputs, marketScenario, deterministic, mc } = opts;
  const w = window.open("", "_blank", "noopener,noreferrer");
  if (!w) return;

  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const mcBlock = mc
    ? `
    <section>
      <h2>Monte Carlo (${mc.paths} paths)</h2>
      <table>
        <tr><td>Chance of success</td><td>${(mc.successRate * 100).toFixed(1)}%</td></tr>
        <tr><td>Median nest egg at retirement</td><td>${formatCurrency(mc.medianNestEggAtRetirement)}</td></tr>
        <tr><td>Median ending balance</td><td>${formatCurrency(mc.medianEndingBalance)}</td></tr>
      </table>
    </section>`
    : "";

  w.document.write(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>${esc(title)}</title>
  <style>
    :root { font-family: system-ui, sans-serif; color: #111; }
    body { max-width: 720px; margin: 48px auto; padding: 0 24px; line-height: 1.5; }
    h1 { font-size: 1.35rem; letter-spacing: 0.04em; text-transform: uppercase; border-bottom: 1px solid #ccc; padding-bottom: 8px; }
    h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em; color: #444; margin-top: 28px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    td { padding: 6px 0; border-bottom: 1px solid #eee; }
    td:first-child { color: #555; width: 55%; }
    .muted { font-size: 0.75rem; color: #666; margin-top: 32px; }
    @media print { body { margin: 24px; } }
  </style>
</head>
<body>
  <h1>${esc(title)}</h1>
  <p class="muted">Educational planning only — not financial advice.</p>
  <section>
    <h2>Assumptions snapshot</h2>
    <table>
      <tr><td>Market preset</td><td>${esc(SCENARIO_LABELS[marketScenario])}</td></tr>
      <tr><td>Current age → retirement</td><td>${inputs.currentAge} → ${inputs.retirementAge}</td></tr>
      <tr><td>Monthly retirement spending</td><td>${formatCurrency(inputs.monthlyRetirementSpending)}</td></tr>
      <tr><td>Expected annual return</td><td>${inputs.annualReturnPercent}%</td></tr>
    </table>
  </section>
  <section>
    <h2>Deterministic projection</h2>
    <table>
      <tr><td>Nest egg at retirement</td><td>${formatCurrency(deterministic.nestEggAtRetirement)}</td></tr>
      <tr><td>Readiness</td><td>${esc(deterministic.readiness)} (${deterministic.readinessScore}/100)</td></tr>
    </table>
  </section>
  ${mcBlock}
  <p style="margin-top:28px"><button type="button" onclick="window.print()" style="padding:10px 18px;border-radius:8px;border:1px solid #ccc;background:#f8f8f8;cursor:pointer;font:inherit">Print or Save as PDF</button></p>
  <p class="muted">Generated from Nestegg · The Dashboard</p>
</body>
</html>`);
  w.document.close();
}
