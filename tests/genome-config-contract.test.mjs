import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";
import * as genes from "../src/lib/probes/gene-registry.ts";
import * as transport from "../src/lib/probes/transport.ts";

const source = fs.readFileSync(new URL("../src/lib/probes/colony-config.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText;
const exports = {};
vm.runInNewContext(compiled, { exports, require(name) {
  if (name === "./gene-registry") return genes;
  if (name === "./transport") return transport;
  throw new Error(`Unexpected import ${name}`);
} });

const cases = JSON.parse(fs.readFileSync(new URL("../services/vonneumann/tests/fixtures/genome-config-contract.json", import.meta.url), "utf8"));
test("browser configuration agrees with the worker on shared phenotype fixtures", () => {
  for (const fixture of cases) {
    const config = exports.buildDefaultStartConfig();
    config.colony_config = { ...config.colony_config, ...fixture.config };
    const issues = exports.validateStartConfig(config);
    assert.equal(issues.length === 0, fixture.accepted, `${fixture.name}: ${JSON.stringify(issues)}`);
  }
});

test("disabled defaults and fixed constraints explain infeasible user settings", () => {
  const config = exports.buildDefaultStartConfig();
  config.colony_config.enabled_genes = [];
  config.colony_config.gene_overrides = { ema_fast: { default: 20 }, ema_slow: { default: 10 } };
  assert.match(exports.validateStartConfig(config).find((issue) => issue.field === "ema_fast").message, /disabled defaults/);
});
