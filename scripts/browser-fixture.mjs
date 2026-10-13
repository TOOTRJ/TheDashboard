#!/usr/bin/env node
// A fresh real Next/React app with synthetic loopback-only Auth/data.
import { spawn, spawnSync } from 'node:child_process';
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
export function createFixtureLaunchGuard() {
  let closing = false;
  return Object.freeze({
    close() { closing = true; },
    assertOpen() { if (closing) throw new Error('Owned fixture is closing'); },
    get closing() { return closing; },
  });
}
export function createFixtureOwnedSteps(guard) {
  const pending = new Set();
  return Object.freeze({
    run(action) {
      guard.assertOpen();
      // Register before scheduling the action: shutdown can neither miss an
      // already-owned write nor admit a new action after the closing boundary.
      const step = Promise.resolve().then(() => { guard.assertOpen(); return action(); });
      pending.add(step);
      void step.then(() => pending.delete(step), () => pending.delete(step));
      return step;
    },
    async drain() {
      if (!guard.closing) throw new Error('Owned fixture steps require a closed launch guard');
      await Promise.allSettled([...pending]);
    },
  });
}
const runningChildren = new Set();
const termination = new WeakMap();
function ownedGroupExists(handle) {
  if (!handle?.pid) return false;
  try { process.kill(-handle.pid, 0); return true; }
  catch (error) { if (error.code === 'ESRCH') return false; throw new Error('Cannot inspect exact owned process group'); }
}
export function parseOwnedGroupState(output, group) {
  if (!Number.isSafeInteger(group) || group <= 0 || group > 2_147_483_647
    || typeof output !== 'string' || output.length > 262_144) throw new Error('Cannot inspect exact owned process group');
  const rows = output.trim().split('\n').filter(Boolean);
  if (!rows.length) return true;
  if (rows.length > 4096) throw new Error('Cannot inspect exact owned process group');
  const seen = new Set();
  return rows.map(line => {
    const row = /^\s*([1-9][0-9]*)\s+([1-9][0-9]*)\s+([A-Za-z][A-Za-z+<>-]*)\s*$/.exec(line);
    const pid = row && Number(row[1]);
    if (!row || !Number.isSafeInteger(pid) || pid > 2_147_483_647
      || Number(row[2]) !== group || seen.has(pid)) throw new Error('Cannot inspect exact owned process group');
    seen.add(pid);
    if (row[3].startsWith('Z') && !/^Z[+<>AELNSsVWXl]*$/.test(row[3])) throw new Error('Cannot inspect exact owned process group');
    return row[3].startsWith('Z');
  }).every(Boolean);
}
export function ownedGroupIsQuiescent(handle, execute = spawnSync, platform = process.platform) {
  // A dead descendant can remain as an unreapable OS zombie. Query only the
  // exact group we created, never a global process inventory. macOS legacy ps
  // ignores -g, so the child environment explicitly selects unix2003 behavior.
  if (!Number.isSafeInteger(handle?.pid) || handle.pid <= 0 || handle.pid > 2_147_483_647) {
    throw new Error('Cannot inspect exact owned process group');
  }
  const env = { COMMAND_MODE: 'unix2003', LC_ALL: 'C' };
  let selection, selectedIds;
  const linuxMembers = () => {
    const members = execute('/usr/bin/pgrep', ['-g', String(handle.pid)], { env, encoding: 'utf8', timeout: 1000, maxBuffer: 262_144 });
    if (!members.error && members.status === 1 && members.stdout === '' && !members.stderr) return [];
    const ids = members.stdout?.trim().split(/\s+/) ?? [];
    if (members.error || members.status !== 0 || members.stderr || !ids.length || ids.length > 4096
      || new Set(ids).size !== ids.length || ids.some(id => !/^[1-9][0-9]*$/.test(id)
        || !Number.isSafeInteger(Number(id)) || Number(id) > 2_147_483_647)) throw new Error('Cannot inspect exact owned process group');
    return ids;
  };
  if (platform === 'darwin') selection = ['-g', String(handle.pid)];
  else if (platform === 'linux') {
    selectedIds = linuxMembers();
    if (!selectedIds.length) return true;
    selection = ['-p', selectedIds.join(',')];
  } else throw new Error('Cannot inspect exact owned process group');
  const state = execute('/bin/ps', [...selection, '-o', 'pid=,pgid=,stat='], { env, encoding: 'utf8', timeout: 1000, maxBuffer: 262_144 });
  if (!state.error && state.status === 1 && state.stdout === '' && !state.stderr) {
    return platform !== 'linux' || linuxMembers().length === 0;
  }
  if (state.error || state.status !== 0 || state.stderr) throw new Error('Cannot inspect exact owned process group');
  const quiescent = parseOwnedGroupState(state.stdout, handle.pid);
  if (!quiescent || platform !== 'linux') return quiescent;
  // A new descendant can appear between pgrep and ps. Never infer quiescence
  // from a stale PID subset: another exact-group sample must agree or be empty.
  const after = linuxMembers();
  return !after.length || (after.length === selectedIds.length && after.every(id => selectedIds.includes(id)));
}
async function waitForOwnedGroup(handle, milliseconds) {
  const end = Date.now() + milliseconds;
  while (ownedGroupExists(handle) && Date.now() < end) await new Promise(resolve => setTimeout(resolve, 25));
  return !ownedGroupExists(handle) || ownedGroupIsQuiescent(handle);
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
export function runFixtureChild(command, args, options, timeout, guard) {
  guard?.assertOpen();
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
  let prepared, backend, next, stopping;
  const guard = createFixtureLaunchGuard();
  const steps = createFixtureOwnedSteps(guard);
  const stop = () => {
    guard.close();
    return stopping ??= (async () => {
      // Await already-owned file/binding work alongside child termination.
      // Do not track main()/its finally or child lifetimes as file steps: doing
      // so would make cleanup await itself or await a child before stopping it.
      await Promise.all([steps.drain(), ...[...runningChildren].map(terminateOwned)]);
      await backend?.stop();
      if (prepared) await removeBuild(prepared);
    })();
  };
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { void stop(); });
  try {
    guard.assertOpen();
    await steps.run(async () => { prepared = await prepareBuild(ROOT); });
    guard.assertOpen();
    preparationPhase = 'owned copy canonicalization';
    await steps.run(async () => { prepared.directory = await realpath(prepared.directory); });
    guard.assertOpen();
    preparationPhase = 'public input defaults';
    vmInput = await steps.run(() => readFile(path.join(prepared.directory, 'src/lib/nestegg/constants.ts'), 'utf8'));
    guard.assertOpen();
    preparationPhase = 'owned loopback binding';
    guard.assertOpen();
    const backendOrigin = await steps.run(async () => {
      backend = createBrowserBackend(defaultInputs());
      try { return await backend.start(); }
      catch (error) { backend = undefined; throw error; }
    });
    guard.assertOpen();
    const port = await steps.run(availablePort);
    guard.assertOpen();
    // Cookies ignore ports. A unique .localhost host prevents sb-127 cookies
    // from colliding with another project's local app on this computer.
    const appOrigin = `http://dashboard-fixture-${prepared.owner}.localhost:${port}`;
    const bindOrigin = `http://127.0.0.1:${port}`;
    backend.setAppOrigin(appOrigin);
    preparationPhase = 'fake environment';
    const env = browserEnvironment(prepared.directory, backendOrigin);
    const connectPolicy = "connect-src 'self' " + backendOrigin + ' ' + backendOrigin.replace('http:', 'ws:');
    // Keep generated local artifacts and process output confined to the owned copy.
    // No .env, ssl, agent/cloud config, existing build or application credentials copy.
    preparationPhase = 'locked dependency installation';
    await runFixtureChild('npm', ['ci', '--include=dev', '--ignore-scripts', '--no-audit', '--no-fund'],
      { cwd: prepared.directory, env, stdio: 'inherit' }, 300_000, guard);
    guard.assertOpen();
    const nextBin = path.join(prepared.directory, 'node_modules/next/dist/bin/next');
    preparationPhase = 'public fixture route copy';
    await steps.run(async () => {
      const metadata = await lstat(nextBin); guard.assertOpen();
      const canonicalNext = await realpath(nextBin); guard.assertOpen();
      if (!metadata.isFile() || canonicalNext !== nextBin) throw new Error('Next fixture executable must be regular owned source');
      // A restrictive test-only connect policy blocks the fixed hosted paper RPC
      // origin as well as all other cloud/worker origins. Real paper contract tests
      // use explicit component fixtures rather than weakening its project pin.
      const config = path.join(prepared.directory, 'next.config.ts');
      await writeFile(config, `import type { NextConfig } from 'next';\nconst config: NextConfig = { allowedDevOrigins: ['127.0.0.1'], async headers() { return [{source:'/:path*',headers:[{key:'X-Dashboard-Fixture-Owner',value:${JSON.stringify(prepared.owner)}},{key:'Content-Security-Policy',value:${JSON.stringify(connectPolicy)}}]}]; }}; export default config;\n`);
      guard.assertOpen();
      const fixtures = [['paper-page.tsx', 'page.tsx'], ['paper-data.ts', 'paper-data.ts']];
      const route = path.join(prepared.directory, 'src/app/(dashboard)/paper-fixture');
      await mkdir(route, { recursive: true, mode: 0o700 }); guard.assertOpen();
      for (const [source, destination] of fixtures) {
        const file = path.join(ROOT, 'scripts/browser-fixtures', source);
        for (const segment of [path.join(ROOT, 'scripts'), path.dirname(file), file]) {
          const metadata = await lstat(segment); guard.assertOpen();
          if (metadata.isSymbolicLink() || (segment === file && !metadata.isFile())) throw new Error('Browser fixture inputs must be regular public files');
        }
        await copyFile(file, path.join(route, destination)); guard.assertOpen();
      }
    });
    guard.assertOpen();
    preparationPhase = 'production fixture build';
    await runFixtureChild(process.execPath, [nextBin, 'build'],
      { cwd: prepared.directory, env, stdio: 'inherit' }, 600_000, guard);
    guard.assertOpen();
    preparationPhase = 'owned Next server readiness';
    guard.assertOpen();
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
        readyResponse = response.status === 200
          && response.headers.get('x-dashboard-fixture-owner') === prepared.owner
          && response.headers.get('content-security-policy') === connectPolicy
          && (await response.text()).includes('SYSTEM');
      } catch { /* The owned server may still be binding its selected port. */ }
      if (readyResponse) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    guard.assertOpen();
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
  main().catch(error => {
    const publicReasons = new Set(['Owned process group cleanup did not complete', 'Owned fixture preparation failed',
      'Owned fixture preparation timed out', 'Owned fixture is closing', 'Owned Next fixture readiness failed']);
    const detail = publicReasons.has(error.message) ? ` (${error.message})` : '';
    process.stderr.write(`Dashboard browser fixture failed during ${preparationPhase}${detail}; private inherited output is not used\n`);
    process.exitCode = 1;
  });
}
