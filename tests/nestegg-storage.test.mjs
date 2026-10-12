import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { createNesteggWorkspaceScope } from '../src/lib/nestegg/session-scope.ts';
import { sessionIdentity } from '../src/lib/auth/session-guard.ts';
const A='00000000-0000-0000-0000-000000000001', B='00000000-0000-0000-0000-000000000002';
function load(path,modules={},globals={}) {
 const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
  {exports,require:n=>{assert.ok(Object.hasOwn(modules,n),n);return modules[n];},...globals});return exports;
}
const constants=load('src/lib/nestegg/constants.ts');
function store(initial={}) {
 const values=new Map(Object.entries(initial)),reads=[];let disabled=false;
 const storage={getItem:k=>{reads.push(k);if(disabled)throw Error('blocked');return values.get(k)??null;},
  setItem:(k,v)=>{if(disabled)throw Error('quota');values.set(k,v);},removeItem:k=>{if(disabled)throw Error('blocked');values.delete(k);}};
 return {values,reads,disable:()=>{disabled=true;},api:load('src/lib/nestegg/storage.ts',{'./constants':constants},{window:{localStorage:storage}})};
}
const draft={inputs:{...constants.DEFAULT_NESTEGG_INPUTS,currentSavings:654321},marketScenario:'aggressive',compareOverlay:true};
test('owner drafts never adopt the previous shared draft or another owner data',()=>{
 const s=store({'nestegg-draft-v1':JSON.stringify(draft)});
 assert.equal(s.api.loadNesteggDraft(A).draft,null);assert.equal(s.api.loadNesteggDraft(B).draft,null);
 assert.ok(s.api.saveNesteggDraft(A,draft));assert.equal(s.api.loadNesteggDraft(A).draft.inputs.currentSavings,654321);
 assert.equal(s.api.loadNesteggDraft(B).draft,null);assert.ok(s.values.has('nestegg-draft-v1'));
 assert.ok(s.reads.every(k=>k!=='nestegg-draft-v1'));
 assert.ok(s.api.saveNesteggDraft(B,{...draft,inputs:{...draft.inputs,currentSavings:25}}));
 assert.ok(s.api.clearNesteggDraft(A));assert.equal(s.api.loadNesteggDraft(A).draft,null);
 assert.equal(s.api.loadNesteggDraft(B).draft.inputs.currentSavings,25);
});
test('wrong owner envelope, anonymous identities and malformed drafts are refused',()=>{
 const s=store();assert.ok(s.api.saveNesteggDraft(A,draft));
 s.values.set(`nestegg-draft-v2:${B}`,s.values.get(`nestegg-draft-v2:${A}`));
 assert.equal(s.api.loadNesteggDraft(B).draft,null);
 s.values.set(`nestegg-draft-v2:${A}`,'{');assert.equal(s.api.loadNesteggDraft(A).draft,null);
 for(const owner of [null,'','anonymous','../../other'])assert.equal(s.api.saveNesteggDraft(owner,draft),false);
});
test('blocked storage and quota failure are explicit and do not throw',()=>{
 const s=store();s.disable();assert.equal(s.api.loadNesteggDraft(A).unavailable,true);
 assert.equal(s.api.saveNesteggDraft(A,draft),false);assert.equal(s.api.clearNesteggDraft(A),false);
 const getter=load('src/lib/nestegg/storage.ts',{'./constants':constants},{window:{get localStorage(){throw Error('disabled');}}});
 assert.equal(getter.loadNesteggDraft(A).unavailable,true);assert.equal(getter.saveNesteggDraft(A,draft),false);
});
test('unmount and strict effect reestablishment retire every captured request',()=>{
 const scope=createNesteggWorkspaceScope(A,'session:A-1');assert.equal(scope.capture().isCurrent(),false);
 scope.activate();const old=scope.capture();assert.equal(old.isCurrent(),true);
 scope.dispose();assert.equal(old.isCurrent(),false);scope.activate();assert.equal(old.isCurrent(),false);
 assert.equal(scope.capture().isCurrent(),true);
});
const token=(session,refresh=0)=>`synthetic.${Buffer.from(JSON.stringify({session_id:session,refresh})).toString('base64url')}.signature`;
function db(authGate,queryGate) {
 const calls=[],tokenSamples=[];let authOwner=A,login='A-1',refresh=0,accessToken=async()=>null;
 const client={auth:{getUser:async()=>{if(authGate)await authGate.promise;return {data:{user:{id:authOwner}}};},
  getSession:async()=>({data:{session:{user:{id:authOwner},access_token:token(login,refresh)}}})},
  from(name){calls.push(['from',name]);const builder={};
   for(const method of ['select','eq','order','insert','update','delete'])builder[method]=(...args)=>{calls.push([method,...args]);return builder;};
   builder.single=()=>builder;builder.maybeSingle=()=>builder;
   builder.then=(resolve,reject)=>accessToken().then(value=>{tokenSamples.push(value);return queryGate.promise;}).then(resolve,reject);return builder;}};
 const scoped=load('src/lib/nestegg/scoped-client.ts',{
  '@/lib/supabase/client':{createClient:()=>client},'@/lib/auth/session-guard':{sessionIdentity},
  '@supabase/supabase-js':{createClient:(url,key,options)=>{accessToken=options.accessToken;return client;}},
 },{process:{env:{NEXT_PUBLIC_SUPABASE_URL:'https://fixture.invalid',NEXT_PUBLIC_SUPABASE_ANON_KEY:'synthetic-public'}}});
 return {calls,client,scoped,tokenSamples,owner:id=>{authOwner=id;},login:id=>{login=id;},refresh:()=>{refresh++;},api:load('src/lib/nestegg/scenarios-supabase.ts',{
  './scoped-client':scoped,'./constants':constants})};
}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function active(){const scope=createNesteggWorkspaceScope(A,'session:A-1');scope.activate();return scope;}
test('auth replacement before delayed verification refuses old-data writes without a query',async()=>{
 const auth=deferred(),q=deferred(),d=db(auth,q),scope=active();
 const promise=d.api.insertNesteggScenarioToSupabase('private A',draft.inputs,'base',scope.capture());
 d.owner(B);auth.resolve();assert.equal(await promise,null);assert.deepEqual(d.calls,[]);
});
test('retired same-owner session refuses late save reply and retains explicit owner predicates',async()=>{
 const q=deferred(),d=db(null,q),scope=active();
 const promise=d.api.updateNesteggScenarioInSupabase('original',draft.inputs,'base',{},scope.capture());
 await new Promise(setImmediate);assert.ok(d.calls.some(c=>c[0]==='eq'&&c[1]==='user_id'&&c[2]===A));
 scope.dispose();scope.activate();q.resolve({data:{id:'original',user_id:A,inputs:draft.inputs,name:'A',market_scenario:'base'},error:null});
 assert.equal(await promise,null);
});
test('wrong-owner database results are not published and reads/deletes are owner-bound',async()=>{
 const q=deferred(),d=db(null,q),scope=active();
 const read=d.api.fetchNesteggScenariosFromSupabase(scope.capture());await new Promise(setImmediate);
 q.resolve({data:[{user_id:B,inputs:draft.inputs}],error:null});await assert.rejects(read,/unavailable/);
 assert.ok(d.calls.some(c=>c[0]==='eq'&&c[1]==='user_id'&&c[2]===A));
 const q2=deferred(),d2=db(null,q2),del=d2.api.deleteNesteggScenarioFromSupabase('original',scope.capture());
 await new Promise(setImmediate);assert.ok(d2.calls.some(c=>c[0]==='eq'&&c[1]==='user_id'&&c[2]===A));
 scope.dispose();q2.resolve({error:null});assert.equal(await del,false);
});

