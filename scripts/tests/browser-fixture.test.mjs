import test from 'node:test';
import assert from 'node:assert/strict';
import { createBrowserBackend, FIXTURE_KEY, FIXTURE_ADMIN_KEY, FIXTURE_PASSWORD, FIXTURE_OWNERS } from '../browser-fixtures/backend.mjs';
import { browserEnvironment, runFixtureChild, createFixtureLaunchGuard, createFixtureOwnedSteps,
  parseOwnedGroupState, ownedGroupIsQuiescent, ownedGroupIsActive, finishFixtureCleanup, fixtureFailureMetadata } from '../browser-fixture.mjs';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';

async function fixture(t) {
  const backend = createBrowserBackend({ currentAge: 32, retirementAge: 65, lifeExpectancy: 90 });
  const origin = await backend.start(); backend.setAppOrigin('http://dashboard-fixture-a1.localhost:33333');
  t.after(() => backend.stop());
  const request = (path, options = {}) => fetch(origin + path, {
    ...options, redirect: 'error', headers: { apikey: FIXTURE_KEY,
      'content-type': 'application/json', ...options.headers },
  });
  const login = async name => {
    const result = await request('/auth/v1/token?grant_type=password', { method: 'POST',
      body: JSON.stringify({ email: `${name}@dashboard.invalid`, password: FIXTURE_PASSWORD }) });
    assert.equal(result.status, 200); return result.json();
  };
  return { origin, request, login };
}
test('browser child drops inherited credentials and fixes both providers to owned loopback', () => {
  const env = browserEnvironment('/private/tmp/owned-browser', 'http://127.0.0.1:12345', {
    PATH: '/bin', API_SECRET_KEY: 'private-api', VERCEL_TOKEN: 'private-vercel',
    NEXT_PUBLIC_SUPABASE_URL: 'https://fxpxsciltakyypunglzr.supabase.co',
    NEXT_PUBLIC_SUPABASE_ANON_KEY: 'private-supabase', PYTHONPATH: '/unreviewed', NODE_OPTIONS: '--inspect',
    NPM_CONFIG_MAXSOCKETS: '999',
  });
  assert.equal(env.NEXT_PUBLIC_SUPABASE_URL, 'http://127.0.0.1:12345');
  assert.equal(env.NEXT_PUBLIC_SUPABASE_ANON_KEY, FIXTURE_KEY);
  assert.equal(env.NEXT_PUBLIC_VN_API_URL, 'http://127.0.0.1:12345');
  assert.equal(env.API_SECRET_KEY, 'dashboard-browser-fixture-api-key');
  assert.equal(env.SUPABASE_SERVICE_ROLE_KEY, FIXTURE_ADMIN_KEY);
  assert.equal(env.NPM_CONFIG_MAXSOCKETS, '4');
  assert.equal(env.NODE_OPTIONS, undefined); assert.equal(env.PYTHONPATH, undefined);
  assert.equal(env.VERCEL_TOKEN, undefined);
  assert.ok(!Object.values(env).some(v => String(v).includes('private-api')));
  for (const url of ['https://127.0.0.1:12345', 'http://localhost:12345',
    'http://127.0.0.1:12345/', 'https://fxpxsciltakyypunglzr.supabase.co', 'http://user@127.0.0.1:12345']) {
    assert.throws(() => browserEnvironment('/private/tmp/owned-browser', url, {}));
  }
});
test('only explicit synthetic logins succeed and data requires their current token', async t => {
  const f = await fixture(t);
  const refused = await f.request('/auth/v1/token?grant_type=password', { method: 'POST',
    body: JSON.stringify({ email: 'real@example.com', password: FIXTURE_PASSWORD }) });
  assert.equal(refused.status, 400);
  assert.equal((await f.request('/rest/v1/nestegg_scenarios?user_id=eq.' + FIXTURE_OWNERS.alice)).status, 401);
  const session = await f.login('alice');
  const result = await f.request('/auth/v1/user', { headers: { authorization: `Bearer ${session.access_token}` } });
  assert.equal((await result.json()).id, FIXTURE_OWNERS.alice);
});
test('owner predicates refuse cross-account reads and fake plans are distinct', async t => {
  const f = await fixture(t), a = await f.login('alice'), b = await f.login('bob');
  const headers = { authorization: `Bearer ${a.access_token}` };
  assert.equal((await f.request('/rest/v1/nestegg_scenarios?user_id=eq.' + FIXTURE_OWNERS.bob, { headers })).status, 403);
  const ar = await (await f.request('/rest/v1/nestegg_scenarios?user_id=eq.' + FIXTURE_OWNERS.alice, { headers })).json();
  const br = await (await f.request('/rest/v1/nestegg_scenarios?user_id=eq.' + FIXTURE_OWNERS.bob,
    { headers: { authorization: `Bearer ${b.access_token}` } })).json();
  assert.deepEqual(ar.map(r => r.inputs.currentSavings), [10_000, 70_000]);
  assert.deepEqual(br.map(r => r.inputs.currentSavings), [800_000]);
});
test('refresh rotates the token while preserving the logical session identity', async t => {
  const f = await fixture(t), a = await f.login('alice');
  const refreshed = await (await f.request('/auth/v1/token?grant_type=refresh_token', { method: 'POST',
    body: JSON.stringify({ refresh_token: a.refresh_token }) })).json();
  const payload = token => JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
  assert.notEqual(a.access_token, refreshed.access_token);
  assert.equal(payload(a.access_token).session_id, payload(refreshed.access_token).session_id);
  const relogin = await f.login('alice');
  assert.notEqual(payload(a.access_token).session_id, payload(relogin.access_token).session_id);
});
test('held original-owner reply stays captured after logout and another login', async t => {
  const f = await fixture(t), a = await f.login('alice');
  await f.request('/__fixture/control', { method: 'POST', body: JSON.stringify({ action: 'hold',
    method: 'GET', path: '/rest/v1/nestegg_scenarios', owner: FIXTURE_OWNERS.alice }) });
  const old = f.request('/rest/v1/nestegg_scenarios?user_id=eq.' + FIXTURE_OWNERS.alice,
    { headers: { authorization: `Bearer ${a.access_token}` } });
  let status;
  for (let i = 0; i < 20; i++) {
    status = await (await f.request('/__fixture/status')).json();
    if (status.pending.length) break;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  assert.equal(status.pending.length, 1);
  await f.request('/auth/v1/logout', { method: 'POST', headers: { authorization: `Bearer ${a.access_token}` } });
  await f.login('bob');
  await f.request('/__fixture/control', { method: 'POST', body: JSON.stringify({ action: 'release', id: status.pending[0].id }) });
  const rows = await (await old).json();
  assert.ok(rows.every(r => r.user_id === FIXTURE_OWNERS.alice));
  assert.equal((await f.request('/auth/v1/user', { headers: { authorization: `Bearer ${a.access_token}` } })).status, 401);
  assert.equal((await f.request('/auth/v1/token?grant_type=refresh_token', { method: 'POST',
    body: JSON.stringify({ refresh_token: a.refresh_token }) })).status, 400);
  assert.equal((await f.login('alice')).user.id, FIXTURE_OWNERS.alice);
});
test('writes stay owner-scoped and unknown RPC/targets fail rather than proxy', async t => {
  const f = await fixture(t), a = await f.login('alice'), headers = { authorization: `Bearer ${a.access_token}` };
  assert.equal((await f.request('/rest/v1/nestegg_scenarios', { method: 'POST', headers,
    body: JSON.stringify({ user_id: FIXTURE_OWNERS.bob, name: 'cross-owner', inputs: {}, market_scenario: 'base' }) })).status, 403);
  const response = await f.request('/rest/v1/nestegg_scenarios?select=*', { method: 'POST',
    headers: { ...headers, accept: 'application/vnd.pgrst.object+json' },
    body: JSON.stringify({ user_id: FIXTURE_OWNERS.alice, name: 'synthetic only', inputs: { currentSavings: 77 }, market_scenario: 'base' }) });
  assert.equal(response.status, 200); assert.equal((await response.json()).user_id, FIXTURE_OWNERS.alice);
  assert.equal((await f.request('/rest/v1/rpc/discover', { method: 'POST', headers, body: '{}' })).status, 404);
  assert.equal((await f.request('/proxy?url=https://example.com', { headers })).status, 404);
});
test('foreign browser origins and oversized request bodies are refused', async t => {
  const f = await fixture(t);
  assert.equal((await f.request('/__fixture/status', { headers: { origin: 'https://example.com' } })).status, 403);
  assert.equal((await f.request('/auth/v1/token?grant_type=password', { method: 'POST',
    body: JSON.stringify({ email: 'alice@dashboard.invalid', password: 'x'.repeat(66_000) }) })).status, 400);
});
test('synthetic Portfolio writes return exact owned acknowledgments and original deleted rows', async t => {
  const f = await fixture(t), a = await f.login('alice');
  const headers = { authorization: `Bearer ${a.access_token}`, accept: 'application/vnd.pgrst.object+json' };
  const base = '/rest/v1/portfolio_accounts';
  const response = await f.request(base, { method: 'POST', headers, body: JSON.stringify({
    user_id: FIXTURE_OWNERS.alice, name: 'private fixture account', balance: 321, updated_at: '2026-10-13T12:00:00Z' }) });
  assert.equal(response.status, 200); const row = await response.json();
  assert.equal(row.user_id, FIXTURE_OWNERS.alice); assert.equal(row.balance, 321);
  const target = base + '?user_id=eq.' + FIXTURE_OWNERS.alice + '&id=eq.' + row.id;
  const edited = await (await f.request(target, { method: 'PATCH', headers, body: JSON.stringify({
    name: 'edited private fixture', balance: 456, updated_at: '2026-10-13T12:01:00Z' }) })).json();
  assert.equal(edited.id, row.id); assert.equal(edited.balance, 456);
  const deleted = await (await f.request(target, { method: 'DELETE', headers })).json();
  assert.equal(deleted.id, row.id); assert.equal(deleted.user_id, FIXTURE_OWNERS.alice);
  assert.equal(await (await f.request(target, { method: 'DELETE', headers })).json(), null);
  const goal = await (await f.request('/rest/v1/profiles?id=eq.' + FIXTURE_OWNERS.alice, {
    method: 'PATCH', headers, body: JSON.stringify({ portfolio_goal: 222222, portfolio_goal_year: 2051 }) })).json();
  assert.equal(goal.id, FIXTURE_OWNERS.alice); assert.equal(goal.portfolio_goal, 222222); assert.equal(goal.portfolio_goal_year, 2051);
});
test('synthetic Portfolio rejects foreign owners and invalid fields without changing saved rows', async t => {
  const f = await fixture(t), a = await f.login('alice');
  const headers = { authorization: `Bearer ${a.access_token}` };
  const target = '/rest/v1/portfolio_accounts?user_id=eq.' + FIXTURE_OWNERS.alice + '&id=eq.alice-portfolio';
  const before = await (await f.request(target, { headers })).json();
  for (const input of [{ name: 'foreign', user_id: FIXTURE_OWNERS.bob, updated_at: '2026-10-13T12:00:00Z' },
    { balance: true, updated_at: '2026-10-13T12:00:00Z' }, { balance: -1, updated_at: '2026-10-13T12:00:00Z' }]) {
    assert.equal((await f.request(target, { method: 'PATCH', headers, body: JSON.stringify(input) })).status, 403);
  }
  assert.equal((await f.request('/rest/v1/portfolio_accounts?user_id=eq.' + FIXTURE_OWNERS.bob + '&id=eq.bob-portfolio', {
    method: 'DELETE', headers })).status, 403);
  assert.equal((await f.request('/rest/v1/profiles?id=eq.' + FIXTURE_OWNERS.alice, { method: 'PATCH', headers,
    body: JSON.stringify({ portfolio_goal: 111, portfolio_goal_year: 2050.5 }) })).status, 403);
  assert.deepEqual(await (await f.request(target, { headers })).json(), before);
  assert.equal((await f.request('/rest/v1/portfolio_accounts', { method: 'POST', headers,
    body: JSON.stringify({ user_id: FIXTURE_OWNERS.bob, name: 'foreign', balance: 1, updated_at: '2026-10-13T12:00:00Z' }) })).status, 403);
});
test('synthetic admin admits only the approved zero-row API read and never writes', async t => {
  const f = await fixture(t), headers = { apikey: FIXTURE_ADMIN_KEY, authorization: `Bearer ${FIXTURE_ADMIN_KEY}` };
  const response = await f.request('/rest/v1/test_events?select=*&limit=0', { headers });
  assert.equal(response.status, 200); assert.deepEqual(await response.json(), []);
  assert.equal((await f.request('/rest/v1/test_events?limit=1', { headers })).status, 403);
  assert.equal((await f.request('/rest/v1/nestegg_scenarios?limit=0', { headers })).status, 403);
  assert.equal((await f.request('/rest/v1/test_events?limit=0', { method: 'POST', headers, body: '{}' })).status, 403);
});
test('preparation timeout awaits termination of its exact child group including descendants', async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'dashboard-browser-process-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const marker = path.join(directory, 'synthetic-heartbeat');
  const descendant = `const fs=require('node:fs');process.on('SIGTERM',()=>{});setInterval(()=>fs.writeFileSync(process.argv[1],String(Date.now())),10);`;
  const parent = `const {spawn}=require('node:child_process');process.on('SIGTERM',()=>{});spawn(process.execPath,['-e',${JSON.stringify(descendant)},process.argv[1]],{stdio:'ignore'});setInterval(()=>{},1000);`;
  await assert.rejects(runFixtureChild(process.execPath, ['-e', parent, marker],
    { cwd: directory, env: {}, stdio: 'ignore' }, 400), /preparation timed out/);
  const final = await readFile(marker, 'utf8');
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(await readFile(marker, 'utf8'), final, 'No owned descendant remains writing after timeout');
});
test('timeout removes surviving descendant even when the group leader exits on TERM', async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'dashboard-browser-orphan-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const marker = path.join(directory, 'synthetic-heartbeat');
  const descendant = `const fs=require('node:fs');process.on('SIGTERM',()=>{});setInterval(()=>fs.writeFileSync(process.argv[1],String(Date.now())),10);`;
  const parent = `require('node:child_process').spawn(process.execPath,['-e',${JSON.stringify(descendant)},process.argv[1]],{stdio:'ignore'});setInterval(()=>{},1000);`;
  await assert.rejects(runFixtureChild(process.execPath, ['-e', parent, marker],
    { cwd: directory, env: {}, stdio: 'ignore' }, 400), /preparation timed out/);
  const final = await readFile(marker, 'utf8');
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(await readFile(marker, 'utf8'), final);
});

