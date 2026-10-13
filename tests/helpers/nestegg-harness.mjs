import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { createNesteggWorkspaceScope } from '../../src/lib/nestegg/session-scope.ts';
import { sessionIdentity } from '../../src/lib/auth/session-guard.ts';
import * as resultIdentity from '../../src/lib/nestegg/result-identity.ts';
export const A='00000000-0000-0000-0000-000000000001',B='00000000-0000-0000-0000-000000000002';
export function transpile(path,modules,globals={}) {
 const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,
  {exports,require:n=>{assert.ok(Object.hasOwn(modules,n),n);return modules[n];},...globals});return exports;
}
export const constants=transpile('src/lib/nestegg/constants.ts',{});
const token=(session,refresh=0)=>`synthetic.${Buffer.from(JSON.stringify({session_id:session,refresh})).toString('base64url')}.signature`;
export const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
export const mc=(mark,paths=200)=>({paths,successRate:0.5,chanceRunOut:0.5,worstCaseDepletionAge:null,bandSeries:[],mark});
export const row=(owner,savings)=>({id:`plan-${owner}`,name:`Private ${owner}`,inputs:{...constants.DEFAULT_NESTEGG_INPUTS,currentSavings:savings},marketScenario:'base',updatedAt:'2026-10-12'});
export function harness(options={}) {
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
 modules['@/lib/nestegg/constants']=constants;modules['@/lib/nestegg/result-identity']=resultIdentity;
 modules['@/lib/nestegg/storage']={defaultDraftState:()=>({inputs:{...constants.DEFAULT_NESTEGG_INPUTS},marketScenario:'base',compareOverlay:false}),
  loadNesteggDraft:owner=>({draft:drafts.get(owner)??null,unavailable:!!options.storageDisabled}),
  saveNesteggDraft:(owner,draft)=>{saves.push({owner,draft});if(options.storageDisabled)return false;drafts.set(owner,draft);return true;}};
 modules['@/lib/nestegg/scenarios-supabase']={
  async fetchNesteggScenariosFromSupabase(scope){reads.push({kind:'plans',scope});if(options.planRead)return options.planRead(scope,reads.filter(r=>r.kind==='plans'&&r.scope.ownerId===scope.ownerId).length);if(options.hydrationGate?.owner===scope.ownerId)await options.hydrationGate.gate.promise;
   if(options.refreshGate&&reads.filter(r=>r.kind==='plans'&&r.scope.ownerId===A).length>1)await options.refreshGate.promise;
   return plans.get(scope.ownerId);},
  async updateNesteggScenarioInSupabase(id,inputs,scenario,extra,scope){const call={kind:'save',scope,inputs,id,scenario,name:extra.name};reads.push(call);if(options.saveController)return options.saveController(call);if(options.saveGate)await options.saveGate.promise;return {...row(scope.ownerId,inputs.currentSavings),id,name:extra.name};}};
 modules['@/lib/portfolio/portfolio-supabase']={async fetchPortfolioTotal(scope){reads.push({kind:'portfolio',scope});return portfolio.get(scope.ownerId);},
  async fetchPortfolioGoal(scope){reads.push({kind:'goal',scope});return {goal:scope.ownerId===A?987654:0,goalYear:2040};}};
 modules['@/lib/nestegg/projections']={runProjection:inputs=>({series:[],nestEggAtRetirement:inputs.currentSavings,heroMessage:'fixed',heroTone:'neutral'}),
  mergeComparisonSeries:()=>[],buildRetirementCashflowYears:()=>[],planHorizonAge:()=>90};
 modules['@/lib/nestegg/insights-engine']={buildNesteggInsights:()=>[]};modules['@/lib/nestegg/future-value']={buildGoalProjectionSeries:()=>({})};
 modules['@/lib/formatters']={formatCurrency:String};
 modules['@/lib/nestegg/monte-carlo']={NESTEGG_MC_MODEL_VERSION:'model-v1',NESTEGG_MC_SEED_POLICY:'seed-v1',NESTEGG_MC_COMPARE_PATHS:350,async runMonteCarloBatched(inputs,scenario,args){
  const call={inputs,scenario,args};mcCalls.push(call);if(options.mcController)return options.mcController(call);if(options.mcGate&&(args.paths===1100||options.holdLight))await options.mcGate.promise;
  args.onProgress?.(0.5);return mc(inputs.currentSavings,args.paths);},runMonteCarloScenarioComparisonBatched:async(inputs,labels,args)=>options.comparisonController?options.comparisonController({inputs,labels,args}):[]};
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
  component:name=>nodes(tree).find(n=>n.type===name)?.props,components:name=>nodes(tree).filter(n=>n.type===name).map(n=>n.props),input:id=>nodes(tree).find(n=>n.props?.id===id)?.props,
  async flush(){for(let i=0;i<8;i++){await new Promise(setImmediate);if(dirty)render();}},
  change(owner,session=`${owner}-1`){auth={user:owner?{id:owner}:null,session:owner?{user:{id:owner},access_token:token(session)}:null,loading:false};render();},
  changeOpaque(owner,value){auth={user:{id:owner},session:{user:{id:owner},access_token:value},loading:false};render();},
  refreshToken(){auth={...auth,session:{...auth.session,access_token:token('A-1',1)}};render();},
  clickFull(){const button=nodes(tree).find(n=>n.type==='Button'&&n.props.onClick&&/Run full analysis|Re-run analysis|Running…/.test(text(n)));assert.ok(button);return button.props.onClick();},
  advance(ms){now+=ms;for(const[id,t]of [...timers])if(t.at<=now){timers.delete(id);t.fn();}if(dirty)render();},
  text,workspaceKey:()=>key,workspaceProps:()=>{const previous=frame;frame=parent;parent.index=0;const outer=page.default();frame=previous;return outer.props;},retiredWrites:()=>retiredWrites,dispose:retire,
 };
}