test('current-session mismatch and failed reads cannot masquerade as an empty owner list',async()=>{
 const q=deferred(),d=db(null,q),scope=active();d.owner(B);
 await assert.rejects(d.api.fetchNesteggScenariosFromSupabase(scope.capture()),/session is unavailable/);assert.equal(d.calls.length,0);
 d.owner(A);const read=d.api.fetchNesteggScenariosFromSupabase(scope.capture());await new Promise(setImmediate);
 q.resolve({data:null,error:{message:'private raw response'}});await assert.rejects(read,/plans are unavailable/);
});

test('portfolio helpers refuse replacement auth before a query and retire delayed owner results',async()=>{
 const q=deferred(),d=db(null,q),scope=active();
 const portfolio=load('src/lib/portfolio/portfolio-supabase.ts',{'@/lib/supabase/client':{createClient:()=>d.client},'@/lib/nestegg/scoped-client':d.scoped},{console:{warn(){}}});
 d.owner(B);await assert.rejects(portfolio.fetchPortfolioTotal(scope.capture()),/session is unavailable/);
 await assert.rejects(portfolio.fetchPortfolioGoal(scope.capture()),/session is unavailable/);assert.equal(d.calls.length,0);
 d.owner(A);const total=portfolio.fetchPortfolioTotal(scope.capture());await new Promise(setImmediate);
 assert.ok(d.calls.some(c=>c[0]==='eq'&&c[1]==='user_id'&&c[2]===A));scope.dispose();
 q.resolve({data:[{user_id:A,balance:500000}],error:null});assert.equal(await total,0);
});
test('missing owner profile is a valid zero goal, while failed scoped profile reads are errors',async()=>{
 const q=deferred(),d=db(null,q),scope=active();
 const portfolio=load('src/lib/portfolio/portfolio-supabase.ts',{'@/lib/supabase/client':{createClient:()=>d.client},'@/lib/nestegg/scoped-client':d.scoped},{console:{warn(){}}});
 const empty=portfolio.fetchPortfolioGoal(scope.capture());await new Promise(setImmediate);q.resolve({data:null,error:null});
 assert.equal((await empty).goal,0);assert.ok(d.calls.some(c=>c[0]==='eq'&&c[1]==='id'&&c[2]===A));
 const bad=deferred(),d2=db(null,bad),p2=load('src/lib/portfolio/portfolio-supabase.ts',{'@/lib/supabase/client':{createClient:()=>d2.client},'@/lib/nestegg/scoped-client':d2.scoped},{console:{warn(){}}});
 const read=p2.fetchPortfolioGoal(scope.capture());await new Promise(setImmediate);bad.resolve({data:null,error:{message:'private raw data'}});
 await assert.rejects(read,/goal is unavailable/);
});

test('same-owner re-login before verification cannot dispatch old-session inputs under new credentials',async()=>{
 const auth=deferred(),q=deferred(),d=db(auth,q),scope=active();
 const save=d.api.insertNesteggScenarioToSupabase('old inputs',draft.inputs,'base',scope.capture());
 d.login('A-2');auth.resolve();assert.equal(await save,null);assert.equal(d.calls.length,0);
});
test('ordinary token refresh verifies the same session and binds each data request to its captured token',async()=>{
 const q=deferred(),d=db(null,q),scope=active();d.refresh();
 const save=d.api.insertNesteggScenarioToSupabase('own inputs',draft.inputs,'base',scope.capture());await new Promise(setImmediate);
 d.owner(B);d.login('B-1');q.resolve({data:{id:'original',user_id:A,inputs:draft.inputs,name:'A',market_scenario:'base'},error:null});
 assert.equal((await save).name,'A');assert.ok(d.tokenSamples.length>0);assert.ok(d.tokenSamples.every(t=>t===token('A-1',1)));
});