test('TERM metadata failure still kills the exact registered ignore-TERM leader', { timeout: 16_000 }, async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'dashboard-browser-metadata-test-'));
  const marker = path.join(directory, 'synthetic-heartbeat');
  const source = `const fs=require('node:fs');process.on('SIGTERM',()=>{});setInterval(()=>fs.writeFileSync(process.argv[1],String(Date.now())),10);`;
  const originalSpawn = childProcess.spawn, originalSpawnSync = childProcess.spawnSync, originalKill = process.kill;
  let owned, failures = 0, probeFailures = 0, phase = 'before-term';
  const observed = [];
  t.after(async () => {
    process.kill = originalKill;
    childProcess.spawn = originalSpawn; childProcess.spawnSync = originalSpawnSync; syncBuiltinESMExports();
    // Even a regression failure must not leave this test's exact child alive.
    if (owned?.pid) {
      try { process.kill(-owned.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
    }
    await rm(directory, { recursive: true, force: true });
  });
  childProcess.spawn = (command, args, options) => {
    assert.equal(command, process.execPath); assert.deepEqual(args, ['-e', source, marker]);
    assert.equal(options.detached, true); assert.equal(options.shell, false);
    owned = originalSpawn(command, args, options); return owned;
  };
  process.kill = (pid, signal) => {
    if (owned && pid === -owned.pid) {
      if (signal === 'SIGTERM' || signal === 'SIGKILL') {
        const result = originalKill.call(process, pid, signal);
        phase = signal === 'SIGTERM' ? 'term' : 'kill';
        observed.push(signal); return result;
      }
      if (signal === 0 && phase === 'term' && probeFailures === 0) {
        probeFailures++; observed.push('probe-unavailable');
        throw Object.assign(new Error('synthetic exact-owned probe unavailable'), { code: 'EPERM' });
      }
    }
    return originalKill.call(process, pid, signal);
  };
  childProcess.spawnSync = (command, args, options) => {
    if (command === '/bin/ps' && owned && phase === 'term' && probeFailures === 1 && failures === 0) {
      const selected = args[1].split(','); assert.ok(selected.includes(String(owned.pid)));
      failures++; observed.push('metadata-unavailable');
      return { error: new Error('synthetic exact-group metadata unavailable'), status: null, stdout: '', stderr: '' };
    }
    return originalSpawnSync(command, args, options);
  };
  syncBuiltinESMExports();
  await assert.rejects(runFixtureChild(process.execPath, ['-e', source, marker],
    { cwd: directory, env: {}, stdio: 'ignore' }, 400), /preparation timed out/);
  assert.equal(failures, 1, 'The TERM-phase metadata check failed before the KILL phase');
  assert.equal(probeFailures, 1);
  assert.deepEqual(observed, ['SIGTERM', 'probe-unavailable', 'metadata-unavailable', 'SIGKILL']);
  const final = await readFile(marker, 'utf8');
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(await readFile(marker, 'utf8'), final, 'No exact owned leader remains writing after timeout');
});


