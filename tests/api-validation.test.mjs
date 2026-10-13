import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const encode = value => new TextEncoder().encode(value);
const SENTIMENT = { score: 75, sentiment: 'bullish', summary: 'Synthetic summary', key_factors: ['Synthetic factor'] };
const clone = value => JSON.parse(JSON.stringify(value));

function harness(options = {}) {
  const env = { API_SECRET_KEY: 'synthetic-api-key', NEXT_PUBLIC_SUPABASE_URL: 'https://synthetic.supabase.invalid',
    SUPABASE_SERVICE_ROLE_KEY: 'synthetic-service-key', ...options.env };
  const calls = [], constructors = [], logs = [];
  const state = { error: null, data: { id: 'synthetic-row' }, constructorError: false, queryError: false, ...options };
  class FixedDate extends Date { constructor(value = '2026-10-13T23:59:58Z') { super(value); } }
  const globals = { TextEncoder, TextDecoder, Uint8Array, URL, URLSearchParams, Date: FixedDate,
    process: { env }, console: { error: (...args) => logs.push(args) },
    fetch() { throw new Error('Network is forbidden in API tests'); } };
  function load(path, modules = {}) {
    const exports = {};
    const code = ts.transpileModule(fs.readFileSync(path, 'utf8'), { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    } }).outputText;
    vm.runInNewContext(code, { exports, ...globals,
      require(name) { assert.ok(Object.hasOwn(modules, name), `Unexpected dependency ${name}`); return modules[name]; } }, { filename: path });
    return exports;
  }
  const errors = load('src/lib/api/errors.ts');
  const validation = load('src/lib/api/validation.ts', { './errors': errors });
  const auth = load('src/lib/api/auth.ts', { './validation': validation });
  const responses = load('src/lib/api/responses.ts', { 'next/server': { NextResponse: { json: Response.json } } });
  const handler = load('src/lib/api/handler.ts', { './auth': auth, './responses': responses, './errors': errors });
  const api = load('src/lib/api/index.ts', { './auth': auth, './responses': responses, './handler': handler, './validation': validation, './errors': errors });
  const admin = load('src/lib/supabase/admin.ts', { '@/lib/api/errors': errors, '@supabase/supabase-js': {
    createClient(url, key, config) {
      constructors.push({ url, key, config: clone(config) });
      if (state.constructorError) throw new Error('PRIVATE SYNTHETIC CONSTRUCTOR DETAIL');
      return { from(table) {
        if (state.queryError) throw new Error('PRIVATE SYNTHETIC QUERY DETAIL');
        const call = { table }; calls.push(call);
        const result = () => ({ data: state.data, error: state.error });
        const builder = {
          insert(value) { call.insert = clone(value); return this; },
          select(columns) { call.select = columns; return this; },
          order(column, config) { call.order = [column, clone(config)]; return this; },
          limit(value) { call.limit = value; return this; },
          single() { call.single = true; return Promise.resolve(result()); },
          then(resolve, reject) { return Promise.resolve(result()).then(resolve, reject); },
        };
        return builder;
      } };
    },
  } });
  const imports = { '@/lib/supabase/admin': admin, '@/lib/api': api };
  return { env, state, calls, constructors, logs, errors, validation, auth, responses, handler, admin,
    testRoute: load('src/app/api/v1/test/route.ts', imports), sentimentRoute: load('src/app/api/v1/sentiment/route.ts', imports) };
}

function request(path = '/api/v1/test', { method = 'GET', body, key = 'synthetic-api-key', source, headers = {} } = {}) {
  const values = { ...headers };
  if (key !== null) values['x-api-key'] = key;
  if (source !== undefined) values['x-source'] = source;
  const init = { method, headers: values };
  if (body !== undefined) init.body = typeof body === 'string' ? body : JSON.stringify(body);
  return new Request('https://dashboard.invalid' + path, init);
}

