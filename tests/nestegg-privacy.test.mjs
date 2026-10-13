import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';
import { createNesteggWorkspaceScope } from '../src/lib/nestegg/session-scope.ts';
import * as resultIdentity from '../src/lib/nestegg/result-identity.ts';
import { harness, transpile, A, B, deferred, row } from './helpers/nestegg-harness.mjs';
test('A to B with no saved plans removes private inputs, goals, results and child state before paint',async()=>{
 const h=harness();await h.flush();assert.equal(h.component('NesteggExportMenu').inputs.currentSavings,800456);
 assert.equal(h.component('NesteggExportMenu').monteCarlo.mark,800456);
 h.change(B);assert.equal(h.component('NesteggExportMenu'),undefined);assert.match(h.text(),/Loading/);
 await h.flush();assert.equal(h.component('NesteggExportMenu').inputs.currentSavings,0);
 assert.equal(h.component('NesteggExportMenu').monteCarlo.mark,0);assert.equal(h.component('NesteggSavedPlanTabsToolbar').cloudScenarios.length,0);
 assert.equal(h.retiredWrites(),0);h.dispose();
});
test('late A hydration cannot publish and old autosave cannot write a B draft',async()=>{
 const gate=deferred(),h=harness({hydrationGate:{owner:A,gate}});h.change(B);await h.flush();gate.resolve();await h.flush();h.advance(400);
 assert.equal(h.component('NesteggExportMenu').inputs.currentSavings,0);assert.ok(h.saves.every(s=>s.owner===B));assert.equal(h.retiredWrites(),0);h.dispose();
 const ready=harness();await ready.flush();ready.change(B);await ready.flush();ready.advance(400);
 assert.ok(ready.saves.every(s=>s.owner===B));ready.dispose();
});
test('late refresh and active-plan save replies from A cannot update B or emit old success',async()=>{
 const refresh=deferred(),save=deferred(),h=harness({refreshGate:refresh,saveGate:save});await h.flush();
 const toolbar=h.component('NesteggSavedPlanTabsToolbar'),pendingRefresh=toolbar.onRefreshCloud(),pendingSave=toolbar.onSaveActivePlan();
 h.change(B);await h.flush();refresh.resolve();save.resolve();await Promise.all([pendingRefresh,pendingSave]);await h.flush();
 assert.equal(h.component('NesteggSavedPlanTabsToolbar').cloudScenarios.length,0);assert.equal(h.component('NesteggExportMenu').inputs.currentSavings,0);
 assert.equal(h.toasts.length,0);assert.equal(h.retiredWrites(),0);h.dispose();
});
test('logout then same-account new login rejects old MC result/progress and removes exports while signed out',async()=>{
 const gate=deferred(),h=harness({mcGate:gate});await h.flush();const old=h.clickFull();
 h.change(null);assert.equal(h.component('NesteggExportMenu'),undefined);assert.match(h.text(),/Sign in/);
 h.portfolio.set(A,73);h.plans.set(A,[]);h.change(A,'A-2');await h.flush();gate.resolve();await old;await h.flush();
 assert.equal(h.component('NesteggExportMenu').inputs.currentSavings,73);assert.equal(h.component('NesteggExportMenu').monteCarlo.mark,73);
 assert.equal(h.retiredWrites(),0);assert.equal(h.toasts.length,0);h.dispose();
});
test('ordinary token refresh keeps a stable login workspace and owner-scoped inputs',async()=>{
 const h=harness();await h.flush();const before=h.reads.length;h.component('NesteggQuickWhatIf').onPatch({currentSavings:64});await h.flush();
 h.refreshToken();await h.flush();assert.equal(h.component('NesteggExportMenu').inputs.currentSavings,64);assert.equal(h.reads.length,before);
 h.advance(400);assert.equal(h.saves.at(-1).owner,A);h.dispose();
});
test('disabled device storage shows an explicit warning without claiming local save',async()=>{
 const h=harness({storageDisabled:true});await h.flush();assert.match(h.text(),/browser draft could not be saved or read/);
 h.advance(400);assert.match(h.text(),/cloud plan saving is separate/);h.dispose();
});
function toolbar(gate) {
 const hooks=[],effects=[],calls=[],toasts=[];let index=0,tree;
 const scope=createNesteggWorkspaceScope(A,'session:A-1');scope.activate();
 const same=(a,b)=>a&&b&&a.length===b.length&&a.every((x,i)=>Object.is(x,b[i]));
 const memo=(fn,deps)=>{const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={deps,value:fn()};return hooks[i].value;};
 const react={useMemo:memo,useRef:v=>memo(()=>({current:v}),[]),useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn);}},
  useState(v){const i=index++;hooks[i]??={value:v};return [hooks[i].value,next=>{hooks[i].value=next;}];}};
 const path='src/components/nestegg/NesteggSavedPlanTabsToolbar.tsx',modules={};
 for(const statement of ts.createSourceFile(path,fs.readFileSync(path,'utf8'),ts.ScriptTarget.Latest).statements)if(ts.isImportDeclaration(statement)){
  const name=statement.moduleSpecifier.text;modules[name]={};for(const item of statement.importClause?.namedBindings?.elements??[])modules[name][item.propertyName?.text??item.name.text]=item.name.text;
 }
 modules['@/lib/nestegg/result-identity']=resultIdentity;modules.react=react;modules['react/jsx-runtime']={jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
 modules['@/components/auth/AuthProvider']={useAuth:()=>({user:{id:A},loading:false})};modules['@/lib/utils']={cn:()=>''};
 modules.sonner={toast:Object.fromEntries(['success','error','message'].map(name=>[name,(...args)=>toasts.push(args)]))};
 modules['@/lib/nestegg/scenarios-supabase']={async insertNesteggScenarioToSupabase(name,inputs,scenario,request){calls.push(['insert',request]);await gate.promise;return row(A,500);},
  async deleteNesteggScenarioFromSupabase(id,request){calls.push(['delete',request]);await gate.promise;return true;},
  async updateNesteggScenarioNameInSupabase(id,name,request){calls.push(['rename',request]);await gate.promise;return row(A,500);}};
 const {NesteggSavedPlanTabsToolbar}=transpile(path,modules,{window:{setTimeout:()=>0,clearTimeout(){}},document:{getElementById:()=>null}});
 const props={workspaceScope:scope,inputs:row(A,500).inputs,marketScenario:'base',cloudScenarios:[row(A,500)],activeSavedScenarioId:`plan-${A}`,
  captureWorkspaceIntent:()=>({generation:1,isCurrent:()=>scope.isCurrent()}),onCloudRenamed:()=>calls.push(['renamed']),onLoadScenario:()=>calls.push(['load']),onRefreshCloud:async()=>calls.push(['refresh']),onCloudSaved:()=>calls.push(['saved']),onCloudScenarioDeleted:async()=>calls.push(['deleted'])};
 function render(){index=0;tree=NesteggSavedPlanTabsToolbar(props);while(effects.length)effects.shift()();}
 function nodes(n){if(!n||typeof n!=='object')return [];return [n,...[n.props?.children].flat(Infinity).flatMap(nodes)];}
 render();return {calls,toasts,scope,click(match){const n=nodes(tree).find(match);assert.ok(n);n.props.onClick({preventDefault(){},stopPropagation(){}});render();}};
}
test('late save-new toolbar response cannot publish A inputs or toast into a replacement workspace',async()=>{
 const gate=deferred(),h=toolbar(gate);h.click(n=>n.type==='Button'&&[n.props.children].flat().some(c=>c==='Duplicate'));
 h.click(n=>n.type==='Button'&&n.props.onClick&&[n.props.children].flat().some(c=>c==='Create saved plan'));
 h.scope.dispose();gate.resolve();await new Promise(setImmediate);assert.deepEqual(h.calls.map(c=>c[0]),['insert']);assert.equal(h.toasts.length,0);
});
test('late delete toolbar response cannot call refresh/deletion callbacks after logout',async()=>{
 const gate=deferred(),h=toolbar(gate);h.click(n=>n.props['aria-label']===`Delete Private ${A}`);
 h.click(n=>n.type==='Button'&&[n.props.children].flat().some(c=>c==='Delete plan'));
 h.scope.dispose();gate.resolve();await new Promise(setImmediate);assert.deepEqual(h.calls.map(c=>c[0]),['delete']);assert.equal(h.toasts.length,0);
});

test('React workspace keys and direct props exclude raw fallback tokens without a global token cache',async()=>{
 const h=harness();await h.flush();h.changeOpaque(A,'opaque-bearer-private-fixture');await h.flush();
 const first=h.workspaceKey();assert.match(first,/^opaque-workspace-/);assert.ok(!first.includes(A));
 assert.ok(!JSON.stringify(h.workspaceProps()).includes('opaque-bearer-private-fixture'));
 h.changeOpaque(A,'refreshed-opaque-private-fixture');await h.flush();assert.notEqual(h.workspaceKey(),first);
 h.change(null);h.change(A,'A-2');await h.flush();assert.notEqual(h.workspaceKey(),first);h.dispose();
});