test('shutdown racing successful preparation refuses every subsequent child launch', async () => {
  const guard = createFixtureLaunchGuard();
  const completed = runFixtureChild(process.execPath, ['-e', 'process.exit(0)'],
    { env: {}, stdio: 'ignore' }, 1000, guard);
  completed.then(() => guard.close());
  await completed;
  assert.equal(guard.closing, true);
  assert.throws(() => runFixtureChild('/must-never-spawn', [], { env: {} }, 1000, guard), /fixture is closing/);
  assert.throws(() => guard.assertOpen(), /fixture is closing/);
  guard.close(); assert.equal(guard.closing, true);
});

test('shutdown drains an already-owned filesystem write before removing its directory', async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'dashboard-browser-write-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const marker = path.join(directory, 'owned-step');
  const guard = createFixtureLaunchGuard(), steps = createFixtureOwnedSteps(guard);
  let enter, release;
  const entered = new Promise(resolve => { enter = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  const write = steps.run(async () => {
    enter(); await gate;
    await writeFile(marker, 'completed owned write');
    guard.assertOpen();
  });
  await entered; guard.close();
  let cleaned = false;
  const cleanup = steps.drain().then(async () => {
    assert.equal(await readFile(marker, 'utf8'), 'completed owned write');
    await rm(directory, { recursive: true }); cleaned = true;
  });
  await new Promise(setImmediate);
  assert.equal(cleaned, false, 'Cleanup waits for the operation already in progress');
  assert.throws(() => steps.run(() => writeFile(marker, 'must not run')), /fixture is closing/);
  release(); await assert.rejects(write, /fixture is closing/); await cleanup;
  assert.equal(cleaned, true);
  await assert.rejects(readFile(marker), error => error.code === 'ENOENT');
});

test('closed steps never start queued work and failed steps cannot deadlock cleanup', async () => {
  const guard = createFixtureLaunchGuard(), steps = createFixtureOwnedSteps(guard);
  await assert.rejects(steps.drain(), /closed launch guard/);
  let launched = false;
  const queued = steps.run(() => { launched = true; });
  guard.close(); await assert.rejects(queued, /fixture is closing/);
  await steps.drain(); assert.equal(launched, false);
  const second = createFixtureLaunchGuard(), failing = createFixtureOwnedSteps(second);
  const rejected = failing.run(() => { throw new Error('synthetic owned step failure'); });
  await assert.rejects(rejected, /synthetic owned step failure/);
  second.close(); await failing.drain();
});

test('failed final group verification settles preparation, closes the owned backend and retains the copy', async t => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'dashboard-browser-finalizer-test-'));
  const marker = path.join(directory, 'owned-copy');
  await writeFile(marker, 'retained source evidence');
  let backend, origin, release, removed = false;
  t.after(async () => { await backend?.stop(); await rm(directory, { recursive: true, force: true }); });
  const preparation = new Promise(resolve => { release = resolve; }).then(async () => {
    backend = createBrowserBackend({ currentAge: 32, retirementAge: 65, lifeExpectancy: 90 });
    origin = await backend.start();
  });
  const failure = Object.assign(new Error('synthetic private metadata detail'), { code: 'EPERM' });
  const cleanup = finishFixtureCleanup([preparation, Promise.reject(failure)], () => backend?.stop(),
    async () => { removed = true; await rm(directory, { recursive: true }); });
  const refused = assert.rejects(cleanup, error => error === failure);
  await new Promise(setImmediate); assert.equal(backend, undefined); assert.equal(removed, false);
  release(); await refused;
  assert.equal(removed, false); assert.equal(await readFile(marker, 'utf8'), 'retained source evidence');
  await assert.rejects(fetch(origin + '/__fixture/status', { signal: AbortSignal.timeout(1000) }));
});

