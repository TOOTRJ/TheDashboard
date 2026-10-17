import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { createNesteggWorkspaceScope } from '../../src/lib/nestegg/session-scope.ts';
import { sessionIdentity } from '../../src/lib/auth/session-guard.ts';
export const A='00000000-0000-0000-0000-000000000001',B='00000000-0000-0000-0000-000000000002';
export const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
export function transpile(file,modules,globals={}) {
 const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,
 {exports,require:name=>{assert.ok(Object.hasOwn(modules,name),name);return modules[name];},...globals});return exports;
}
export const account=(owner,name=`Private ${owner}`,balance=123)=>({id:`account-${owner}`,name,balance,updatedAt:'2026-10-13'});
const token=(id,refresh=0)=>`fake.${Buffer.from(JSON.stringify({session_id:id,refresh})).toString('base64url')}.signature`;
export function harness() {
 let auth={user:{id:A},session:{user:{id:A},access_token:token('A-1')},loading:false};
 const parent={hooks:[],index:0,layout:[],effects:[],active:true};let frame=null,key=null,tree,dirty=false,retiredWrites=0,uuid=0;
 const toasts=[],visibleToasts=new Map(),dismissed=[],calls=[],controllers={},accounts=new Map([[A,[account(A)]],[B,[account(B,'B private',456)]]]);
 const same=(a,b)=>a&&b&&a.length===b.length&&a.every((x,i)=>Object.is(x,b[i]));
 const memo=(fn,deps)=>{const i=frame.index++;if(!frame.hooks[i]||!same(frame.hooks[i].deps,deps))frame.hooks[i]={deps,value:fn()};return frame.hooks[i].value;};
 const effect=(fn,deps,layout)=>{const f=frame,i=f.index++;if(!f.hooks[i]||!same(f.hooks[i].deps,deps)){const old=f.hooks[i];f.hooks[i]={deps,cleanup:old?.cleanup,run:fn,layout};(layout?f.layout:f.effects).push(()=>{f.hooks[i].cleanup?.();f.hooks[i].cleanup=fn();});}};
 const react={useMemo:memo,useRef:value=>memo(()=>({current:value}),[]),useLayoutEffect:(fn,deps)=>effect(fn,deps,true),useEffect:(fn,deps)=>effect(fn,deps,false),
 useState(value){const f=frame,i=f.index++;f.hooks[i]??={value:typeof value==='function'?value():value};return [f.hooks[i].value,next=>{if(!f.active){retiredWrites++;return;}const result=typeof next==='function'?next(f.hooks[i].value):next;if(!Object.is(result,f.hooks[i].value)){f.hooks[i].value=result;dirty=true;}}];}};
 const modules={};const source=ts.createSourceFile('page.tsx',fs.readFileSync('src/app/(dashboard)/portfolio/page.tsx','utf8'),ts.ScriptTarget.Latest);
 for(const stmt of source.statements)if(ts.isImportDeclaration(stmt)){const name=stmt.moduleSpecifier.text;modules[name]={};for(const x of stmt.importClause?.namedBindings?.elements??[])modules[name][x.propertyName?.text??x.name.text]=x.name.text;}
 const jsx=(type,props,key)=>({type,props,key});modules.react=react;modules['react/jsx-runtime']={jsx,jsxs:jsx};modules['next/link']={default:'Link'};
 modules['@/components/auth/AuthProvider']={useAuth:()=>auth};modules['@/lib/auth/session-guard']={sessionIdentity};modules['@/lib/nestegg/session-scope']={createNesteggWorkspaceScope};
 modules.sonner={toast:{...Object.fromEntries(['success','error'].map(name=>[name,(...args)=>{const entry={name,args};toasts.push(entry);visibleToasts.set(args[1].id,entry);return args[1].id;}])),dismiss:id=>{dismissed.push(id);const entry=visibleToasts.get(id);visibleToasts.delete(id);entry?.args[1].onDismiss?.({id});}}};
 modules['@/lib/formatters']={formatCurrency:String};modules['@/lib/nestegg/future-value']={computeRequiredMonthlySavings:()=>1};
 async function invoke(kind,scope,args,fallback){const call={kind,scope,args};calls.push(call);return controllers[kind]?controllers[kind](call):fallback();}
 modules['@/lib/portfolio/portfolio-supabase']={
 fetchPortfolioAccounts:scope=>invoke('read',scope,[],()=>accounts.get(scope.ownerId)),
 fetchPortfolioGoal:scope=>invoke('readGoal',scope,[],()=>({goal:scope.ownerId===A?100:200,goalYear:2040})),
 insertPortfolioAccount:(name,balance,scope)=>invoke('add',scope,[name,balance],()=>({...account(scope.ownerId,name,balance),id:`added-${calls.length}`})),
 updatePortfolioAccount:(id,fields,scope)=>invoke('edit',scope,[id,fields],()=>({...account(scope.ownerId,fields.name,fields.balance),id})),
 deletePortfolioAccount:(id,scope)=>invoke('delete',scope,[id],()=>true),
 updatePortfolioGoal:(amount,year,scope)=>invoke('goal',scope,[amount,year],()=>true),
 };
 const page=transpile('src/app/(dashboard)/portfolio/page.tsx',modules,{crypto:{randomUUID:()=>`opaque-${++uuid}`},console});
 function retire(){if(frame){for(const hook of frame.hooks)hook.cleanup?.();frame.active=false;}}
 function render(){const previous=frame;frame=parent;parent.index=0;const outer=page.default();frame=previous;
  if(outer.type!==page.PortfolioWorkspace){retire();frame=null;key=null;tree=outer;dirty=false;return;}
  if(key!==outer.key){retire();key=outer.key;frame={hooks:[],index:0,layout:[],effects:[],active:true};}
  frame.index=0;dirty=false;tree=page.PortfolioWorkspace(outer.props);while(frame.layout.length)frame.layout.shift()();while(frame.effects.length)frame.effects.shift()();}
 function nodes(n){if(!n||typeof n!=='object')return [];return [n,...[n.props?.children].flat(Infinity).flatMap(x=>nodes(x))];}
 function text(n=tree){return nodes(n).flatMap(x=>[x.props?.children].flat(Infinity).filter(v=>typeof v==='string'||typeof v==='number')).join(' ');}
 render();return {toasts,visibleToasts,dismissed,unrelatedToast(){visibleToasts.set('outside',{name:'external',args:['Unrelated notification',{id:'outside'}]});},autoClose(id){const entry=visibleToasts.get(id);visibleToasts.delete(id);entry?.args[1].onAutoClose?.({id});},calls,controllers,accounts,text,nodes:()=>nodes(tree),
 input:id=>nodes(tree).find(n=>n.props?.id===id)?.props,
 button:label=>nodes(tree).find(n=>n.type==='Button'&&(n.props['aria-label']===label||text(n).trim()===label))?.props,
 key:()=>key,retiredWrites:()=>retiredWrites,
 async flush(){for(let i=0;i<10;i++){await new Promise(setImmediate);if(dirty)render();}},
 change(owner,login=`${owner}-1`){auth={user:owner?{id:owner}:null,session:owner?{user:{id:owner},access_token:token(login)}:null,loading:false};render();},
 refresh(){auth={...auth,session:{...auth.session,access_token:token('A-1',1)}};render();},
 strictCycle(){for(const hook of frame.hooks)hook.cleanup?.();for(const layout of [true,false])for(const hook of frame.hooks)if(hook.run&&hook.layout===layout)hook.cleanup=hook.run();},
 strictReplace(){retire();frame=null;key=null;render();},dispose:retire,
 };
}
