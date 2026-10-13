import test from 'node:test';
import assert from 'node:assert/strict';
import { createBrowserBackend, FIXTURE_KEY, FIXTURE_ADMIN_KEY, FIXTURE_PASSWORD, FIXTURE_OWNERS } from '../browser-fixtures/backend.mjs';
import { browserEnvironment, runFixtureChild } from '../browser-fixture.mjs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

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
  });
  assert.equal(env.NEXT_PUBLIC_SUPABASE_URL, 'http://127.0.0.1:12345');
  assert.equal(env.NEXT_PUBLIC_SUPABASE_ANON_KEY, FIXTURE_KEY);
  assert.equal(env.NEXT_PUBLIC_VN_API_URL, 'http://127.0.0.1:12345');
  assert.equal(env.API_SECRET_KEY, 'dashboard-browser-fixture-api-key');
  assert.equal(env.SUPABASE_SERVICE_ROLE_KEY, FIXTURE_ADMIN_KEY);
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