test('failure diagnostics expose only closed error enums and exact owned metadata', () => {
  const prepared = { directory: '/private/tmp/dashboard-ci-build-ABC123', owner: '00000000-0000-4000-8000-000000000001' };
  const error = Object.assign(new TypeError('private error message'), { code: 'EPERM', stack: 'private stack', secret: 'private credential' });
  const data = fixtureFailureMetadata(error, prepared, [11, 11, -1, 'private group', NaN]);
  assert.equal(data.errorName, 'TypeError'); assert.equal(data.errorCode, 'EPERM');
  assert.deepEqual(data.ownedProcessGroups, [11]); assert.equal(data.parentPid, process.pid);
  assert.equal(data.markerDirectory, prepared.directory); assert.equal(data.markerOwner, prepared.owner);
  assert.doesNotMatch(JSON.stringify(data), /private error|private stack|private credential|private group/);
  const unknown = fixtureFailureMetadata({ name: 'private name', code: 'private code', message: 'private message' },
    { directory: '/Users/private-data/dashboard-ci-build-ABC123', owner: prepared.owner });
  assert.equal(unknown.errorName, 'UnknownError'); assert.equal(unknown.errorCode, 'UNKNOWN');
  assert.equal(unknown.markerDirectory, null); assert.equal(unknown.markerOwner, null);
  assert.doesNotMatch(JSON.stringify(unknown), /private/);
  assert.equal(fixtureFailureMetadata(new Error('private wrapped error', { cause: error })).errorCode, 'EPERM');
  assert.equal(fixtureFailureMetadata(null).errorName, 'UnknownError');
});