function streamRequest(chunks, { source = null, key = 'synthetic-api-key', readError = false, cancelError = false } = {}) {
  let index = 0;
  const control = { reads: 0, cancellations: 0, released: false };
  return { control, value: { url: 'https://dashboard.invalid/api/v1/test',
    headers: { get(name) { return name === 'x-api-key' ? key : name === 'x-source' ? source : name === 'content-length' ? '1' : null; } },
    body: { getReader() { return {
      async read() { control.reads++; if (readError) throw new Error('PRIVATE SYNTHETIC STREAM DETAIL');
        return index < chunks.length ? { done: false, value: chunks[index++] } : { done: true }; },
      cancel() { control.cancellations++; if (cancelError) throw new Error('PRIVATE SYNTHETIC CANCEL DETAIL'); return Promise.resolve(); },
      releaseLock() { control.released = true; },
    }; } },
  } };
}

async function assertResponse(response, status, code) {
  assert.equal(response.status, status);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  const body = await response.json();
  assert.equal(typeof body.meta.timestamp, 'string');
  if (code) { assert.equal(body.success, false); assert.equal(body.error.code, code); }
  else assert.equal(body.success, true);
  assert.doesNotMatch(JSON.stringify(body), /PRIVATE SYNTHETIC|synthetic-service-key|synthetic-api-key/);
  return body;
}

test('importing actual routes and admin performs no construction or database request', () => {
  const h = harness({ env: { API_SECRET_KEY: undefined, NEXT_PUBLIC_SUPABASE_URL: undefined, SUPABASE_SERVICE_ROLE_KEY: undefined } });
  assert.equal(h.constructors.length, 0); assert.equal(h.calls.length, 0);
});

for (const key of [undefined, '', '   ', '\t']) test(`missing/blank key configuration is controlled503 (${JSON.stringify(key)})`, async () => {
  const h = harness({ env: { API_SECRET_KEY: key } });
  await assertResponse(await h.testRoute.GET(request()), 503, 'SERVICE_UNAVAILABLE');
  assert.equal(h.constructors.length, 0); assert.equal(h.calls.length, 0);
  assert.deepEqual(h.logs, [['Dashboard API failure', 'CONFIGURATION']]);
});

for (const key of [null, '', 'wrong-key']) test(`valid configuration refuses unauthorized key before body read (${JSON.stringify(key)})`, async () => {
  const h = harness(), streamed = streamRequest([encode('{}')], { key });
  await assertResponse(await h.testRoute.POST(streamed.value), 401, 'UNAUTHORIZED');
  assert.equal(streamed.control.reads, 0); assert.equal(h.constructors.length, 0); assert.equal(h.calls.length, 0);
});

test('absent limit defaults50 and canonical0/1/100 keep explicit columns and original read semantics', async () => {
  const h = harness({ data: [] });
  for (const [query, limit] of [['', 50], ['?limit=0', 0], ['?limit=1', 1], ['?limit=100', 100]]) {
    const response = await h.testRoute.GET(request('/api/v1/test' + query));
    await assertResponse(response, 200);
    assert.equal(h.calls.at(-1).limit, limit);
    assert.equal(h.calls.at(-1).select, 'id,payload,source,created_at');
  }
  assert.equal(h.constructors.length, 1);
  assert.deepEqual(h.constructors[0].config, { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } });
});

test('malformed limits perform zero admin construction and DB queries', async () => {
  const h = harness();
  for (const query of ['?limit=', '?limit=%20', '?limit=-1', '?limit=-0', '?limit=101', '?limit=999999999999999999',
    '?limit=1.5', '?limit=1abc', '?limit=abc', '?limit=NaN', '?limit=Infinity', '?limit=1e2', '?limit=01', '?limit=%2B1',
    '?limit=0x10', '?limit=1&limit=1', '?limit=0&limit=100']) {
    await assertResponse(await h.testRoute.GET(request('/api/v1/test' + query)), 400, 'BAD_REQUEST');
  }
  assert.equal(h.calls.length, 0); assert.equal(h.constructors.length, 0);
});

