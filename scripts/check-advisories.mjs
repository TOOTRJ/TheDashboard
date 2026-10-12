import { readFileSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const own = (value, key) => Object.hasOwn(value, key);

// Evaluate the actual transitive advisory graph, rather than allowing package
// names or severities wholesale. Each inherited finding must reach only the
// exact reviewed leaf and remain on an unchanged, dev-only lockfile path.
export function assessAudit(report, lock, policy, { mode, now = new Date() }) {
  if (!["full", "production"].includes(mode) || !Number.isFinite(now.getTime())) {
    throw new Error("Invalid audit mode or clock");
  }
  if (!object(report) || report.error || report.auditReportVersion !== 2 ||
      !object(report.vulnerabilities) || !object(report.metadata?.vulnerabilities) ||
      !object(lock?.packages) || policy?.version !== 1 || !Array.isArray(policy.exceptions)) {
    throw new Error("Missing or invalid audit/lock/policy evidence");
  }
  const vulnerabilities = report.vulnerabilities;
  const entries = Object.entries(vulnerabilities);
  if (entries.length > 256) throw new Error("Advisory graph exceeds its node budget");
  const counts = report.metadata.vulnerabilities;
  if (counts.total !== entries.length ||
      ["info", "low", "moderate", "high", "critical"].some((level) =>
        !Number.isSafeInteger(counts[level]) || counts[level] < 0 ||
        counts[level] !== entries.filter(([, finding]) => finding?.severity === level).length)) {
    throw new Error("Audit counts do not match findings");
  }
  if (mode === "production" && entries.length) {
    throw new Error("Production dependencies contain an advisory");
  }

  let visits = 0;
  function leaves(name, ancestors = new Set()) {
    if (++visits > 4096 || ancestors.size >= 64) throw new Error("Advisory graph exceeds its work budget");
    if (ancestors.has(name) || !own(vulnerabilities, name)) throw new Error("Invalid advisory dependency graph");
    const finding = vulnerabilities[name];
    if (!object(finding) || finding.name !== name || !Array.isArray(finding.via) || !finding.via.length ||
        finding.via.length > 32 || !Array.isArray(finding.nodes) || !finding.nodes.length ||
        finding.nodes.length > 16 || typeof name !== "string" || name.length > 200) {
      throw new Error("Incomplete or oversized advisory finding");
    }
    const seen = new Set(ancestors).add(name);
    const edges = new Set();
    return finding.via.flatMap((via) => {
      const edge = typeof via === "string" ? `dependency:${via}` : `advisory:${via?.url}`;
      if (edges.has(edge)) throw new Error("Duplicate advisory dependency edge");
      edges.add(edge);
      if (typeof via === "string") return leaves(via, seen);
      if (!object(via) || typeof via.url !== "string" || via.url.length > 300 || via.name !== name ||
          (own(via, "dependency") && via.dependency !== name)) {
        throw new Error("Invalid advisory leaf");
      }
      return [{ leaf: via, path: [...seen] }];
    });
  }

  const allowed = new Set();
  for (const [name] of entries) {
    for (const { leaf, path: dependencyPath } of leaves(name)) {
      const matching = policy.exceptions.filter((exception) =>
        exception.advisory === leaf.url.split("/").at(-1) && exception.url === leaf.url &&
        exception.package === leaf.name && exception.severity === leaf.severity);
      if (matching.length !== 1) throw new Error(`Unreviewed advisory in ${name}`);
      const exception = matching[0];
      const expiry = /^\d{4}-\d{2}-\d{2}$/.test(exception.expires_on ?? "")
        ? Date.parse(`${exception.expires_on}T00:00:00Z`) : NaN;
      const review = Date.parse(`${exception.reviewed_on}T00:00:00Z`);
      if (exception.scope !== "development-only" || !Number.isFinite(expiry) ||
          !Number.isFinite(review) || review > now.getTime() || expiry <= now.getTime() ||
          new Date(expiry).toISOString().slice(0, 10) !== exception.expires_on ||
          new Date(review).toISOString().slice(0, 10) !== exception.reviewed_on ||
          expiry <= review || typeof exception.reason !== "string" || !exception.reason.trim() ||
          !object(exception.affected_packages) || exception.affected_packages[leaf.name] !== exception.version) {
        throw new Error(`Expired or invalid exception in ${name}`);
      }
      for (const dependency of dependencyPath) {
        const evidence = vulnerabilities[dependency];
        if (evidence.severity !== exception.severity || !own(exception.affected_packages, dependency)) {
          throw new Error(`Unreviewed severity or dependency path in ${name}`);
        }
        for (const node of evidence.nodes) {
          const entry = lock.packages[node];
          if (node !== `node_modules/${dependency}` || !entry || entry.dev !== true ||
              entry.version !== exception.affected_packages[dependency]) {
            throw new Error(`Changed or non-development dependency in ${name}`);
          }
        }
      }
      allowed.add(exception.advisory);
    }
  }
  return { mode, findings: entries.length, acceptedExceptions: [...allowed].sort(), productionClean: mode === "production" };
}

function run() {
  const directory = mkdtempSync(path.join(tmpdir(), "dashboard-advisory-check-"));
  try {
    const userConfig = path.join(directory, "user-empty");
    const globalConfig = path.join(directory, "global-empty");
    writeFileSync(userConfig, ""); writeFileSync(globalConfig, "");
    const env = Object.fromEntries(["PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT"].flatMap((key) =>
      process.env[key] ? [[key, process.env[key]]] : []));
    const lock = JSON.parse(readFileSync(path.join(root, "package-lock.json"), "utf8"));
    const policy = JSON.parse(readFileSync(path.join(root, "security/advisory-exceptions.json"), "utf8"));
    for (const mode of ["full", "production"]) {
      const result = spawnSync("npm", ["audit", "--json", "--ignore-scripts",
        "--registry=https://registry.npmjs.org", `--userconfig=${userConfig}`,
        `--globalconfig=${globalConfig}`, `--cache=${path.join(directory, "cache")}`,
        ...(mode === "production" ? ["--omit=dev"] : [])],
      { cwd: root, env, encoding: "utf8", timeout: 120_000, maxBuffer: 8 * 1024 * 1024, shell: false });
      if (result.error || result.signal || ![0, 1].includes(result.status)) {
        throw new Error("Public advisory scan failed; no successful result");
      }
      const report = JSON.parse(result.stdout);
      const assessment = assessAudit(report, lock, policy, { mode });
      if ((result.status === 0) !== (assessment.findings === 0)) throw new Error("Audit exit status does not match findings");
      console.log(JSON.stringify(assessment));
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { run(); } catch (error) {
    console.error(error instanceof Error ? error.message : "Advisory check failed");
    process.exitCode = 1;
  }
}
