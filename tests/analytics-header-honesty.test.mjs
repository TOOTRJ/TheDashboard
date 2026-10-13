import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const base = new URL('../', import.meta.url);
const read = name => fs.readFileSync(new URL(name, base), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const jsx = (type, props) => ({ type, props });
const dashboardPaths = ['/', '/analytics', '/strategies', '/nestegg', '/probes', '/reports', '/settings', '/portfolio', '/docs'];

// Executes actual TSX and the actual local mock getters with controlled hooks,
// JSX and callbacks. This is not React DOM, Radix portal/keyboard behavior,
// hydration, an authenticated account, a native download or browser acceptance.
function harness({ pathname = '/', dateRange = '30d', component = 'Header' } = {}) {
  const calls = [], forbiddenCalls = [], states = [], effects = [], seenEffects = new Set();
  let cursor = 0, tree;
  const forbidden = name => () => { forbiddenCalls.push(name); throw new Error(`Unexpected ${name}`); };
  const react = {
    useState(initial) {
      const slot = cursor++;
      if (!(slot in states)) states[slot] = typeof initial === 'function' ? initial() : initial;
      return [states[slot], next => { states[slot] = typeof next === 'function' ? next(states[slot]) : next; }];
    },
    useMemo(fn) { cursor++; return fn(); },
    useEffect(fn) {
      const slot = cursor++;
      if (!seenEffects.has(slot)) { seenEffects.add(slot); effects.push(fn); }
    },
  };
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : ['2026-10-13T12:00:00Z'])); }
  }
  const globals = { Date: FixedDate, Math,
    setTimeout: forbidden('timer'), setInterval: forbidden('interval'), fetch: forbidden('network'),
    Blob: forbidden('artifact'), URL: { createObjectURL: forbidden('download'), revokeObjectURL: forbidden('download cleanup') },
    document: { createElement: forbidden('DOM artifact') },
    window: { open: forbidden('popup'), location: { assign: forbidden('navigation') } },
  };
  function load(name, modules) {
    const output = ts.transpileModule(read(name), { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText;
    const exports = {};
    vm.runInNewContext(output, { exports, ...globals, require(name) {
      assert.ok(Object.hasOwn(modules, name), `Unexpected dependency ${name}`); return modules[name];
    } }, { filename: name, timeout: 1000 });
    return exports;
  }
  const mock = load('src/lib/mock/data.ts', {});
  const filters = { dateRange, searchQuery: '', dateRangeOptions: mock.getDateRangeOptions(),
    setDateRange(value) { calls.push(['dateRange', value]); filters.dateRange = value; },
    setSearchQuery(value) { calls.push(['searchQuery', value]); filters.searchQuery = value; },
  };
  const common = { react, 'react/jsx-runtime': { jsx, jsxs: jsx } };
  function uiModules(file) {
    const modules = { ...common };
    const source = ts.createSourceFile(file, read(file), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    for (const node of source.statements) {
      if (!ts.isImportDeclaration(node)) continue;
      const name = node.moduleSpecifier.text;
      if (name === 'lucide-react' || name === 'recharts' || name.startsWith('@/components/ui/')) {
        modules[name] = {};
        for (const item of node.importClause?.namedBindings?.elements ?? []) {
          modules[name][item.propertyName?.text ?? item.name.text] = item.name.text;
        }
      }
    }
    return modules;
  }
  const theme = { current: 'dark', setTheme(value) { calls.push(['theme', value]); theme.current = value; } };
  const themeFile = 'src/components/theme/ThemeToggle.tsx';
  const themeExports = load(themeFile, { ...uiModules(themeFile), 'next-themes': {
    useTheme: () => ({ theme: theme.current, setTheme: theme.setTheme }),
  } });
  const file = component === 'Analytics' ? 'src/app/(dashboard)/analytics/page.tsx'
    : component === 'ThemeToggle' ? themeFile : 'src/components/layout/Header.tsx';
  const exported = component === 'ThemeToggle' ? themeExports : load(file, {
    ...uiModules(file), '@/lib/mock': mock, '@/lib/formatters': { formatShortDate: value => value },
    '@/components/layout/DashboardProvider': { useDashboardFilters: () => filters },
    '@/components/theme/ThemeToggle': themeExports,
    '@/components/auth/AuthProvider': { useAuth: () => ({
      user: { email: 'alice@example.invalid', user_metadata: {} }, profile: { full_name: 'Fixture User' },
      async signOut() { calls.push(['signOut']); },
    }) },
    'next/navigation': {
      usePathname: () => pathname,
      useRouter: () => ({ push: value => calls.push(['push', value]), refresh: () => calls.push(['refresh']) }),
    },
  });
  function render() {
    cursor = 0;
    tree = component === 'Header' ? exported.Header({ onOpenMobileNav: () => calls.push(['mobileNavigation']) })
      : component === 'ThemeToggle' ? exported.ThemeToggle() : exported.default();
  }
  function nodes(node) {
    return node && typeof node === 'object' ? [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)] : [];
  }
  function text(node = tree) {
    return nodes(node).flatMap(n => [n.props?.children].flat(Infinity).filter(v => typeof v === 'string' || typeof v === 'number'))
      .join(' ').replace(/\s+/g, ' ').trim();
  }
  render();
  return { calls, forbiddenCalls, filters, mock, themeExports, render, text, nodes,
    mount() { for (const effect of effects.splice(0)) effect(); render(); },
    all(predicate) { return nodes(tree).filter(predicate); },
    find(predicate) { const node = nodes(tree).find(predicate); assert.ok(node, `Missing controlled element in: ${text()}`); return node; },
    async request(node, key = 'click') {
      if (!node.props.disabled) {
        if (key === 'Enter') node.props.onKeyDown?.({ key, preventDefault() {} });
        else await node.props.onClick?.({ preventDefault() {} });
      }
      render();
    },
  };
}

test('Analytics labels generated charts and fixed values without unsupported advice or AI results', () => {
  const h = harness({ component: 'Analytics' });
  for (const label of ['Sample Analytics', 'Sample Portfolio Growth', 'Sample P&L Trend', 'Sample Win Rate Trend',
    'Sample Exchange Volume', 'Fixed Sample Stats', 'Example Risk/Reward']) assert.ok(h.text().includes(label), label);
  assert.match(h.text(), /Local sample charts and fixed example metrics/);
  assert.match(h.text(), /No account or trading bot performance is loaded/);
  assert.match(h.text(), /fixed examples.*do not change with the sample range/i);
  assert.match(h.text(), /not calculated from these charts or your trades/);
  assert.doesNotMatch(h.text(), /AI-generated|Strong Uptrend|increasing position|SOL Momentum|12\.4%|outperforming|strongest performance/i);
  assert.deepEqual(h.calls, []); assert.deepEqual(h.forbiddenCalls, []);
});

test('Analytics export is visibly unavailable with no click/Enter/artifact/download handler', async () => {
  const h = harness({ component: 'Analytics' });
  const button = h.find(n => n.type === 'Button' && h.text(n) === 'Export CSV unavailable');
  assert.equal(button.props.disabled, true); assert.equal(button.props.type, 'button');
  assert.equal(button.props.onClick, undefined); assert.equal(button.props.onKeyDown, undefined);
  assert.match(h.text(h.find(n => n.props?.id === button.props['aria-describedby'])), /sample charts are not connected to an account export/);
  await h.request(button); await h.request(button, 'Enter');
  assert.deepEqual(h.calls, []); assert.deepEqual(h.forbiddenCalls, []);
});

test('actual local sample date ranges change dated chart series while exchange volume and stats remain fixed', () => {
  const h = harness({ component: 'Analytics' });
  let originalVolume, originalStats;
  for (const [range, length] of [['7d', 7], ['30d', 30], ['90d', 90]]) {
    h.filters.dateRange = range; h.render();
    const charts = h.all(n => n.type === 'AreaChart');
    assert.equal(charts.length, 3);
    for (const [index, getter] of ['getPortfolioSeries', 'getPnlSeries', 'getWinRateSeries'].entries()) {
      assert.equal(charts[index].props.data.length, length);
      assert.deepEqual(clone(charts[index].props.data), clone(h.mock[getter](range)));
    }
    const volume = clone(h.find(n => n.type === 'BarChart').props.data);
    const stats = h.text(h.find(n => n.type === 'Card' && h.text(n).includes('Fixed Sample Stats')));
    if (!originalVolume) { originalVolume = volume; originalStats = stats; }
    assert.deepEqual(volume, originalVolume); assert.equal(stats, originalStats);
  }
  assert.deepEqual(h.forbiddenCalls, []);
});

test('Header scopes search only to sample activity and date selection only to actual sample consumers', () => {
  for (const pathname of [...dashboardPaths, '/analytics/other']) {
    const h = harness({ pathname }); h.mount();
    assert.equal(h.all(n => n.type === 'Input').length, pathname === '/' ? 1 : 0, pathname);
    assert.equal(h.all(n => n.type === 'Select').length, pathname === '/' || pathname === '/analytics' ? 1 : 0, pathname);
    if (pathname === '/' || pathname === '/analytics') {
      const trigger = h.find(n => n.type === 'SelectTrigger');
      assert.equal(trigger.props['aria-label'], 'Sample date range');
      assert.match(h.text(h.find(n => n.props?.id === trigger.props['aria-describedby'])), /Allocation, exchange-volume and fixed stat examples stay unchanged/);
    }
    if (pathname === '/strategies') {
      assert.match(h.text(), /Strategy Concepts/); assert.match(h.text(), /Example strategies and independent charts; historical evaluation unavailable/);
    }
    if (pathname === '/analytics') assert.equal(h.text(h.find(n => n.type === 'h1')), 'Sample Analytics');
    assert.deepEqual(h.calls, []); assert.deepEqual(h.forbiddenCalls, []);
  }
});

test('Header admits only exact sample date options and retains working activity search callback', () => {
  for (const pathname of ['/', '/analytics']) {
    const h = harness({ pathname }); h.mount();
    const choices = h.all(n => n.type === 'SelectItem').map(n => n.props.value);
    assert.deepEqual(choices, ['7d', '30d', '90d']);
    for (const range of choices) { h.find(n => n.type === 'Select').props.onValueChange(range); h.render(); assert.equal(h.filters.dateRange, range); }
    const accepted = clone(h.calls);
    for (const value of ['', '7d ', ' 7d', '7D', 'all', 'private-invalid', 7, null, {}]) {
      h.find(n => n.type === 'Select').props.onValueChange(value); h.render();
    }
    assert.deepEqual(h.calls, accepted); assert.equal(h.filters.dateRange, '90d');
    if (pathname === '/') {
      const input = h.find(n => n.type === 'Input');
      assert.equal(input.props['aria-label'], 'Search sample activity');
      input.props.onChange({ target: { value: 'SOL' } }); h.render();
      assert.equal(h.filters.searchQuery, 'SOL'); assert.deepEqual(h.calls.at(-1), ['searchQuery', 'SOL']);
      const matches = h.mock.searchTradeFeed(h.mock.getTradeFeed('90d'), h.filters.searchQuery);
      assert.ok(matches.length > 0); assert.ok(matches.every(row => row.asset === 'SOL'));
    }
    assert.deepEqual(h.forbiddenCalls, []);
  }
});

test('Header removes fabricated notification count and keeps missing account actions disabled with a reason', async () => {
  const h = harness(); h.mount();
  assert.match(h.text(), /Notifications unavailable/);
  assert.equal(h.all(n => n.type === 'Bell' || n.props?.['aria-label'] === 'Notifications').length, 0);
  const unavailable = h.all(n => n.type === 'DropdownMenuItem' && /unavailable/.test(h.text(n)));
  assert.equal(unavailable.length, 3);
  for (const node of unavailable) {
    assert.equal(node.props.disabled, true); assert.equal(node.props.onClick, undefined); assert.equal(node.props.onSelect, undefined);
    assert.match(h.text(h.find(n => n.props?.id === node.props['aria-describedby'])), /Profile, wallet settings and API key management are not available/);
    await h.request(node); await h.request(node, 'Enter');
  }
  assert.deepEqual(h.calls, []); assert.deepEqual(h.forbiddenCalls, []);
});

test('Header preserves real mobile navigation, ThemeToggle component and sign-out callback order on every route', async () => {
  for (const pathname of dashboardPaths) {
    const h = harness({ pathname }); h.mount();
    assert.equal(h.all(n => n.type === h.themeExports.ThemeToggle).length, 1);
    await h.request(h.find(n => n.type === 'Button' && n.props['aria-label'] === 'Open navigation menu'));
    await h.request(h.find(n => n.type === 'DropdownMenuItem' && h.text(n) === 'Sign Out'));
    assert.deepEqual(h.calls, [['mobileNavigation'], ['signOut'], ['push', '/login'], ['refresh']]);
    assert.deepEqual(h.forbiddenCalls, []);
  }
});

test('the unchanged actual ThemeToggle still dispatches Light, Dark and System choices', async () => {
  const h = harness({ component: 'ThemeToggle' }); h.mount();
  for (const [label, theme] of [['Light', 'light'], ['Dark', 'dark'], ['System', 'system']]) {
    await h.request(h.find(n => n.type === 'DropdownMenuItem' && h.text(n).includes(label)));
    assert.deepEqual(h.calls.at(-1), ['theme', theme]);
  }
  assert.equal(h.calls.length, 3); assert.deepEqual(h.forbiddenCalls, []);
});
