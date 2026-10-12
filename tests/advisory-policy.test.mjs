import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { assessAudit } from "../scripts/check-advisories.mjs";

const policy = JSON.parse(readFileSync(new URL("../security/advisory-exceptions.json", import.meta.url), "utf8"));
const now = new Date("2026-10-12T22:00:00Z");
function fixture() {
  const names = Object.keys(policy.exceptions[0].affected_packages);
  const vulnerabilities = Object.fromEntries(names.map((name) => [name, {
    name, severity: "high", nodes: [`node_modules/${name}`],
    via: name === "braces" ? [{ name, severity: "high", url: policy.exceptions[0].url }] : ["braces"],
  }]));
  const lock = { packages: Object.fromEntries(names.map((name) => [`node_modules/${name}`, {
    version: policy.exceptions[0].affected_packages[name], dev: true,
  }])) };
  return { report: { auditReportVersion: 2, vulnerabilities,
    metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: names.length, critical: 0, total: names.length } } },
  lock, policy: structuredClone(policy) };
}
function evaluate(value, options = {}) {
  return assessAudit(value.report, value.lock, value.policy, { mode: "full", now, ...options });
}

test("accepts only the exact reviewed development chain and requires clean production", () => {
  const value = fixture();
  assert.deepEqual(evaluate(value).acceptedExceptions, ["GHSA-vfj7-8cjw-p6xm"]);
  assert.throws(() => evaluate(value, { mode: "production" }), /Production/);
  value.report.vulnerabilities = {};
  value.report.metadata.vulnerabilities.high = value.report.metadata.vulnerabilities.total = 0;
  assert.equal(evaluate(value, { mode: "production" }).productionClean, true);
});

test("fails closed on additional advisories, changed versions, runtime paths and expiry", () => {
  for (const mutate of [
    (v) => { v.report.vulnerabilities.braces.via.push({ name: "braces", severity: "high", url: "https://github.com/advisories/GHSA-new-issue" }); },
    (v) => { v.lock.packages["node_modules/braces"].version = "3.0.4"; },
    (v) => { v.lock.packages["node_modules/braces"].dev = false; },
    (v) => { v.report.vulnerabilities.braces.nodes = ["node_modules/other/node_modules/braces"]; },
    (v) => { v.policy.exceptions[0].expires_on = "2026-10-12"; },
    (v) => { v.policy.exceptions[0].reviewed_on = "2026-10-13"; },
    (v) => { v.policy.exceptions[0].severity = "critical"; },
    (v) => { v.policy.exceptions.push(structuredClone(v.policy.exceptions[0])); },
  ]) { const value = fixture(); mutate(value); assert.throws(() => evaluate(value)); }
});

test("fails closed on scanner errors, incomplete counts, missing dependencies and graph cycles", () => {
  for (const mutate of [
    (v) => { v.report.error = { message: "registry unavailable" }; },
    (v) => { delete v.report.metadata; },
    (v) => { v.report.metadata.vulnerabilities.total = 0; },
    (v) => { v.report.vulnerabilities.braces.via = ["braces"]; },
    (v) => { v.report.vulnerabilities.braces.via = ["missing"]; },
    (v) => { v.report.vulnerabilities.braces.via = []; },
  ]) { const value = fixture(); mutate(value); assert.throws(() => evaluate(value)); }
});

test("a reviewed advisory cannot be attached directly to a different package", () => {
  const value = fixture();
  const parent = value.report.vulnerabilities["eslint-config-next"];
  parent.via = value.report.vulnerabilities.braces.via;
  value.report.vulnerabilities = { "eslint-config-next": parent };
  delete value.lock.packages["node_modules/braces"];
  value.report.metadata.vulnerabilities.high = value.report.metadata.vulnerabilities.total = 1;
  assert.throws(() => evaluate(value), /Invalid advisory leaf/);
});

test("duplicate paths and oversized graphs cannot amplify evaluator work", () => {
  for (const mutate of [
    (v) => { v.report.vulnerabilities["eslint-config-next"].via = ["braces", "braces"]; },
    (v) => { v.report.vulnerabilities.braces.via.push(structuredClone(v.report.vulnerabilities.braces.via[0])); },
    (v) => { v.report.vulnerabilities.braces.via = Array(33).fill("braces"); },
    (v) => { v.report.vulnerabilities.braces.nodes = Array(17).fill("node_modules/braces"); },
    (v) => { v.policy.exceptions[0].expires_on = "2026-02-30"; },
  ]) { const value = fixture(); mutate(value); assert.throws(() => evaluate(value)); }
});
