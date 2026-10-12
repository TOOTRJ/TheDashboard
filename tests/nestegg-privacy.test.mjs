import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { createNesteggWorkspaceScope } from '../src/lib/nestegg/session-scope.ts';
import { sessionIdentity } from '../src/lib/auth/session-guard.ts';
const A='00000000-0000-0000-0000-000000000001',B='00000000-0000-0000-0000-000000000002';
function transpile(path,modules,globals={}) {
 const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,
  {exports,require:n=>{assert.ok(Object.hasOwn(modules,n),n);return modules[n];},...globals});return exports;
}
const constants=transpile('src/lib/nestegg/constants.ts',{});
const token=(session,refresh=0)=>`synthetic.${Buffer.from(JSON.stringify({session_id:session,refresh})).toString('base64url')}.signature`;
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const mc=(mark,paths=200)=>({paths,successRate:0.5,chanceRunOut:0.5,worstCaseDepletionAge:null,bandSeries:[],mark});
const row=(owner,savings)=>({id:`plan-${owner}`,name:`Private ${owner}`,inputs:{...constants.DEFAULT_NESTEGG_INPUTS,currentSavings:savings},marketScenario:'base',updatedAt:'2026-10-12'});
function harness(options={}) {
 let auth={user:{id:A},session:{user:{id:A},access_token:token('A-1')},loading:false};
 const parent={hooks:[],index:0,layout:[],effects:[],active:true};
 let frame=null,tree,key=null,dirty=false,retiredWrites=0,now=0,timerId=0;
 const timers=new Map(),toasts=[],reads=[],saves=[],mcCalls=[],drafts=new Map();
 const plans=new Map([[A,[row(A,500123)]],[B,[]]]),portfolio=new Map([[A,800456],[B,0]]);
 const later=(fn,delay)=>{const id=++timerId;timers.set(id,{fn,at:now+delay});return id;};
 const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>Object.is(v,b[i]));
 const memo=(fn,deps)=>{const i=frame.index++;if(!frame.hooks[i]||!same(frame.hooks[i].deps,deps))frame.hooks[i]={deps,value:fn()};return frame.hooks[i].value;};
 const effect=(fn,deps,layout)=>{const f=frame,i=f.index++;if(!f.hooks[i]||!same(f.hooks[i].deps,deps)){
  const old=f.hooks[i];f.hooks[i]={deps,cleanup:old?.cleanup};(layout?f.layout:f.effects).push(()=>{f.hooks[i].cleanup?.();f.hooks[i].cleanup=fn();});}};
 const react={useMemo:memo,useCallback:(fn,deps)=>memo(()=>fn,deps),useRef:v=>memo(()=>({current:v}),[]),
  useEffect:(fn,deps)=>effect(fn,deps,false),useLayoutEffect:(fn,deps)=>effect(fn,deps,true),
  useState(v){const f=frame,i=f.index++;f.hooks[i]??={value:typeof v==='function'?v():v};return [f.hooks[i].value,next=>{
   if(!f.active){retiredWrites++;return;}const value=typeof next==='function'?next(f.hooks[i].value):next;
   if(!Object.is(value,f.hooks[i].value)){f.hooks[i].value=value;dirty=true;}}];}};
 const modules={};const ast=ts.createSourceFile('page.tsx',fs.readFileSync('src/app/(dashboard)/nestegg/page.tsx','utf8'),ts.ScriptTarget.Latest);
 for(const statement of ast.statements)if(ts.isImportDeclaration(statement)){
  const name=statement.moduleSpecifier.text;modules[name]={};
  for(const item of statement.importClause?.namedBindings?.elements??[])modules[name][item.propertyName?.text??item.name.text]=item.name.text;
 }
 const jsx=(type,props,key)=>({type,props,key});modules.react=react;modules['react/jsx-runtime']={jsx,jsxs:jsx};
 modules['@/components/auth/AuthProvider']={useAuth:()=>auth};
 modules['@/lib/auth/session-guard']={sessionIdentity};modules['@/lib/nestegg/session-scope']={createNesteggWorkspaceScope};
 modules.sonner={toast:Object.fromEntries(['success','error','message'].map(name=>[name,(...args)=>toasts.push({name,args})]))};
 modules['@/lib/nestegg/constants']=constants;
 modules['@/lib/nestegg/storage']={defaultDraftState:()=>({inputs:{...constants.DEFAULT_NESTEGG_INPUTS},marketScenario:'base',compareOverlay:false}),
  loadNesteggDraft:owner=>({draft:drafts.get(owner)??null,unavailable:!!options.storageDisabled}),
  saveNesteggDraft:(owner,draft)=>{saves.push({owner,draft});if(options.storageDisabled)return false;drafts.set(owner,draft);return true;}};
 modules['@/lib/nestegg/scenarios-supabase']={
  async fetchNesteggScenariosFromSupabase(scope){reads.push({kind:'plans',scope});if(options.hydrationGate?.owner===scope.ownerId)await options.hydrationGate.gate.promise;
   if(options.refreshGate&&reads.filter(r=>r.kind==='plans'&&r.scope.ownerId===A).length>1)await options.refreshGate.promise;
   return plans.get(scope.ownerId);},
  async updateNesteggScenarioInSupabase(id,inputs,scenario,extra,scope){reads.push({kind:'save',scope,inputs});if(options.saveGate)await options.saveGate.promise;return {...row(scope.ownerId,inputs.currentSavings),id,name:extra.name};}};
 modules['@/lib/portfolio/portfolio-supabase']={async fetchPortfolioTotal(scope){reads.push({kind:'portfolio',scope});return portfolio.get(scope.ownerId);},
  async fetchPortfolioGoal(scope){reads.push({kind:'goal',scope});return {goal:scope.ownerId===A?987654:0,goalYear:2040};}};
 modules['@/lib/nestegg/projections']={runProjection:inputs=>({series:[],nestEggAtRetirement:inputs.currentSavings,heroMessage:'fixed',heroTone:'neutral'}),
  mergeComparisonSeries:()=>[],buildRetirementCashflowYears:()=>[],planHorizonAge:()=>90};
 modules['@/lib/nestegg/insights-engine']={buildNesteggInsights:()=>[]};modules['@/lib/nestegg/future-value']={buildGoalProjectionSeries:()=>({})};
 modules['@/lib/formatters']={formatCurrency:String};
 modules['@/lib/nestegg/monte-carlo']={async runMonteCarloBatched(inputs,scenario,args){
  const call={inputs,args};mcCalls.push(call);if(options.mcGate&&(args.paths===1100||options.holdLight))await options.mcGate.promise;
  args.onProgress?.(0.5);return mc(inputs.currentSavings,args.paths);},runMonteCarloScenarioComparisonBatched:async()=>[]};
 const page=transpile('src/app/(dashboard)/nestegg/page.tsx',modules,{crypto:{randomUUID:()=>`opaque-workspace-${++timerId}`},window:{setTimeout:later,clearTimeout:id=>timers.delete(id)},console});
 function retire(){if(frame){for(const h of frame.hooks)h.cleanup?.();frame.active=false;}}
 function render(){
  const previous=frame;frame=parent;parent.index=0;const outer=page.default();frame=previous;
  if(outer.type!==page.NesteggWorkspace){retire();frame=null;key=null;tree=outer;dirty=false;return;}
  if(key!==outer.key){retire();key=outer.key;frame={hooks:[],index:0,layout:[],effects:[],active:true};}
  frame.index=0;dirty=false;tree=page.NesteggWorkspace(outer.props);
  while(frame.layout.length)frame.layout.shift()();while(frame.effects.length)frame.effects.shift()();
 }
 function nodes(n){if(!n||typeof n!=='object')return [];return [n,...[n.props?.children].flat(Infinity).flatMap(nodes)];}
 function text(n=tree){return nodes(n).flatMap(n=>[n.props?.children].flat(Infinity).filter(v=>typeof v==='string'||typeof v==='number')).join(' ');}
 render();
 return {toasts,reads,saves,mcCalls,drafts,plans,portfolio,
  component:name=>nodes(tree).find(n=>n.type===name)?.props,
  async flush(){for(let i=0;i<8;i++){await new Promise(setImmediate);if(dirty)render();}},
  change(owner,session=`${owner}-1`){auth={user:owner?{id:owner}:null,session:owner?{user:{id:owner},access_token:token(session)}:null,loading:false};render();},
  changeOpaque(owner,value){auth={user:{id:owner},session:{user:{id:owner},access_token:value},loading:false};render();},
  refreshToken(){auth={...auth,session:{...auth.session,access_token:token('A-1',1)}};render();},
  clickFull(){const button=nodes(tree).find(n=>n.type==='Button'&&n.props.onClick&&text(n).includes('Run full analysis'));assert.ok(button);return button.props.onClick();},
  advance(ms){now+=ms;for(const[id,t]of [...timers])if(t.at<=now){timers.delete(id);t.fn();}if(dirty)render();},
  text,workspaceKey:()=>key,workspaceProps:()=>{const previous=frame;frame=parent;parent.index=0;const outer=page.default();frame=previous;return outer.props;},retiredWrites:()=>retiredWrites,dispose:retire,
 };
}
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
 const react={useMemo:memo,useEffect(fn,deps){const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){hooks[i]={deps};effects.push(fn);}},
  useState(v){const i=index++;hooks[i]??={value:v};return [hooks[i].value,next=>{hooks[i].value=next;}];}};
 const path='src/components/nestegg/NesteggSavedPlanTabsToolbar.tsx',modules={};
 for(const statement of ts.createSourceFile(path,fs.readFileSync(path,'utf8'),ts.ScriptTarget.Latest).statements)if(ts.isImportDeclaration(statement)){
  const name=statement.moduleSpecifier.text;modules[name]={};for(const item of statement.importClause?.namedBindings?.elements??[])modules[name][item.propertyName?.text??item.name.text]=item.name.text;
 }
 modules.react=react;modules['react/jsx-runtime']={jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
 modules['@/components/auth/AuthProvider']={useAuth:()=>({user:{id:A},loading:false})};modules['@/lib/utils']={cn:()=>''};
 modules.sonner={toast:Object.fromEntries(['success','error','message'].map(name=>[name,(...args)=>toasts.push(args)]))};
 modules['@/lib/nestegg/scenarios-supabase']={async insertNesteggScenarioToSupabase(name,inputs,scenario,request){calls.push(['insert',request]);await gate.promise;return row(A,500);},
  async deleteNesteggScenarioFromSupabase(id,request){calls.push(['delete',request]);await gate.promise;return true;},
  async updateNesteggScenarioNameInSupabase(id,name,request){calls.push(['rename',request]);await gate.promise;return row(A,500);}};
 const {NesteggSavedPlanTabsToolbar}=transpile(path,modules,{window:{setTimeout:()=>0,clearTimeout(){}},document:{getElementById:()=>null}});
 const props={workspaceScope:scope,inputs:row(A,500).inputs,marketScenario:'base',cloudScenarios:[row(A,500)],activeSavedScenarioId:`plan-${A}`,
  onLoadScenario:()=>calls.push(['load']),onRefreshCloud:async()=>calls.push(['refresh']),onCloudSaved:()=>calls.push(['saved']),onCloudScenarioDeleted:async()=>calls.push(['deleted'])};
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
