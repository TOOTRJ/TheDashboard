#!/usr/bin/env node
// Build only a fresh allowlisted copy with deliberately fake public configuration.
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { lstat, mkdir, mkdtemp, readFile, realpath, rm, writeFile, copyFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MARKER = ".dashboard-ci-build-owner";
const FILES = ["package.json", "package-lock.json", "tsconfig.json", "next.config.ts",
  "postcss.config.mjs", "eslint.config.mjs", "components.json"];
const DIRECTORIES = ["src", "public"];
const FORBIDDEN = new Set(["node_modules", ".next", ".git", ".vercel", ".claude",
  ".codex", ".aws", "ssl", "__pycache__"]);

function permittedName(name) {
  return !FORBIDDEN.has(name) && !name.startsWith(".env") && !name.endsWith(".pem");
}

function validateInput(name) {
  if (typeof name !== "string" || path.isAbsolute(name) || name.split("/").some(part => !part || part === "." || part === "..")) {
    throw new Error("Build input paths must be canonical repository-relative paths");
  }
  if (name.split("/").some(part => !permittedName(part))) throw new Error("Private or generated files cannot be reviewed build inputs");
  if (!FILES.includes(name) && !DIRECTORIES.some(directory => name.startsWith(`${directory}/`))) {
    throw new Error("Build input is outside the frontend allowlist");
  }
}

export function trackedInputs(root, inherited = process.env) {
  const env = Object.fromEntries(["PATH", "TMPDIR", "LANG", "LC_ALL"].filter(key => inherited[key]).map(key => [key, inherited[key]]));
  const result = spawnSync("git", ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
    "-c", "submodule.recurse=false", "-c", "maintenance.auto=false", "ls-files", "--cached", "-z", "--", ...FILES, ...DIRECTORIES],
  { cwd: root, env, encoding: "utf8", timeout: 10_000, shell: false });
  if (result.error || result.status !== 0) throw new Error("Cannot resolve tracked frontend inputs");
  return result.stdout.split("\0").filter(Boolean);
}

export async function prepareBuild(root = ROOT, temporaryRoot = os.tmpdir(), reviewedInputs) {
  root = await realpath(root);
  const inputs = [...new Set(reviewedInputs ?? trackedInputs(root))].sort();
  for (const name of inputs) validateInput(name);
  for (const required of ["package.json", "package-lock.json", "tsconfig.json"]) {
    if (!inputs.includes(required)) throw new Error("Required build inputs must be tracked or explicitly reviewed fixtures");
  }
  const owner = randomUUID();
  const directory = await mkdtemp(path.join(temporaryRoot, "dashboard-ci-build-"));
  await writeFile(path.join(directory, MARKER), owner, { mode: 0o600, flag: "wx" });
  const counts = { files: 0, bytes: 0 };
  const prepared = { directory, owner, counts };
  try {
    for (const name of inputs) {
      const parts = name.split("/");
      for (let index = 1; index <= parts.length; index++) {
        const metadata = await lstat(path.join(root, ...parts.slice(0, index)));
        if (metadata.isSymbolicLink()) throw new Error("Build inputs cannot contain symbolic links");
        if (index < parts.length && !metadata.isDirectory()) throw new Error("Build input ancestors must be directories");
        if (index === parts.length && !metadata.isFile()) throw new Error("Reviewed build inputs must be regular files");
      }
      const source = path.join(root, name), destination = path.join(directory, name);
      await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
      await copyFile(source, destination);
      counts.files += 1;
      counts.bytes += (await lstat(source)).size;
    }
    for (const name of ["empty-user-npmrc", "empty-global-npmrc"]) {
      await writeFile(path.join(directory, name), "", { mode: 0o600, flag: "wx" });
    }
    return prepared;
  } catch (error) {
    await removeBuild(prepared);
    throw error;
  }
}

export function buildEnvironment(directory, inherited = process.env) {
  const env = {};
  for (const key of ["PATH", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "SYSTEMROOT"]) {
    if (typeof inherited[key] === "string") env[key] = inherited[key];
  }
  Object.assign(env, {
    CI: "true", NODE_ENV: "production", NEXT_TELEMETRY_DISABLED: "1",
    DASHBOARD_OFFLINE_BUILD: "1",
    PYTHON_DOTENV_DISABLED: "1", NO_UPDATE_NOTIFIER: "1",
    NEXT_PUBLIC_SUPABASE_URL: "https://dashboard-ci.invalid",
    NEXT_PUBLIC_SUPABASE_ANON_KEY: "dashboard-ci-fake-public-key",
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_dashboard_ci_fake",
    SUPABASE_SERVICE_ROLE_KEY: "dashboard-ci-fake-secret-with-no-access",
    NPM_CONFIG_USERCONFIG: path.join(directory, "empty-user-npmrc"),
    NPM_CONFIG_GLOBALCONFIG: path.join(directory, "empty-global-npmrc"),
    NPM_CONFIG_CACHE: path.join(directory, "npm-cache"),
    NPM_CONFIG_MAXSOCKETS: "4",
    NPM_CONFIG_AUDIT: "false", NPM_CONFIG_FUND: "false",
  });
  return env;
}

export async function removeBuild(prepared) {
  const marker = await lstat(path.join(prepared.directory, MARKER));
  if (!marker.isFile() || marker.isSymbolicLink()
      || await readFile(path.join(prepared.directory, MARKER), "utf8") !== prepared.owner) {
    throw new Error("Refusing to remove a build directory without its exact ownership marker");
  }
  await rm(prepared.directory, { recursive: true });
}

export async function runBuild(prepared, execute = spawnSync) {
  const env = buildEnvironment(prepared.directory);
  for (const [label, command, args, timeout] of [
    ["clean locked install", "npm", ["ci", "--include=dev", "--ignore-scripts", "--no-audit", "--no-fund"], 300_000],
    ["isolated fake-configuration build", process.execPath,
      [path.join(prepared.directory, "node_modules/next/dist/bin/next"), "build"], 600_000],
  ]) {
    process.stdout.write(`Dashboard CI: ${label}\n`);
    const result = execute(command, args, { cwd: prepared.directory, env, timeout, stdio: "inherit", shell: false });
    if (result.error || result.signal || result.status !== 0) {
      throw new Error(`Dashboard CI ${label} failed`);
    }
  }
}

async function main() {
  if (process.argv.slice(2).some(arg => arg !== "--prepare-only")) {
    throw new Error("Supported option: --prepare-only");
  }
  const prepared = await prepareBuild();
  try {
    if (!process.argv.includes("--prepare-only")) await runBuild(prepared);
    process.stdout.write(`${JSON.stringify({ scope: "isolated-fake-configuration", ...prepared.counts })}\n`);
  } finally {
    await removeBuild(prepared);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => { process.stderr.write("Dashboard isolated build check failed\n"); process.exitCode = 1; });
}
