import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const ts = require('typescript');

// Controlled hooks/JSX/action execution. This is not a React DOM renderer,
// native keyboard/portal implementation, actual account or browser acceptance.
function pageHarness(page) {
  const path = new URL(`../src/app/(dashboard)/${page}/page.tsx`, import.meta.url);
  const states = [], effects = [];
  let index = 0, tree;
  const forbidden = name => () => { effects.push(name); throw new Error(`Unexpected ${name} in unavailable action`); };
  const react = { useState(initial) {
    const slot = index++;
    if (!(slot in states)) states[slot] = typeof initial === 'function' ? initial() : initial;
    return [states[slot], next => { states[slot] = typeof next === 'function' ? next(states[slot]) : next; }];
  } };
  const jsx = (type, props) => ({ type, props });
  const modules = { react, 'react/jsx-runtime': { jsx, jsxs: jsx },
    sonner: { toast: { success: forbidden('success toast'), error: forbidden('error toast') } } };
  const imports = ts.createSourceFile(path.pathname, fs.readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  for (const statement of imports.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    const name = statement.moduleSpecifier.text;
    if (name === 'react' || name === 'sonner') continue;
    assert.ok(name === 'lucide-react' || name.startsWith('@/components/ui/') || name === '@/components/theme/ThemeToggle', name);
    modules[name] = {};
    for (const item of statement.importClause?.namedBindings?.elements ?? []) {
      modules[name][item.propertyName?.text ?? item.name.text] = item.name.text;
    }
  }
  const output = ts.transpileModule(fs.readFileSync(path, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const exports = {};
  const context = vm.createContext({ exports, module: { exports },
    require(name) { assert.ok(name in modules, `Unsupported page dependency: ${name}`); return modules[name]; },
    setTimeout: forbidden('timer'), setInterval: forbidden('interval'), fetch: forbidden('network'),
    Blob: forbidden('artifact'), URL: { createObjectURL: forbidden('download') },
    document: { createElement: forbidden('DOM artifact'), location: { assign: forbidden('navigation') } },
    window: { open: forbidden('popup'), fetch: forbidden('network'),
      localStorage: { setItem: forbidden('storage'), removeItem: forbidden('storage') } },
  });
  vm.runInContext(output, context, { timeout: 1000 });
  function render() { index = 0; tree = exports.default(); }
  function nodes(node) {
    return node && typeof node === 'object' ? [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)] : [];
  }
  function text(node = tree) {
    return nodes(node).flatMap(n => [n.props?.children].flat(Infinity).filter(v => typeof v === 'string' || typeof v === 'number')).join(' ').replace(/\s+/g, ' ').trim();
  }
  render();
  return {
    effects, render, text,
    all(predicate) { return nodes(tree).filter(predicate); },
    find(predicate) { const found = nodes(tree).find(predicate); assert.ok(found); return found; },
    click(node) { if (!node.props.disabled) node.props.onClick?.({ preventDefault() {} }); render(); },
    enter(node) { if (!node.props.disabled) { node.props.onKeyDown?.({ key: 'Enter', preventDefault() {} }); node.props.onClick?.({ preventDefault() {} }); } render(); },
    select(node, value) { assert.equal(node.props.disabled, undefined); node.props.onValueChange(value); render(); },
  };
}

function assertUnavailable(h, node) {
  assert.equal(node.props.disabled, true);
  assert.equal(node.props.type, 'button');
  assert.equal(node.props.onClick, undefined, 'Unsupported mutation has no callable success handler');
  const reason = h.find(n => n.props?.id === node.props['aria-describedby']);
  assert.match(h.text(reason), /not available|cannot be saved|cannot be downloaded/i);
  h.click(node); h.enter(node);
  assert.deepEqual(h.effects, []);
}

test('Reports marks the overview and preview as samples without generation or integration claims', () => {
  const h = pageHarness('reports');
  assert.match(h.text(), /All figures and trades on this page are examples/);
  assert.match(h.text(), /Sample Summary/);
  assert.match(h.text(), /Sample Activity/);
  assert.doesNotMatch(h.text(), /Last generated|TurboTax|CoinTracker|Koinly|FIFO|LIFO|ready for download|generated successfully/i);
  assert.equal(h.all(n => n.type === 'form').length, 0);
  for (const button of h.all(n => n.type === 'Button' && n.props.disabled)) assertUnavailable(h, button);
});

test('Every report sample opens and closes without a fake completion, timer, artifact or request', () => {
  const h = pageHarness('reports');
  const previews = h.all(n => n.type === 'Button' && h.text(n).includes('Sample Preview'));
  assert.equal(previews.length, 4);
  for (const button of previews) {
    h.enter(button);
    assert.equal(h.find(n => n.type === 'Sheet').props.open, true);
    assert.match(h.text(h.find(n => n.type === 'SheetTitle')), /^Sample .* Preview$/);
    assert.match(h.text(h.find(n => n.type === 'SheetDescription')), /No account data/);
    assertUnavailable(h, h.find(n => n.type === 'Button' && n.props['aria-describedby'] === 'preview-report-unavailable'));
    h.find(n => n.type === 'Sheet').props.onOpenChange(false); h.render();
    assert.equal(h.find(n => n.type === 'Sheet').props.open, false);
  }
  assert.deepEqual(h.effects, []);
});

test('Settings profile and wallet previews cannot submit, save, connect or disconnect', () => {
  const h = pageHarness('settings');
  assert.match(h.text(), /values below are examples, not your account settings/);
  assert.match(h.text(), /Example Profile/);
  assert.match(h.text(), /Sample addresses and balances/);
  assert.equal(h.all(n => n.type === 'form').length, 0);
  for (const field of h.all(n => n.type === 'Input')) {
    assert.equal(field.props.readOnly, true);
    assert.equal(field.props.onChange, undefined);
    h.enter(field);
  }
  const buttons = h.all(n => n.type === 'Button' && /Save Profile|Connect unavailable|Disconnect unavailable/.test(h.text(n)));
  assert.equal(buttons.length, 4);
  for (const button of buttons) assertUnavailable(h, button);
});

test('Sample notification and trading controls are unavailable while the real ThemeToggle is preserved', () => {
  const h = pageHarness('settings');
  assert.equal(h.all(n => n.type === 'ThemeToggle').length, 1);
  const switches = h.all(n => n.type === 'Switch');
  assert.equal(switches.length, 3);
  for (const item of switches) {
    assert.equal(item.props.disabled, true); assert.equal(item.props.onCheckedChange, undefined);
    assert.match(item.props['aria-label'], /^Sample/);
    assert.ok(h.find(n => n.props?.id === item.props['aria-describedby']));
  }
  for (const item of h.all(n => n.type === 'Select' && n.props.disabled)) assert.equal(item.props.onValueChange, undefined);
  assert.equal(h.all(n => n.type === 'Select' && n.props.disabled).length, 2);
  assert.match(h.text(), /these values do not configure the bot/);
  assertUnavailable(h, h.find(n => n.type === 'Button' && h.text(n).includes('Save Preferences')));
});

test('Choosing an example tier changes only its preview and never the example current plan or billing', () => {
  const h = pageHarness('settings');
  const current = h.text(h.find(n => n.props?.id === 'example-current-plan'));
  assert.match(h.text(), /Example current plan/);
  assert.match(h.text(), /No account billing information has been loaded/);
  assert.match(h.text(), /Choosing a preview does not change your subscription or begin payment/);
  for (const choice of ['Elite', 'Whale', 'Pro']) {
    h.select(h.find(n => n.type === 'Select' && !n.props.disabled), choice);
    assert.match(h.text(), new RegExp(`Selected preview: ${choice}`));
    assert.equal(h.text(h.find(n => n.props?.id === 'example-current-plan')), current);
    assertUnavailable(h, h.find(n => n.type === 'Button' && h.text(n).includes('Upgrade unavailable')));
    assert.deepEqual(h.effects, []);
  }
  assert.doesNotMatch(h.text(), /Next billing|Unlimited API calls|Upgrade initiated|Confirm Upgrade/);
});
