// Synthetic, loopback-only Supabase protocol fixture. Never proxy a request.
import http from 'node:http';
import { createHmac, randomUUID } from 'node:crypto';

export const FIXTURE_KEY = 'dashboard-browser-fixture-public-key';
export const FIXTURE_ADMIN_KEY = 'dashboard-browser-fixture-service-role-fake';
export const FIXTURE_PASSWORD = 'fixture-password';
export const FIXTURE_OWNERS = Object.freeze({
  alice: '10000000-0000-4000-8000-000000000001',
  bob: '20000000-0000-4000-8000-000000000002',
});
const TABLES = new Set(['profiles', 'nestegg_scenarios', 'portfolio_accounts',
  'vn_colonies', 'vn_probes', 'vn_trades', 'vn_generation_stats', 'vn_fitness_snapshots']);
const ERROR = { code: 'FIXTURE_REFUSAL', message: 'Synthetic fixture refused request' };
const MAX_BODY = 65_536;
const MAX_HISTORY = 512;
const MAX_PENDING = 16;

export function createBrowserBackend(defaultInputs) {
  const accounts = new Map();
  const tokens = new Map();
  const refresh = new Map();
  const revoked = new Set();
  const retiredSessions = new Set();
  const history = [];
  const pending = new Map();
  const holds = [];
  let origin, appOrigin, stopped = false;
  for (const [name, id] of Object.entries(FIXTURE_OWNERS)) {
    const user = { id, aud: 'authenticated', role: 'authenticated',
      email: `${name}@dashboard.invalid`, email_confirmed_at: '2026-01-01T00:00:00Z',
      app_metadata: { provider: 'email', providers: ['email'] },
      user_metadata: { full_name: `Fixture ${name}` }, identities: [],
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      is_anonymous: false };
    const savings = name === 'alice' ? [10_000, 70_000] : [800_000];
    accounts.set(id, { user, profile: { id, email: user.email, full_name: `Fixture ${name}`,
      avatar_url: null, portfolio_goal: 1_000_000, portfolio_goal_year: 2050,
      created_at: user.created_at, updated_at: user.updated_at },
      plans: savings.map((amount, i) => ({ id: `${name}-plan-${i + 1}`, user_id: id,
        name: `${name.toUpperCase()} PRIVATE PLAN ${i + 1}`,
        inputs: { ...structuredClone(defaultInputs), currentSavings: amount,
          monthlyContribution: name === 'alice' ? 300 : 1_500 },
        market_scenario: 'base', updated_at: `2026-01-0${i + 1}T00:00:00Z` })),
      portfolio: [{ id: `${name}-portfolio`, user_id: id, name: `${name} fixture account`,
        balance: savings[0], updated_at: user.updated_at }] });
  }

  function session(owner, logicalSession = randomUUID()) {
    const user = accounts.get(owner)?.user;
    if (!user || retiredSessions.has(logicalSession)) return null;
    const now = Math.floor(Date.now() / 1000), nonce = randomUUID();
    const parts = [Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url'),
      Buffer.from(JSON.stringify({ iss: `${origin}/auth/v1`, sub: owner,
        aud: 'authenticated', exp: now + 3600, iat: now, role: 'authenticated',
        email: user.email, session_id: logicalSession, jti: nonce, aal: 'aal1',
        app_metadata: user.app_metadata, user_metadata: user.user_metadata })).toString('base64url')];
    const signature = createHmac('sha256', 'synthetic-fixture-signing-key-no-cloud-authority')
      .update(parts.join('.')).digest('base64url');
    const token = `${parts.join('.')}.${signature}`, renewal = `fixture-refresh-${nonce}`;
    tokens.set(token, { owner, logicalSession }); refresh.set(renewal, { owner, logicalSession });
    return { access_token: token, token_type: 'bearer', expires_in: 3600,
      expires_at: now + 3600, refresh_token: renewal, user: structuredClone(user) };
  }

  function ownerOf(req) {
    const bearer = /^Bearer (.+)$/.exec(req.headers.authorization ?? '')?.[1];
    const identity = bearer && !revoked.has(bearer) ? tokens.get(bearer) : null;
    return identity && !retiredSessions.has(identity.logicalSession) ? identity.owner : null;
  }
  function send(res, status, value, extra = {}) {
    if (res.destroyed || res.writableEnded) return;
    res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store',
      'access-control-allow-origin': appOrigin ?? origin,
      'access-control-expose-headers': 'content-range', ...extra });
    res.end(JSON.stringify(value));
  }
  async function body(req) {
    let bytes = 0, text = '';
    for await (const chunk of req) {
      bytes += chunk.length;
      if (bytes > MAX_BODY) throw new Error('Body bound');
      text += chunk;
    }
    return text ? JSON.parse(text) : {};
  }
  function trace(method, path, owner) {
    if (history.length >= MAX_HISTORY) throw new Error('Fixture request bound');
    const entry = { sequence: history.length + 1, method, path, owner: owner ?? null };
    history.push(entry); return entry;
  }
  function deliver(req, res, entry, status, value, headers = {}) {
    // Capture the original response BEFORE the delay. Delayed A cannot become B.
    const captured = structuredClone(value);
    const hold = holds.findIndex(h => h.method === req.method && h.path === entry.path
      && (!h.owner || h.owner === entry.owner));
    if (hold < 0) return send(res, status, captured, headers);
    holds.splice(hold, 1);
    if (pending.size >= MAX_PENDING) return send(res, 503, ERROR);
    const id = randomUUID();
    const timer = setTimeout(() => { pending.delete(id); send(res, 504, ERROR); }, 90_000);
    pending.set(id, { id, entry, status, value: captured, headers, res, timer });
    res.once('close', () => { clearTimeout(timer); pending.delete(id); });
  }

  const server = http.createServer(async (req, res) => {
    try {
      if (stopped || req.headers.host !== new URL(origin).host
        || (req.headers.origin && req.headers.origin !== appOrigin
          && req.headers.origin !== origin)) return send(res, 403, ERROR);
      const url = new URL(req.url, origin), path = url.pathname;
      if (req.method === 'OPTIONS') {
        res.writeHead(204, { 'access-control-allow-origin': appOrigin ?? origin,
          'access-control-allow-methods': 'GET,POST,PATCH,DELETE,OPTIONS',
          'access-control-allow-headers': 'authorization,apikey,content-type,prefer,range,x-client-info,accept-profile,content-profile,x-supabase-api-version' });
        return res.end();
      }
      if (path === '/__fixture/status' && req.method === 'GET') {
        return send(res, 200, { synthetic: true, history: structuredClone(history),
          pending: [...pending.values()].map(p => ({ id: p.id, ...p.entry })), holds: structuredClone(holds) });
      }
      if (path === '/__fixture/control' && req.method === 'POST') {
        if (req.headers.apikey !== FIXTURE_KEY) return send(res, 403, ERROR);
        const control = await body(req);
        if (control.action === 'hold' && ['GET', 'PATCH', 'POST', 'DELETE'].includes(control.method)
          && typeof control.path === 'string' && /^\/(rest\/v1\/(nestegg_scenarios|profiles|portfolio_accounts)|auth\/v1\/(user|logout))$/.test(control.path)
          && (!control.owner || accounts.has(control.owner)) && holds.length < MAX_PENDING) {
          holds.push({ method: control.method, path: control.path, owner: control.owner ?? null });
          return send(res, 200, { accepted: true });
        }
        if (control.action === 'release' && typeof control.id === 'string' && pending.has(control.id)) {
          const p = pending.get(control.id); pending.delete(control.id); clearTimeout(p.timer);
          send(p.res, p.status, p.value, p.headers);
          return send(res, 200, { accepted: true });
        }
        return send(res, 400, ERROR);
      }
      if (req.headers.apikey === FIXTURE_ADMIN_KEY) {
        if (req.headers.authorization !== `Bearer ${FIXTURE_ADMIN_KEY}`
          || req.method !== 'GET' || path !== '/rest/v1/test_events'
          || url.searchParams.get('limit') !== '0') return send(res, 403, ERROR);
        trace(req.method, path, null); return send(res, 200, [], { 'content-range': '*/0' });
      }
      if (req.headers.apikey !== FIXTURE_KEY) return send(res, 401, ERROR);
      const owner = ownerOf(req), entry = trace(req.method, path, owner);
      if (path === '/auth/v1/token' && req.method === 'POST') {
        const input = await body(req);
        let id, logicalSession;
        if (url.searchParams.get('grant_type') === 'password') {
          const name = /^(alice|bob)@dashboard\.invalid$/.exec(input.email ?? '')?.[1];
          id = name && input.password === FIXTURE_PASSWORD ? FIXTURE_OWNERS[name] : null;
        } else if (url.searchParams.get('grant_type') === 'refresh_token') {
          const prior = refresh.get(input.refresh_token);
          id = prior?.owner; logicalSession = prior?.logicalSession;
        }
        const result = id ? session(id, logicalSession) : null;
        return send(res, result ? 200 : 400, result ?? ERROR);
      }
      if (!owner) return send(res, 401, ERROR);
      if (path === '/auth/v1/user' && req.method === 'GET') {
        return deliver(req, res, entry, 200, accounts.get(owner).user);
      }
      if (path === '/auth/v1/logout' && req.method === 'POST') {
        const token = req.headers.authorization.slice(7);
        revoked.add(token);
        retiredSessions.add(tokens.get(token).logicalSession);
        return deliver(req, res, entry, 200, {});
      }
      const table = /^\/rest\/v1\/([^/]+)$/.exec(path)?.[1];
      if (!TABLES.has(table)) return send(res, 404, ERROR);
      const account = accounts.get(owner);
      const filter = table === 'profiles' ? 'id' : 'user_id';
      const ownerFilter = url.searchParams.get(filter);
      if ((req.method !== 'POST' && !table.startsWith('vn_') && ownerFilter !== `eq.${owner}`)
        || (ownerFilter && ownerFilter !== `eq.${owner}`)) return send(res, 403, ERROR);
      let rows = table === 'profiles' ? [account.profile]
        : table === 'nestegg_scenarios' ? account.plans
        : table === 'portfolio_accounts' ? account.portfolio : [];
      const idFilter = url.searchParams.get('id');
      if (table !== 'profiles' && idFilter) rows = rows.filter(r => `eq.${r.id}` === idFilter);
      if (req.method === 'POST' && table === 'nestegg_scenarios') {
        const input = await body(req);
        if (input.user_id !== owner || typeof input.name !== 'string' || !input.inputs
          || !['base', 'conservative', 'aggressive'].includes(input.market_scenario)) return send(res, 403, ERROR);
        const row = { id: randomUUID(), user_id: owner, name: input.name,
          inputs: structuredClone(input.inputs), market_scenario: input.market_scenario,
          updated_at: new Date().toISOString() };
        account.plans.push(row); rows = [row];
      } else if (req.method === 'PATCH' && table === 'nestegg_scenarios' && idFilter) {
        const input = await body(req);
        if (Object.keys(input).some(k => !['name', 'inputs', 'market_scenario', 'updated_at'].includes(k))) return send(res, 403, ERROR);
        for (const row of rows) Object.assign(row, structuredClone(input));
      } else if (req.method === 'DELETE' && table === 'nestegg_scenarios' && idFilter) {
        const selected = new Set(rows.map(r => r.id));
        account.plans = account.plans.filter(r => !selected.has(r.id)); rows = [];
      } else if (req.method !== 'GET') return send(res, 405, ERROR);
      const single = (req.headers.accept ?? '').includes('application/vnd.pgrst.object+json');
      const count = rows.length;
      const headers = { 'content-range': count ? `0-${count - 1}/${count}` : '*/0' };
      return deliver(req, res, entry, 200, single ? rows[0] ?? null : rows, headers);
    } catch { send(res, 400, ERROR); }
  });
  return {
    async start() {
      await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
      origin = `http://127.0.0.1:${server.address().port}`; return origin;
    },
    setAppOrigin(value) {
      const url = new URL(value);
      if (url.protocol !== 'http:' || !/^dashboard-fixture-[0-9a-f-]+\.localhost$/.test(url.hostname)
        || url.origin !== value) throw new Error('Fixture app must use its isolated localhost hostname');
      appOrigin = value;
    },
    async stop() {
      stopped = true;
      for (const p of pending.values()) { clearTimeout(p.timer); send(p.res, 503, ERROR); }
      pending.clear(); server.closeAllConnections();
      await new Promise(resolve => server.close(resolve));
    },
  };
}
