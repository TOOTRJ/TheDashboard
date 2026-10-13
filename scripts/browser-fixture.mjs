#!/usr/bin/env node
// A fresh real Next/React app with synthetic loopback-only Auth/data.
import { spawn } from 'node:child_process';
import net from 'node:net';
import { readFile, writeFile, realpath, lstat, mkdir, copyFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';
import { prepareBuild, buildEnvironment, removeBuild } from './check-build.mjs';
import { createBrowserBackend, FIXTURE_KEY, FIXTURE_ADMIN_KEY } from './browser-fixtures/backend.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
function defaultInputs() {
  const source = ts.transpileModule(
    // This admitted public module has only a type import; no private I/O.
    // Its exact current defaults avoid a second drifting fixture model.
    vmInput, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const exports = {};
  vm.runInNewContext(source, { exports }, { timeout: 1000 });
  return JSON.parse(JSON.stringify(exports.DEFAULT_NESTEGG_INPUTS));
}
let vmInput;
let preparationPhase = 'input validation';

export async function availablePort() {
  const probe = net.createServer();
  await new Promise((resolve, reject) => { probe.once('error', reject); probe.listen(0, '127.0.0.1', resolve); });
  const port = probe.address().port;
  await new Promise(resolve => probe.close(resolve)); return port;
}
const runningChildren = new Set();
const termination = new WeakMap();
function ownedGroupExists(handle) {
  if (!handle?.pid) return false;
  try { process.kill(-handle.pid, 0); return true; }
  catch (error) { if (error.code === 'ESRCH') return false; throw new Error('Cannot inspect exact owned process group'); }
}
async function waitForOwnedGroup(handle, milliseconds) {
  const end = Date.now() + milliseconds;
  while (ownedGroupExists(handle) && Date.now() < end) await new Promise(resolve => setTimeout(resolve, 25));
  return !ownedGroupExists(handle);
}
async function terminateOwned(processHandle) {
  if (termination.has(processHandle)) return termination.get(processHandle);
  const completion = (async () => {
    // The leader can exit while an stdio:ignore descendant remains. Keep the
    // exact PGID until it disappears; never enumerate or signal other groups.
    if (ownedGroupExists(processHandle)) {
      try { process.kill(-processHandle.pid, 'SIGTERM'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
      if (!await waitForOwnedGroup(processHandle, 10_000)) {
        try { process.kill(-processHandle.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
        if (!await waitForOwnedGroup(processHandle, 1000)) throw new Error('Owned process group cleanup did not complete');
      }
    }
    runningChildren.delete(processHandle);
  })();
  termination.set(processHandle, completion); return completion;
}
export function runFixtureChild(command, args, options, timeout) {
  return new Promise((resolve, reject) => {
    const ownedChild = spawn(command, args, { ...options, shell: false, detached: true });
    runningChildren.add(ownedChild);
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      void terminateOwned(ownedChild).then(() => reject(new Error('Owned fixture preparation timed out')), reject);
    }, timeout);
    ownedChild.once('error', () => { clearTimeout(timer); runningChildren.delete(ownedChild); reject(new Error('Owned fixture preparation failed')); });
    ownedChild.once('close', async code => {
      clearTimeout(timer);
      if (!timedOut) {
        try {
          await terminateOwned(ownedChild);
          if (code === 0) resolve();
          else reject(new Error('Owned fixture preparation failed'));
        } catch (error) { reject(error); }
      }
    });
  });
}
export function browserEnvironment(directory, backendOrigin, inherited) {
  const url = new URL(backendOrigin);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.origin !== backendOrigin) throw new Error('Backend must be exact loopback origin');
  return { ...buildEnvironment(directory, inherited), NODE_ENV: 'production',
    NEXT_PUBLIC_SUPABASE_URL: backendOrigin,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: FIXTURE_KEY,
    SUPABASE_SERVICE_ROLE_KEY: FIXTURE_ADMIN_KEY,
    NEXT_PUBLIC_VN_API_URL: backendOrigin, NEXT_PUBLIC_VN_WS_URL: backendOrigin.replace('http:', 'ws:') + '/ws',
    // Production refuses insecure worker endpoints; no fallback localhost worker.
    NEXT_PUBLIC_VN_SERVICE_MODE: 'browser-fixture-legacy',
    API_SECRET_KEY: 'dashboard-browser-fixture-api-key',
  };
}

async function main() {
  if (process.argv.length !== 2) throw new Error('This fixture accepts no environment/source/target arguments');
  const prepared = await prepareBuild(ROOT);
  preparationPhase = 'owned copy canonicalization';
  prepared.directory = await realpath(prepared.directory);
  let backend, next, stopping;
  const stop = () => stopping ??= (async () => {
    await Promise.all([...runningChildren].map(terminateOwned));
    await backend?.stop(); await removeBuild(prepared);
  })();
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { void stop(); });
  try {
    preparationPhase = 'public input defaults';
    vmInput = await readFile(path.join(prepared.directory, 'src/lib/nestegg/constants.ts'), 'utf8');
    backend = createBrowserBackend(defaultInputs());
    preparationPhase = 'owned loopback binding';
    const backendOrigin = await backend.start(), port = await availablePort();
    // Cookies ignore ports. A unique .localhost host prevents sb-127 cookies
    // from colliding with another project's local app on this computer.
    const appOrigin = `http://dashboard-fixture-${prepared.owner}.localhost:${port}`;
    const bindOrigin = `http://127.0.0.1:${port}`;
    backend.setAppOrigin(appOrigin);
    preparationPhase = 'fake environment';
    const env = browserEnvironment(prepared.directory, backendOrigin);
    // Keep generated local artifacts and process output confined to the owned copy.
    // No .env, ssl, agent/cloud config, existing build or application credentials copy.
    preparationPhase = 'locked dependency installation';
    await runFixtureChild('npm', ['ci', '--include=dev', '--ignore-scripts', '--no-audit', '--no-fund'],
      { cwd: prepared.directory, env, stdio: 'inherit' }, 300_000);
    const nextBin = path.join(prepared.directory, 'node_modules/next/dist/bin/next');
    preparationPhase = 'public fixture route copy';
    if (!(await lstat(nextBin)).isFile() || await realpath(nextBin) !== nextBin) throw new Error('Next fixture executable must be regular owned source');
    // A restrictive test-only connect policy blocks the fixed hosted paper RPC
    // origin as well as all other cloud/worker origins. Real paper contract tests
    // use explicit component fixtures rather than weakening its project pin.
    const config = path.join(prepared.directory, 'next.config.ts');
    await writeFile(config, `import type { NextConfig } from 'next';\nconst config: NextConfig = { allowedDevOrigins: ['127.0.0.1'], async headers() { return [{source:'/:path*',headers:[{key:'Content-Security-Policy',value:${JSON.stringify("connect-src 'self' " + backendOrigin + ' ' + backendOrigin.replace('http:', 'ws:'))}}]}]; }}; export default config;\n`);
    const fixtures = [['paper-page.tsx', 'page.tsx'], ['paper-data.ts', 'paper-data.ts']];
    const route = path.join(prepared.directory, 'src/app/(dashboard)/paper-fixture');
    await mkdir(route, { recursive: true, mode: 0o700 });
    for (const [source, destination] of fixtures) {
      const file = path.join(ROOT, 'scripts/browser-fixtures', source);
      for (const segment of [path.join(ROOT, 'scripts'), path.dirname(file), file]) {
        const metadata = await lstat(segment);
        if (metadata.isSymbolicLink() || (segment === file && !metadata.isFile())) throw new Error('Browser fixture inputs must be regular public files');
      }
      await copyFile(file, path.join(route, destination));
    }
    preparationPhase = 'production fixture build';
    await runFixtureChild(process.execPath, [nextBin, 'build'],
      { cwd: prepared.directory, env, stdio: 'inherit' }, 600_000);
    preparationPhase = 'owned Next server readiness';
    next = spawn(process.execPath, [nextBin, 'start', '--hostname', '127.0.0.1', '--port', String(port)],
      { cwd: prepared.directory, env, stdio: 'inherit', shell: false, detached: true });
    runningChildren.add(next);
    next.once('error', () => { process.stderr.write('Owned Next fixture failed\n'); void stop(); });
    const deadline = Date.now() + 30_000;
    let readyResponse = false;
    while (Date.now() < deadline && next.exitCode === null && next.signalCode === null) {
      try {
        const response = await fetch(bindOrigin + '/login', { redirect: 'error',
          headers: { Host: new URL(appOrigin).host }, signal: AbortSignal.timeout(1000) });
        readyResponse = response.status === 200 && (await response.text()).includes('SYSTEM');
      } catch { /* The owned server may still be binding its selected port. */ }
      if (readyResponse) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (!readyResponse) throw new Error('Owned Next fixture readiness failed');
    const ready = { scope: 'synthetic-loopback-browser', appOrigin, backendOrigin,
      directory: prepared.directory, owner: prepared.owner, originalConfigReplacedOnlyInOwnedCopy: true,
      snapshotFiles: prepared.counts.files, snapshotBytes: prepared.counts.bytes,
      copiedPublicFixtureRoute: '/paper-fixture', isolatedCookieHostname: true,
      parentPid: process.pid, nextProcessGroup: next.pid,
      credentials: 'fake only; no cloud authority' };
    process.stdout.write(JSON.stringify(ready) + '\n');
    await new Promise(resolve => next.once('exit', resolve));
  } finally { await stop(); }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => { process.stderr.write(`Dashboard browser fixture failed during ${preparationPhase}; private inherited output is not used\n`); process.exitCode = 1; });
}