test('object-only body rejects arrays/null/scalars/malformed/nonfinite before DB', async () => {
  const h = harness();
  for (const body of ['[]', 'null', 'true', '1', '"text"', '{', '', '{"n":NaN}', '{"n":1e309}', '{"n":[-1e309]}']) {
    await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body })), 400, 'BAD_REQUEST');
  }
  assert.equal(h.calls.length, 0); assert.equal(h.constructors.length, 0);
});

test('arbitrary finite diagnostic object remains normalized JSON with source metadata', async () => {
  const h = harness();
  const body = { arbitrary: [true, null, 1.25, { text: 'Unicode 🦉 and \ncontrol permitted' }], actor: 'caller label' };
  await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body, source: 'fixture' })), 201);
  assert.deepEqual(h.calls[0].insert, { payload: body, source: 'fixture' });
  assert.equal(h.calls[0].select, 'id,payload,source,created_at');
  assert.equal(Object.hasOwn(h.calls[0].insert, 'user_id'), false);
});

test('NUL/lone surrogates in all JSON strings and keys refuse while valid pairs survive', async () => {
  const h = harness();
  for (const body of ['{"x":"\\u0000"}', '{"\\u0000":1}', '{"nested":["\\ud800"]}', '{"\\udc00":null}', '{"x":"\\ud800A"}']) {
    await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body })), 400, 'BAD_REQUEST');
  }
  assert.equal(h.calls.length, 0);
  await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body: '{"x":"\\ud83e\\udd89"}' })), 201);
  assert.equal(h.calls[0].insert.payload.x, '🦉');
});

test('original byte cap is enforced incrementally and ignores forged short content length', async () => {
  const h = harness();
  const good = JSON.stringify({ x: 'a'.repeat(65536 - JSON.stringify({ x: '' }).length) });
  assert.equal(encode(good).length, 65536);
  await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body: good })), 201);
  for (const cancelError of [false, true]) {
    const tooLarge = streamRequest([encode(good), encode(' '), encode('must not read')], { cancelError });
    await assertResponse(await h.testRoute.POST(tooLarge.value), 400, 'BAD_REQUEST');
    assert.equal(tooLarge.control.reads, 2); assert.equal(tooLarge.control.cancellations, 1); assert.equal(tooLarge.control.released, true);
  }
  assert.equal(h.calls.length, 1);
});

test('UTF8 byte cap counts multibyte data and malformed UTF8/stream errors are private400', async () => {
  const h = harness();
  const raw = encode(JSON.stringify({ x: 'é'.repeat(32765) }));
  assert.ok(raw.length > 65536);
  for (const streamed of [streamRequest([raw]), streamRequest([new Uint8Array([123,34,120,34,58,34,255,34,125])]),
    streamRequest([], { readError: true })]) {
    await assertResponse(await h.testRoute.POST(streamed.value), 400, 'BAD_REQUEST');
    assert.equal(streamed.control.released, true);
  }
  assert.equal(h.calls.length, 0);
});

test('real Web stream can split an original UTF8 character between chunks', async () => {
  const h = harness(), bytes = encode('{"text":"🦉"}');
  const body = new ReadableStream({ start(controller) { controller.enqueue(bytes.slice(0, 10)); controller.enqueue(bytes.slice(10)); controller.close(); } });
  const req = new Request('https://dashboard.invalid/api/v1/test', { method: 'POST', headers: { 'x-api-key': 'synthetic-api-key' }, body, duplex: 'half' });
  await assertResponse(await h.testRoute.POST(req), 201); assert.equal(h.calls[0].insert.payload.text, '🦉');
});

