import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import test from 'node:test';
import { createClient } from '@supabase/supabase-js';
import { createBrowserBackend, FIXTURE_KEY, FIXTURE_OWNERS, FIXTURE_PASSWORD } from '../browser-fixtures/backend.mjs';

const path = '/rest/v1/vn_trades';

async function fixture(t) {
  const backend = createBrowserBackend({});
  const origin = await backend.start();
  t.after(() => backend.stop());
  function request(route, options = {}) {
    const url = new URL(route, origin);
    assert.equal(url.origin, origin);
    return fetch(url, { ...options, redirect: 'error', signal: AbortSignal.timeout(1500),
      headers: { apikey: FIXTURE_KEY, 'content-type': 'application/json' } });
  }
  async function client(name) {
    const login = await request('/auth/v1/token?grant_type=password', {
      method: 'POST', body: JSON.stringify({ email: `${name}@dashboard.invalid`, password: FIXTURE_PASSWORD }),
    });
    assert.equal(login.status, 200);
    const { access_token } = await login.json();
    return createClient(origin, FIXTURE_KEY, { accessToken: async () => access_token });
  }
  return { client, status: async () => (await request('/__fixture/status')).json(),
    control: value => request('/__fixture/control', { method: 'POST', body: JSON.stringify(value) }) };
}

function page(client, owner, offset, signal = AbortSignal.timeout(1500)) {
  return client.from('vn_trades').select('*', { count: 'exact' }).eq('probe_id', owner)
    .order('opened_at', { ascending: false }).order('id', { ascending: true })
    .range(offset, offset + 199).abortSignal(signal);
}

async function observe(status, predicate) {
  const end = performance.now() + 1200;
  do {
    const value = await status();
    if (predicate(value)) return value;
    await delay(10);
  } while (performance.now() < end);
  assert.fail('Expected synthetic trace state did not arrive');
}

test('loopback SDK sees 1001 exact, ordered Alice rows in 28 capped pages and only two Bob rows', async (t) => {
  const f = await fixture(t);
  const [alice, bob] = await Promise.all([f.client('alice'), f.client('bob')]);
  const rows = [];
  for (let offset = 0; offset < 1001; offset += 37) {
    const result = await page(alice, FIXTURE_OWNERS.alice, offset);
    assert.equal(result.status, 200);
    assert.equal(result.count, 1001);
    assert.equal(result.data.length, Math.min(37, 1001 - offset));
    rows.push(...result.data);
  }
  assert.deepEqual(rows.map(row => row.pair), Array.from({ length: 1001 }, (_, index) =>
    `ALICE-TRADE-${String(index + 1).padStart(4, '0')}/USDC`));
  assert.equal(new Set(rows.map(row => row.id)).size, 1001);
  assert.equal(new Set(rows.map(row => row.opened_at)).size, 1);
  const bobRows = await page(bob, FIXTURE_OWNERS.bob, 0);
  assert.equal(bobRows.count, 2);
  assert.deepEqual(bobRows.data.map(row => row.pair), ['BOB-TRADE-0001/USDC', 'BOB-TRADE-0002/USDC']);
  assert.equal((await page(bob, FIXTURE_OWNERS.alice, 0)).status, 403);
  assert.equal((await page(alice, FIXTURE_OWNERS.bob, 0)).status, 403);
  const history = (await f.status()).history.filter(entry => entry.trade && entry.owner === FIXTURE_OWNERS.alice);
  assert.deepEqual(history.map(entry => entry.trade.offset), Array.from({ length: 28 }, (_, i) => i * 37));
  assert.equal(history.every(entry => entry.trade.outcome === 'sent'), true);
});

test('held trade page is owner and offset specific; transport abort retires its original response', async (t) => {
  const f = await fixture(t);
  const [alice, bob] = await Promise.all([f.client('alice'), f.client('bob')]);
  const hold = { action: 'hold', method: 'GET', path, owner: FIXTURE_OWNERS.alice, offset: 37 };
  assert.equal((await f.control({ ...hold, owner: undefined })).status, 400);
  assert.equal((await f.control({ ...hold, offset: -1 })).status, 400);
  assert.equal((await f.control({ ...hold, method: 'POST' })).status, 400);
  assert.equal((await f.control(hold)).status, 200);
  assert.equal((await page(alice, FIXTURE_OWNERS.alice, 0)).count, 1001);
  assert.equal((await page(bob, FIXTURE_OWNERS.bob, 37)).count, 2);
  assert.equal((await f.status()).holds.length, 1);
  const abort = new AbortController();
  const pending = page(alice, FIXTURE_OWNERS.alice, 37, abort.signal).then(value => value);
  const state = await observe(f.status, value => value.pending.length === 1);
  const held = state.pending[0];
  assert.equal(held.owner, FIXTURE_OWNERS.alice);
  assert.equal(held.trade.offset, 37);
  assert.equal(held.trade.outcome, 'held');
  abort.abort();
  const cancelled = await pending;
  assert.equal(cancelled.data, null);
  assert.ok(cancelled.error);
  const retired = await observe(f.status, value => value.history.some(entry =>
    entry.sequence === held.sequence && entry.trade?.outcome === 'client-aborted'));
  assert.equal(retired.pending.length, 0);
  assert.equal((await f.control({ action: 'release', id: held.id })).status, 400);
  assert.equal((await page(bob, FIXTURE_OWNERS.bob, 0)).count, 2);
});
