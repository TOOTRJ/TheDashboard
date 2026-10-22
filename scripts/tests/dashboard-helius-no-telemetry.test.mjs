import assert from 'node:assert/strict';
import test from 'node:test';
import { withoutHeliusTelemetry } from '../dashboard-helius-no-telemetry.mjs';

const endpoint = 'https://www.helius.dev/relay-RMqE/capture/';

test('suppresses the pinned telemetry URL for strings, URL objects and Requests', async () => {
  let calls = 0;
  const fetch = withoutHeliusTelemetry(() => { calls += 1; throw new Error('Unexpected delegation'); });
  for (const input of [endpoint, new URL(endpoint), new Request(endpoint, {
    method: 'POST', body: 'FAKE_TELEMETRY_DO_NOT_TRANSMIT',
  }), endpoint + '?batch=1']) {
    const result = await fetch(input);
    assert.equal(result.status, 204);
    assert.equal(await result.text(), '');
  }
  assert.equal(calls, 0);
});

test('does not inspect the suppressed request payload or headers', async () => {
  const fetch = withoutHeliusTelemetry(() => { throw new Error('Unexpected delegation'); });
  const init = {};
  Object.defineProperty(init, 'body', { get() { throw new Error('Body inspected'); } });
  Object.defineProperty(init, 'headers', { get() { throw new Error('Headers inspected'); } });
  assert.equal((await fetch(endpoint, init)).status, 204);
});

test('ordinary provider and documentation fetch calls preserve identity and arguments', async () => {
  const response = new Response('mock response');
  const calls = [];
  const fetch = withoutHeliusTelemetry(function (input, init) {
    calls.push({ input, init, receiver: this });
    return Promise.resolve(response);
  });
  const input = new Request('https://mainnet.helius-rpc.com/');
  const init = { method: 'POST', body: 'mock rpc' };
  const receiver = {};
  assert.equal(await fetch.call(receiver, input, init), response);
  assert.deepEqual(calls, [{ input, init, receiver }]);
});

test('does not suppress other hosts, protocols or paths', async () => {
  const passed = [];
  const fetch = withoutHeliusTelemetry((input) => {
    passed.push(input);
    return Promise.resolve(new Response('mock'));
  });
  for (const url of [
    'https://www.helius.dev/docs/agents/mcp',
    'https://other.invalid/relay-RMqE/capture/',
    'https://www.helius.dev/relay-RMqE/capture/other',
    'http://www.helius.dev/relay-RMqE/capture/',
    'https://www.helius.dev:444/relay-RMqE/capture/',
  ]) {
    assert.equal((await fetch(url)).status, 200);
  }
  assert.equal(passed.length, 5);
});

test('delegated failures keep their original error without logging', async () => {
  const error = new TypeError('mock native failure');
  const fetch = withoutHeliusTelemetry(() => Promise.reject(error));
  await assert.rejects(fetch('not a valid URL'), (caught) => caught === error);
});

test('the preload installs the suppression on global fetch', async () => {
  assert.equal((await globalThis.fetch(endpoint, { method: 'POST' })).status, 204);
});