test('empty stream chunks are not retained/copied and cannot trigger DB before the full body', async () => {
  const h = harness(); let copies = 0, reads = 0, released = false, resolve;
  class EmptyChunk extends Uint8Array { slice() { copies++; throw new Error('Empty chunk must never be copied'); } }
  const empty = new EmptyChunk(0), gate = new Promise(yes => { resolve = yes; });
  const pending = h.testRoute.POST({ url: 'https://dashboard.invalid/api/v1/test', headers: new Headers({ 'x-api-key': 'synthetic-api-key' }),
    body: { getReader() { return {
      async read() {
        reads++;
        if (reads <= 20_000) return { done: false, value: empty };
        if (reads === 20_001) { await gate; return { done: false, value: encode('{"done":true}') }; }
        return { done: true };
      },
      releaseLock() { released = true; },
    }; } },
  });
  await new Promise(setImmediate);
  assert.equal(reads, 20_001); assert.equal(copies, 0); assert.equal(h.constructors.length, 0); assert.equal(h.calls.length, 0);
  resolve(); await assertResponse(await pending, 201);
  assert.equal(copies, 0); assert.equal(released, true); assert.equal(h.calls.length, 1);
});

test('depth16 and total10000 value/key nodes are exact boundaries', async () => {
  const h = harness();
  const layers = depth => { let value = null; for (let i = 0; i < depth; i++) value = { x: value }; return value; };
  await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body: layers(16) })), 201);
  await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body: layers(17) })), 400, 'BAD_REQUEST');
  await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body: { x: Array(9997).fill(0) } })), 201);
  await assertResponse(await h.testRoute.POST(request(undefined, { method: 'POST', body: { x: Array(9998).fill(0) } })), 400, 'BAD_REQUEST');
  assert.equal(h.calls.length, 2);
});

test('source is bounded caller metadata on GET and POST, never principal or provider proof', async () => {
  const h = harness();
  for (const source of ['x'.repeat(129), 'é'.repeat(65), '\u0000', '\n', '\u007f', '\u0080', '\ud800']) {
    const streamed = streamRequest([encode('{}')], { source });
    await assertResponse(await h.testRoute.POST(streamed.value), 400, 'BAD_REQUEST');
    await assertResponse(await h.testRoute.GET({ ...streamed.value, body: null }), 400, 'BAD_REQUEST');
  }
  assert.equal(h.calls.length, 0); assert.equal(h.constructors.length, 0);
  for (const source of [null, '', 'é'.repeat(64)]) {
    await assertResponse(await h.testRoute.POST(streamRequest([encode('{}')], { source }).value), 201);
    assert.equal(h.calls.at(-1).insert.source, source === null || source === '' ? 'unknown' : source);
  }
});

test('sentiment exact fields/finite score/enum and calendar validation reject before DB', async () => {
  const h = harness();
  for (const patch of [{ score: '50' }, { score: -1 }, { score: 101 }, { sentiment: 'BULLISH' }, { summary: '' }, { summary: ' \n ' },
    { key_factors: null }, { key_factors: [1] }, { date: null }, { date: '2026-02-29' }, { date: '1900-02-29' },
    { date: '2026-13-01' }, { date: '2026-04-31' }, { date: '0000-01-01' }, { date: '2026-01-00' }, { date: '2026-1-01' }, { unknown: true }]) {
    await assertResponse(await h.sentimentRoute.POST(request('/api/v1/sentiment', { method: 'POST', body: { ...SENTIMENT, ...patch } })), 400, 'BAD_REQUEST');
  }
  await assertResponse(await h.sentimentRoute.POST(request('/api/v1/sentiment', { method: 'POST', body: JSON.stringify(SENTIMENT).replace('75', '1e309') })), 400, 'BAD_REQUEST');
  assert.equal(h.calls.length, 0); assert.equal(h.constructors.length, 0);
});

