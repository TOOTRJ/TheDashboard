import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const base = new URL('../', import.meta.url);
const read = name => fs.readFileSync(new URL(name, base), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const jsx = (type, props, key) => ({ type, props, key });

// Executes actual local TSX, getters and callbacks. Hook frames and effect/
// timer queues are controlled fixtures, not React DOM, elapsed animation time,
// keyboard/portal behavior, real clipboard, account or browser acceptance.
function harness(component = 'Home', range = '30d') {
  const frames = new Map(), pending = [], timers = new Map(), intervals = new Map(), forbiddenCalls = [];
  let active, timerId = 0, tree;
  const forbidden = name => () => { forbiddenCalls.push(name); throw new Error(`Unexpected ${name}`); };
  const react = {
    useRef(initial) { return react.useState({ current: initial })[0]; },
    useState(initial) {
      const frame = active, slot = frame.cursor++;
      if (!(slot in frame.states)) frame.states[slot] = typeof initial === 'function' ? initial() : initial;
      return [frame.states[slot], next => { frame.states[slot] = typeof next === 'function' ? next(frame.states[slot]) : next; }];
    },
    useEffect(fn, deps) {
      const frame = active, slot = frame.cursor++, old = frame.effects[slot];
      if (!old || !deps || deps.length !== old.deps.length || deps.some((value, index) => !Object.is(value, old.deps[index]))) {
        frame.effects[slot] = { deps: deps ? [...deps] : [], cleanup: undefined };
        pending.push(() => { old?.cleanup?.(); frame.effects[slot].cleanup = fn(); });
      }
    },
  };
  class FixedDate extends Date { constructor(...args) { super(...(args.length ? args : ['2026-10-13T12:00:00Z'])); } }
  const globals = { Date: FixedDate, Math,
    setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; }, clearTimeout: id => timers.delete(id),
    setInterval(fn) { const id = ++timerId; intervals.set(id, fn); return id; }, clearInterval: id => intervals.delete(id),
    fetch: forbidden('network'), Blob: forbidden('artifact'), URL: { createObjectURL: forbidden('download') },
    navigator: { clipboard: { writeText: forbidden('clipboard') } },
    window: { open: forbidden('popup'), location: { assign: forbidden('navigation') } },
    document: { createElement: forbidden('DOM artifact') },
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
  const mock = load('src/lib/mock/data.ts', {}), filters = { dateRange: range, searchQuery: '' };
  function modules(file) {
    const dependencies = { react, 'react/jsx-runtime': { jsx, jsxs: jsx }, '@/lib/mock': mock,
      '@/components/layout/DashboardProvider': { useDashboardFilters: () => filters },
      '@/lib/formatters': { formatShortDate: value => value, formatDateTime: value => value },
    };
    const source = ts.createSourceFile(file, read(file), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    for (const node of source.statements) if (ts.isImportDeclaration(node)) {
      const name = node.moduleSpecifier.text;
      if (name === 'lucide-react' || name === 'recharts' || name.startsWith('@/components/ui/')) {
        dependencies[name] = {};
        for (const item of node.importClause?.namedBindings?.elements ?? []) dependencies[name][item.propertyName?.text ?? item.name.text] = item.name.text;
      }
    }
    return dependencies;
  }
  const exports = {};
  for (const name of ['KpiCards', 'Charts', 'ActivityTable']) {
    const file = `src/components/dashboard/${name}.tsx`;
    exports[name] = load(file, modules(file))[name];
  }
  const file = 'src/app/(dashboard)/page.tsx';
  exports.Home = load(file, { ...modules(file),
    ...Object.fromEntries(['KpiCards', 'Charts', 'ActivityTable'].map(name => [`@/components/dashboard/${name}`, { [name]: exports[name] }])),
  }).default;
  function run(fn, props, key) {
    const previous = active;
    if (!frames.has(key)) frames.set(key, { states: [], effects: [], cursor: 0 });
    active = frames.get(key); active.cursor = 0;
    try { return fn(props); } finally { active = previous; }
  }
  function expand(node, path = 'root') {
    if (Array.isArray(node)) return node.map((child, index) => expand(child, `${path}/${index}`));
    if (!node || typeof node !== 'object') return node;
    if (typeof node.type === 'function') return expand(run(node.type, node.props, `${path}/${node.type.name}/${node.key ?? ''}`), `${path}/body`);
    return { ...node, props: { ...node.props, children: expand(node.props?.children, `${path}/children`) } };
  }
  function render() { tree = expand(run(exports[component], {}, component)); }
  function nodes(node) { return node && typeof node === 'object' ? [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)] : []; }
  function text(node = tree) {
    return nodes(node).flatMap(n => [n.props?.children].flat(Infinity).filter(value => typeof value === 'string' || typeof value === 'number'))
      .join(' ').replace(/\s+/g, ' ').trim();
  }
  function flush() {
    let count = 0;
    do {
      if (++count > 200) throw new Error('Controlled queue did not settle');
      for (const effect of pending.splice(0)) effect();
      const callbacks = [...timers.values()]; timers.clear();
      for (const fn of callbacks) fn();
      render();
    } while (pending.length || timers.size);
  }
  render(); flush();
  return { mock, filters, forbiddenCalls, text, flush,
    all(predicate) { return nodes(tree).filter(predicate); },
    find(predicate) { const node = nodes(tree).find(predicate); assert.ok(node, `Missing element in ${text()}`); return node; },
    click(node) { if (!node.props.disabled) node.props.onClick?.(); render(); flush(); },
    enter(node) { if (!node.props.disabled) node.props.onKeyDown?.({ key: 'Enter', preventDefault() {} }); render(); flush(); },
    changeRange(value) { filters.dateRange = value; render(); flush(); },
    search(value) { filters.searchQuery = value; render(); flush(); },
    rows() { return nodes(tree).filter(n => n.type === 'TableRow' && typeof n.props.onClick === 'function'); },
    dispose() { for (const frame of frames.values()) for (const effect of frame.effects) effect?.cleanup?.(); pending.length = 0; timers.clear(); intervals.clear(); },
  };
}

test('Home and every nested sample surface disclose provenance, fictional activity and local clock', () => {
  const h = harness();
  for (const label of ['All prices, holdings, metrics, charts and activity below are generated or fixed examples',
    'Sample ticker', 'Example holdings', 'Local clock, not quote time:', 'Sample Crypto Prices',
    'Example Holdings Allocation', 'Example Volume by Exchange', 'Sample Activity']) assert.ok(h.text().includes(label), label);
  for (const kpi of h.mock.getKpiSnapshots('30d')) assert.ok(h.text().includes(`Sample ${kpi.title}`));
  assert.doesNotMatch(h.text(), /Live Feed|Your Holdings|Your latest trading activity|Your trading activity distribution/);
  assert.deepEqual(h.forbiddenCalls, []); h.dispose();
});

test('all ranges preserve actual KPI and price values while fixed allocation and volume stay unchanged', () => {
  const h = harness(); let holdings, volume;
  for (const [range, days] of [['7d', 7], ['30d', 30], ['90d', 90]]) {
    h.changeRange(range);
    const kpis = h.mock.getKpiSnapshots(range), cards = h.all(n => n.type === 'Card' && h.text(n).includes('sample change over selected range'));
    assert.equal(cards.length, 4);
    for (const [index, kpi] of kpis.entries()) {
      assert.ok(h.text(cards[index]).includes(kpi.formattedValue));
      assert.deepEqual(clone(h.all(n => n.type === 'LineChart')[index].props.data), clone(kpi.trend));
    }
    const prices = h.all(n => n.type === 'LineChart').at(-1).props.data;
    assert.equal(prices.length, days); assert.deepEqual(clone(prices), clone(h.mock.getCryptoPriceSeries(range)));
    const nextHoldings = clone(h.find(n => n.type === 'Pie').props.data), nextVolume = clone(h.find(n => n.type === 'BarChart').props.data);
    if (!holdings) { holdings = nextHoldings; volume = nextVolume; }
    assert.deepEqual(nextHoldings, holdings); assert.deepEqual(nextVolume, volume);
  }
  assert.deepEqual(h.forbiddenCalls, []); h.dispose();
});

test('all activity ranges and timestamp/total sort directions retain the actual generated rows', () => {
  for (const range of ['7d', '30d', '90d']) {
    const h = harness('ActivityTable', range), data = [...h.mock.getTradeFeed(range)];
    const expected = (key, ascending) => data.toSorted((a, b) => (key === 'total' ? a.total - b.total : Date.parse(a.timestamp) - Date.parse(b.timestamp)) * (ascending ? 1 : -1)).slice(0, 8).map(row => row.id);
    assert.deepEqual(h.rows().map(row => row.key), expected('timestamp', false));
    const sort = label => h.find(n => n.type === 'Button' && h.text(n) === label);
    h.click(sort('Time')); assert.deepEqual(h.rows().map(row => row.key), expected('timestamp', true));
    h.click(sort('Time')); assert.deepEqual(h.rows().map(row => row.key), expected('timestamp', false));
    h.click(sort('Total')); assert.deepEqual(h.rows().map(row => row.key), expected('total', false));
    h.click(sort('Total')); assert.deepEqual(h.rows().map(row => row.key), expected('total', true));
    assert.deepEqual(h.forbiddenCalls, []); h.dispose();
  }
});

test('activity paging, combined global/local search, empty search and range change preserve page resets', () => {
  const h = harness('ActivityTable', '90d'), ordered = [...h.mock.getTradeFeed('90d')];
  const next = () => h.find(n => n.type === 'Button' && n.props['aria-label'] === 'Next page');
  const prev = () => h.find(n => n.type === 'Button' && n.props['aria-label'] === 'Previous page');
  assert.equal(prev().props.disabled, true);
  h.click(next()); assert.deepEqual(h.rows().map(row => row.key), ordered.slice(8, 16).map(row => row.id));
  while (!next().props.disabled) h.click(next());
  assert.deepEqual(h.rows().map(row => row.key), ordered.slice(56).map(row => row.id));
  const last = h.rows().map(row => row.key); h.click(next()); assert.deepEqual(h.rows().map(row => row.key), last);
  h.click(prev()); assert.deepEqual(h.rows().map(row => row.key), ordered.slice(48, 56).map(row => row.id));
  h.search(ordered[0].asset);
  assert.equal(prev().props.disabled, true);
  const input = h.find(n => n.type === 'Input'); input.props.onChange({ target: { value: ordered[0].type } }); h.flush();
  const filtered = [...h.mock.searchTradeFeed(h.mock.searchTradeFeed(ordered, ordered[0].asset), ordered[0].type)];
  assert.ok(filtered.length > 0); assert.deepEqual(h.rows().map(row => row.key), filtered.slice(0, 8).map(row => row.id));
  input.props.onChange({ target: { value: 'fictional-no-match' } }); h.flush();
  assert.equal(h.rows().length, 0); assert.match(h.text(), /No trades match your filters/);
  input.props.onChange({ target: { value: '' } }); h.search('');
  h.click(next()); h.changeRange('7d'); assert.equal(prev().props.disabled, true);
  assert.deepEqual(h.rows().map(row => row.key), [...h.mock.getTradeFeed('7d')].slice(0, 8).map(row => row.id));
  assert.deepEqual(h.forbiddenCalls, []); h.dispose();
});

test('sample dialogs retain actual selected details while fictional copy/explorer have no side effects', () => {
  const h = harness('ActivityTable', '90d'), first = h.mock.getTradeFeed('90d')[0];
  h.click(h.rows()[0]); assert.equal(h.find(n => n.type === 'Dialog').props.open, true);
  assert.match(h.text(), /Sample Trade Details/); assert.match(h.text(), /Fictional Transaction Hash/); assert.match(h.text(), /Fictional Wallet/);
  assert.ok(h.text().includes(first.txHash)); assert.ok(h.text().includes(first.wallet));
  const buttons = h.all(n => n.type === 'Button' && (n.props['aria-label'] === 'Copy unavailable' || h.text(n) === 'Explorer unavailable'));
  assert.equal(buttons.length, 2);
  for (const button of buttons) {
    assert.equal(button.props.disabled, true); assert.equal(button.props.type, 'button');
    assert.equal(button.props.onClick, undefined); assert.equal(button.props.onKeyDown, undefined);
    assert.match(h.text(h.find(n => n.props?.id === button.props['aria-describedby'])), /Copy and explorer actions are unavailable for these fictional, abbreviated identifiers/);
    h.click(button); h.enter(button);
  }
  h.find(n => n.type === 'Dialog').props.onOpenChange(false); h.flush();
  assert.equal(h.find(n => n.type === 'Dialog').props.open, false);
  const trigger = h.all(n => n.type === 'button' && n.props['aria-haspopup'] === 'dialog')[0];
  assert.equal(trigger.props.type, 'button');
  assert.equal(trigger.props['aria-label'], `View sample ${first.type.toLowerCase()} ${first.asset} trade details`);
  let stopped = 0, focused = 0, prevented = 0;
  const element = { isConnected: true, focus() { focused++; } };
  trigger.props.onClick({ currentTarget: element, stopPropagation() { stopped++; } }); h.flush();
  assert.equal(stopped, 1);
  assert.equal(h.find(n => n.type === 'Dialog').props.open, true);
  assert.match(h.text(h.find(n => n.type === 'DialogDescription')), /Generated example with fictional identifiers/);
  h.find(n => n.type === 'DialogContent').props.onCloseAutoFocus({ preventDefault() { prevented++; } });
  assert.equal(prevented, 1); assert.equal(focused, 1);
  const detached = { isConnected: false, focus() { throw new Error('Detached trigger must not receive focus'); } };
  trigger.props.onClick({ currentTarget: detached, stopPropagation() {} }); h.flush();
  h.find(n => n.type === 'DialogContent').props.onCloseAutoFocus({ preventDefault() { throw new Error('Preserve the default fallback'); } });
  assert.deepEqual(h.forbiddenCalls, []); h.dispose();
});
