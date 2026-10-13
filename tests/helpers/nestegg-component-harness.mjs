import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
import { transpile } from './nestegg-harness.mjs';

/** Controlled hook/JSX execution, not a real React renderer or browser acceptance. */
export function componentHarness(path, name, initialProps, replacements = {}) {
  const hooks = [], pending = [];
  let index = 0, tree, dirty = false, props = initialProps;
  const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const memo = (fn, deps) => {
    const i = index++;
    if (!hooks[i] || !same(hooks[i].deps, deps)) hooks[i] = { deps, value: fn() };
    return hooks[i].value;
  };
  const effect = (fn, deps) => {
    const i = index++, old = hooks[i];
    if (!old || !same(old.deps, deps)) {
      hooks[i] = { deps, cleanup: old?.cleanup };
      pending.push(() => { hooks[i].cleanup?.(); hooks[i].cleanup = fn(); });
    }
  };
  const react = {
    useMemo: memo, useCallback: (fn, deps) => memo(() => fn, deps), useRef: value => memo(() => ({ current: value }), []),
    useEffect: effect, useLayoutEffect: effect,
    useState(value) {
      const i = index++;
      hooks[i] ??= { value: typeof value === 'function' ? value() : value };
      return [hooks[i].value, next => {
        const value = typeof next === 'function' ? next(hooks[i].value) : next;
        if (!Object.is(value, hooks[i].value)) { hooks[i].value = value; dirty = true; }
      }];
    },
  };
  const modules = {};
  for (const item of ts.createSourceFile(path, fs.readFileSync(path, 'utf8'), ts.ScriptTarget.Latest).statements) {
    if (!ts.isImportDeclaration(item)) continue;
    const imported = modules[item.moduleSpecifier.text] = {};
    for (const binding of item.importClause?.namedBindings?.elements ?? []) imported[binding.propertyName?.text ?? binding.name.text] = binding.name.text;
  }
  const jsx = (type, props) => ({ type, props });
  Object.assign(modules, { react, 'react/jsx-runtime': { jsx, jsxs: jsx }, ...replacements });
  const component = transpile(path, modules, { window: { setTimeout: () => 0, clearTimeout() {} }, document: { getElementById: () => null } })[name];
  function nodes(n) { return n && typeof n === 'object' ? [n, ...[n.props?.children].flat(Infinity).flatMap(nodes)] : []; }
  function render(runEffects = true) {
    index = 0; dirty = false; tree = component(props);
    if (runEffects) while (pending.length) pending.shift()();
  }
  render();
  return {
    find(predicate) { const node = nodes(tree).find(predicate); assert.ok(node); return node.props; },
    text() { return nodes(tree).flatMap(n => [n.props?.children].flat(Infinity).filter(v => typeof v === 'string' || typeof v === 'number')).join(' '); },
    update(next, runEffects = true) { props = { ...props, ...next }; render(runEffects); },
    render,
    async flush() { for (let i = 0; i < 8; i++) { await new Promise(setImmediate); if (dirty) render(); } },
    dispose() { for (const hook of hooks) hook.cleanup?.(); },
  };
}