test('sentiment score uses integer values without fraction rounding or token/sign restrictions', async () => {
  const rejected = harness();
  for (const score of [0.1, 75.5, 99.9, -0.1, 100.1, true, false, '75', null]) {
    await assertResponse(await rejected.sentimentRoute.POST(request('/api/v1/sentiment',
      { method: 'POST', body: { ...SENTIMENT, score } })), 400, 'BAD_REQUEST');
  }
  for (const token of ['1e309', '-1e309']) {
    const body = JSON.stringify(SENTIMENT).replace('75', token);
    await assertResponse(await rejected.sentimentRoute.POST(request('/api/v1/sentiment',
      { method: 'POST', body })), 400, 'BAD_REQUEST');
  }
  assert.equal(rejected.calls.length, 0); assert.equal(rejected.constructors.length, 0);

  const accepted = harness();
  for (const [token, score] of [['0', 0], ['1', 1], ['100', 100], ['1.0', 1], ['1e0', 1], ['-0', 0]]) {
    const body = JSON.stringify(SENTIMENT).replace('75', token);
    await assertResponse(await accepted.sentimentRoute.POST(request('/api/v1/sentiment',
      { method: 'POST', body })), 201);
    assert.equal(accepted.calls.at(-1).insert.score, score);
    assert.equal(Number.isInteger(accepted.calls.at(-1).insert.score), true);
  }
  assert.equal(accepted.calls.length, 6); assert.equal(accepted.constructors.length, 1);
  const negativeZero = accepted.validation.validateSentiment({ ...SENTIMENT, score: -0 });
  assert.equal(Object.is(negativeZero.score, -0), true);
  assert.throws(() => accepted.validation.validateSentiment({ ...SENTIMENT, score: 75.5 }), accepted.errors.ApiInputError);
});

test('Gregorian dates preserve valid low years/leap centuries and omitted UTC date', async () => {
  const h = harness();
  for (const date of [undefined, '0001-01-01', '0099-12-31', '2000-02-29', '2024-02-29', '9999-12-31']) {
    const body = { ...SENTIMENT, ...(date === undefined ? {} : { date }) };
    await assertResponse(await h.sentimentRoute.POST(request('/api/v1/sentiment', { method: 'POST', body })), 201);
    assert.equal(h.calls.at(-1).insert.date, date ?? '2026-10-13');
    assert.equal(h.calls.at(-1).select, 'id,score,sentiment,summary,key_factors,date,source,created_at');
  }
});

test('sentiment UTF8 field and factor limits accept exact bounds and reject one over', async () => {
  const h = harness();
  const good = { ...SENTIMENT, score: 100, summary: 'é'.repeat(2048), key_factors: Array(64).fill('é'.repeat(128)) };
  await assertResponse(await h.sentimentRoute.POST(request('/api/v1/sentiment', { method: 'POST', body: good })), 201);
  for (const body of [{ ...good, summary: good.summary + 'a' }, { ...good, key_factors: [...good.key_factors, 'x'] },
    { ...good, key_factors: [good.key_factors[0] + 'a'] }]) {
    await assertResponse(await h.sentimentRoute.POST(request('/api/v1/sentiment', { method: 'POST', body })), 400, 'BAD_REQUEST');
  }
  assert.equal(h.calls.length, 1);
});

test('lazy admin configuration failures are fixed503 and never use stale cached credentials', async () => {
  const h = harness({ data: [] });
  await assertResponse(await h.testRoute.GET(request()), 200); assert.equal(h.constructors.length, 1);
  h.env.SUPABASE_SERVICE_ROLE_KEY = ''; await assertResponse(await h.testRoute.GET(request()), 503, 'SERVICE_UNAVAILABLE');
  assert.equal(h.calls.length, 1);
  h.env.SUPABASE_SERVICE_ROLE_KEY = 'synthetic-new-service'; h.state.constructorError = true;
  await assertResponse(await h.testRoute.GET(request()), 503, 'SERVICE_UNAVAILABLE'); assert.equal(h.calls.length, 1);
  h.state.constructorError = false; await assertResponse(await h.testRoute.GET(request()), 200);
  await assertResponse(await h.testRoute.GET(request()), 200); assert.equal(h.constructors.length, 3);
  assert.equal(h.calls.length, 3);
  for (const name of ['NEXT_PUBLIC_SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY']) {
    const missing = harness({ env: { [name]: undefined } });
    await assertResponse(await missing.testRoute.GET(request()), 503, 'SERVICE_UNAVAILABLE'); assert.equal(missing.constructors.length, 0);
  }
});