test('failed exact-group signal probes retire only with positive empty or zombie metadata', () => {
  const handle = { pid: 11 }, failure = Object.assign(new Error('synthetic signal probe refused'), { code: 'EPERM' });
  const probe = current => { assert.equal(current, handle); throw failure; };
  assert.equal(ownedGroupIsActive(handle, probe, current => {
    assert.equal(current, handle); return parseOwnedGroupState('12 11 Z\n13 11 Zs\n', 11);
  }), false);
  assert.equal(ownedGroupIsActive(handle, probe, current => { assert.equal(current, handle); return true; }), false);
  assert.throws(() => ownedGroupIsActive(handle, probe, () => false), error => error === failure);
  assert.throws(() => ownedGroupIsActive(handle, probe, () => { throw new Error('synthetic metadata unavailable'); }), /metadata unavailable/);
  assert.throws(() => ownedGroupIsActive(handle, probe, () => parseOwnedGroupState('12 99 Z', 11)), /exact owned process group/);
});

test('owned-group parser distinguishes zombie-only quiescence from live or malformed members', () => {
  assert.equal(parseOwnedGroupState(' 12 11 Z\n 13 11 Zs\n', 11), true);
  assert.equal(parseOwnedGroupState('12 11 Z\n13 11 Ss\n', 11), false);
  assert.equal(parseOwnedGroupState('', 11), true);
  for (const [output, group] of [['12 99 Z', 11], ['PID PGID STAT', 11], ['12 11 Zgarbage', 11],
    ['12 11 Z\n12 11 Z', 11], ['0 11 Z', 11], ['12 11 0', 11], ['12 11 Z', 0],
    ['12 11 Z', -11], ['12 11 Z', NaN], ['x'.repeat(262_145), 11]]) {
    assert.throws(() => parseOwnedGroupState(output, group), /exact owned process group/);
  }
});