test('validation always precedes missing admin configuration and fixed private failures', async () => {
  const h = harness({ env: { NEXT_PUBLIC_SUPABASE_URL: undefined } });
  await assertResponse(await h.testRoute.GET(request('/api/v1/test?limit=bad')), 400, 'BAD_REQUEST');
  await assertResponse(await h.sentimentRoute.POST(request('/api/v1/sentiment', { method: 'POST', body: {} })), 400, 'BAD_REQUEST');
  assert.equal(h.logs.length, 0); assert.equal(h.constructors.length, 0);
});

test('any23505 is generic409 and other DB/unexpected failures are sanitized500 without retries', async () => {
  const h = harness({ error: { code: '23505', message: 'PRIVATE SYNTHETIC UNIQUE DETAIL', details: 'private payload' } });
  for (const post of [() => h.testRoute.POST(request(undefined, { method: 'POST', body: {} })),
    () => h.sentimentRoute.POST(request('/api/v1/sentiment', { method: 'POST', body: SENTIMENT }))]) {
    const body = await assertResponse(await post(), 409, 'CONFLICT'); assert.doesNotMatch(body.error.message, /date/i);
  }
  assert.equal(h.calls.length, 2);
  h.state.error = { code: 'XX000', message: 'PRIVATE SYNTHETIC DB DETAIL' };
  await assertResponse(await h.testRoute.GET(request()), 500, 'INTERNAL_ERROR');
  h.state.queryError = true; await assertResponse(await h.testRoute.GET(request()), 500, 'INTERNAL_ERROR');
  assert.equal(h.calls.length, 3); assert.doesNotMatch(JSON.stringify(h.logs), /PRIVATE|private payload|service-key/);
});

test('no-error null or wrong-container SDK replies are safe500 after one original request', async () => {
  for (const data of [null, {}, 42, 'PRIVATE SYNTHETIC RESULT', true, undefined]) {
    const h = harness({ data, error: null });
    await assertResponse(await h.testRoute.GET(request()), 500, 'INTERNAL_ERROR');
    assert.equal(h.calls.length, 1); assert.equal(h.constructors.length, 1);
    assert.deepEqual(h.logs, [['Dashboard API failure', 'DATABASE_READ']]);
  }
  for (const data of [null, [], 42, 'PRIVATE SYNTHETIC RESULT', true, undefined]) {
    for (const kind of ['test', 'sentiment']) {
      const h = harness({ data, error: null });
      const response = kind === 'test'
        ? await h.testRoute.POST(request(undefined, { method: 'POST', body: {} }))
        : await h.sentimentRoute.POST(request('/api/v1/sentiment', { method: 'POST', body: SENTIMENT }));
      await assertResponse(response, 500, 'INTERNAL_ERROR');
      assert.equal(h.calls.length, 1); assert.equal(h.constructors.length, 1);
      assert.deepEqual(h.logs, [['Dashboard API failure', 'DATABASE_WRITE']]);
    }
  }
});

test('pure validation helpers retain exact calendar/input boundaries with no service configuration', () => {
  const h = harness({ env: { API_SECRET_KEY: undefined } });
  assert.equal(h.validation.validCalendarDate('2000-02-29'), true); assert.equal(h.validation.validCalendarDate('1900-02-29'), false);
  assert.equal(h.validation.validateLimit(new URLSearchParams()), 50);
  assert.throws(() => h.validation.validateJsonObject({ x: Infinity }), h.errors.ApiInputError);
  assert.throws(() => h.validation.validateJsonObject({ x: '\udc00' }), h.errors.ApiInputError);
  assert.throws(() => h.validation.validateSentiment({ ...SENTIMENT, score: NaN }), h.errors.ApiInputError);
  assert.throws(() => h.validation.validateSentiment({ ...SENTIMENT, summary: '\u0000' }), h.errors.ApiInputError);
  assert.throws(() => h.validation.validateSentiment({ ...SENTIMENT, key_factors: ['\ud800'] }), h.errors.ApiInputError);
  assert.equal(h.constructors.length, 0);
});