test('macOS quiescence selects only exact owned group metadata with legacy mode disabled', () => {
  const calls = [];
  const execute = (command, args, options) => {
    calls.push({ command, args, options }); return { status: 0, stdout: '12 11 Z\n13 11 Zs\n', stderr: '' };
  };
  assert.equal(ownedGroupIsQuiescent({ pid: 11 }, execute, 'darwin'), true);
  assert.deepEqual(calls[0].args, ['-g', '11', '-o', 'pid=,pgid=,stat=']);
  assert.equal(calls[0].command, '/bin/ps');
  assert.deepEqual(calls[0].options.env, { COMMAND_MODE: 'unix2003', LC_ALL: 'C' });
  assert.equal(calls[0].options.maxBuffer, 262_144);
  assert.equal(calls[0].options.timeout, 1000);
});

test('Linux quiescence resamples exact membership so a new descendant cannot be missed', () => {
  const calls = [], replies = [
    { status: 0, stdout: '12\n13\n', stderr: '' },
    { status: 0, stdout: '12 11 Z\n13 11 Z\n', stderr: '' },
    { status: 0, stdout: '12\n13\n14\n', stderr: '' },
  ];
  const execute = (command, args) => { calls.push({ command, args }); return replies.shift(); };
  assert.equal(ownedGroupIsQuiescent({ pid: 11 }, execute, 'linux'), false);
  assert.deepEqual(calls, [{ command: '/usr/bin/pgrep', args: ['-g', '11'] },
    { command: '/bin/ps', args: ['-p', '12,13', '-o', 'pid=,pgid=,stat='] },
    { command: '/usr/bin/pgrep', args: ['-g', '11'] }]);
  const replaced = [{ status: 0, stdout: '12\n', stderr: '' },
    { status: 1, stdout: '', stderr: '' }, { status: 0, stdout: '14\n', stderr: '' }];
  assert.equal(ownedGroupIsQuiescent({ pid: 11 }, () => replaced.shift(), 'linux'), false,
    'A vanished stale PID subset is not proof that its entire owned group is empty');
});

test('owned-group command failures, foreign metadata and unsupported platforms fail closed', () => {
  for (const reply of [{ status: 2, stdout: '', stderr: 'synthetic command error' },
    { status: 1, stdout: '', stderr: 'synthetic permission error' },
    { status: 0, stdout: '12 99 Z', stderr: '' },
    { status: 0, stdout: 'unknown', stderr: '' },
    { error: new Error('synthetic unavailable'), status: null, stdout: '', stderr: '' }]) {
    assert.throws(() => ownedGroupIsQuiescent({ pid: 11 }, () => reply, 'darwin'), /exact owned process group/);
  }
  assert.equal(ownedGroupIsQuiescent({ pid: 11 }, () => ({ status: 1, stdout: '', stderr: '' }), 'darwin'), true);
  assert.throws(() => ownedGroupIsQuiescent({ pid: 0 }, () => assert.fail('must not execute'), 'darwin'), /exact owned process group/);
  assert.throws(() => ownedGroupIsQuiescent({ pid: 11 }, () => assert.fail('must not execute'), 'win32'), /exact owned process group/);
});
