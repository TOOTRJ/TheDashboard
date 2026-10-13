import test from 'node:test';
import assert from 'node:assert/strict';
import {A,B,deferred,transpile} from './helpers/portfolio-harness.mjs';
import {createNesteggWorkspaceScope} from '../src/lib/nestegg/session-scope.ts';
import {sessionIdentity} from '../src/lib/auth/session-guard.ts';
const token=id=>`fake.${Buffer.from(JSON.stringify({session_id:id})).toString('base64url')}.sig`;
function harness(){
 const workspace=createNesteggWorkspaceScope(A,'session:A-1');workspace.activate();const scope=workspace.capture(),calls=[],clients=[];
 const control={user:A,login:'A-1',result:{data:{id:'x',user_id:A,name:'n',balance:12,updated_at:'2026-10-13T00:00:00Z'},error:null}};
 const query=new Proxy({}, {get(_,name){if(name==='single'||name==='maybeSingle'||name==='order')return async(...args)=>{calls.push({name,args});if(control.resultGate)await control.resultGate.promise;return control.result;};return (...args)=>{calls.push({name,args});return query;};}});
 const browser={auth:{getUser:async()=>{if(control.userGate)await control.userGate.promise;return {data:{user:control.user?{id:control.user}:null}};},getSession:async()=>({data:{session:{user:{id:control.user},access_token:token(control.login)}}})}};
 const scoped=transpile('src/lib/nestegg/scoped-client.ts',{
 '@supabase/supabase-js':{createClient:(url,key,options)=>{clients.push({url,key,options});return {from:table=>{calls.push({name:'from',args:[table]});return query;}};}},
 '@/lib/supabase/client':{createClient:()=>browser},'@/lib/auth/session-guard':{sessionIdentity},
 },{process:{env:{NEXT_PUBLIC_SUPABASE_URL:'https://fake.invalid',NEXT_PUBLIC_SUPABASE_ANON_KEY:'fake'}}});
 const helper=transpile('src/lib/portfolio/portfolio-supabase.ts',{'@/lib/supabase/client':{createClient:()=>browser},'@/lib/nestegg/scoped-client':scoped},{console:{warn:()=>assert.fail('No raw provider diagnostics expected')}});
 return {helper,scope,workspace,control,calls,clients};
}
const invoke=(h,kind)=>kind==='add'?h.helper.insertPortfolioAccount('n',12,h.scope):kind==='edit'?h.helper.updatePortfolioAccount('x',{name:'n',balance:12},h.scope):kind==='delete'?h.helper.deletePortfolioAccount('x',h.scope):h.helper.updatePortfolioGoal(333,2040,h.scope);
for(const kind of ['add','edit','delete','goal']){
 test(`${kind} authenticates original owner/login and binds original token`,async()=>{
  const h=harness();if(kind==='goal')h.control.result.data={id:A,portfolio_goal:'333',portfolio_goal_year:2040};
  assert.ok(await invoke(h,kind));assert.equal(h.clients.length,1);assert.equal(await h.clients[0].options.accessToken(),token('A-1'));
  if(kind!=='add')assert.ok(h.calls.some(c=>c.name==='eq'&&c.args[0]===(kind==='goal'?'id':'user_id')&&c.args[1]===A));
  h.workspace.dispose();await assert.rejects(h.clients[0].options.accessToken());
 });
 test(`${kind} refuses missing/foreign/zero-row acknowledgment and provider error`,async()=>{
  for(const data of [null,[],{id:'wrong',user_id:B},{id:A,portfolio_goal:null,portfolio_goal_year:2040},{id:A,portfolio_goal:334,portfolio_goal_year:2040}]){
   const h=harness();h.control.result.data=data;assert.ok(!(await invoke(h,kind)));
  }
  const h=harness();h.control.result.error={message:'private detail'};assert.ok(!(await invoke(h,kind)));
 });
 test(`${kind} cannot use changed owner/login or retire during identity lookup`,async()=>{
  for(const change of [{user:B},{login:'A-2'}]){const h=harness();Object.assign(h.control,change);assert.ok(!(await invoke(h,kind)));assert.equal(h.clients.length,0);assert.equal(h.calls.length,0);}
  const h=harness(),gate=deferred();h.control.userGate=gate;const result=invoke(h,kind);h.workspace.dispose();gate.resolve();assert.ok(!(await result));assert.equal(h.clients.length,0);assert.equal(h.calls.length,0);
 });
 test(`${kind} acknowledgment retired after submission cannot succeed`,async()=>{
  const h=harness();if(kind==='goal')h.control.result.data={id:A,portfolio_goal:333,portfolio_goal_year:2040};
  const gate=deferred();h.control.resultGate=gate;const result=invoke(h,kind);for(let i=0;i<12&&!h.calls.some(c=>c.name==='single');i++)await Promise.resolve();assert.ok(h.calls.some(c=>c.name==='single'));h.workspace.dispose();gate.resolve();assert.ok(!(await result));
 });
}
test('invalid economic values never create a data client or become a zero save',async()=>{
 for(const balance of [NaN,Infinity,-1]){const h=harness();assert.equal(await h.helper.insertPortfolioAccount('n',balance,h.scope),null);assert.equal(await h.helper.updatePortfolioAccount('x',{balance},h.scope),null);assert.equal(await h.helper.updatePortfolioGoal(balance,2040,h.scope),false);assert.equal(h.clients.length,0);}
 const h=harness();assert.equal(await h.helper.updatePortfolioGoal(0,2040.5,h.scope),false);assert.equal(h.clients.length,0);
});
test('owned account update requires exact returned ID and goal requires exact saved amount/year',async()=>{
 const h=harness();h.control.result.data.id='other-owned';assert.equal(await invoke(h,'edit'),null);assert.equal(await invoke(h,'delete'),false);
 for(const data of [{id:A,portfolio_goal:333,portfolio_goal_year:2041},{id:B,portfolio_goal:333,portfolio_goal_year:2040}]){h.control.result.data=data;assert.equal(await invoke(h,'goal'),false);}
});
test('scoped read failure differs from valid empty accounts and default zero goal',async()=>{
 const h=harness();h.control.result={data:[],error:null};assert.equal((await h.helper.fetchPortfolioAccounts(h.scope)).length,0);
 h.control.result={data:{portfolio_goal:0,portfolio_goal_year:null},error:null};assert.equal((await h.helper.fetchPortfolioGoal(h.scope)).goal,0);
 h.control.result={data:null,error:null};assert.equal((await h.helper.fetchPortfolioGoal(h.scope)).goal,0);
 h.control.result={data:null,error:{message:'secret'}};await assert.rejects(h.helper.fetchPortfolioAccounts(h.scope),/unavailable/);
});
test('present malformed goal/year cannot become zero on reads or acknowledgments',async()=>{
 for(const data of [false,0,'',[],undefined]){const h=harness();h.control.result.data=data;await assert.rejects(h.helper.fetchPortfolioGoal(h.scope),/unavailable/);if(!Array.isArray(data))await assert.rejects(h.helper.fetchPortfolioAccounts(h.scope),/unavailable/);}
 const values=[true,false,'', ' ',null,undefined,{},[],NaN,Infinity,'Infinity','0x1','private'];
 for(const value of values){const h=harness();h.control.result.data={id:A,portfolio_goal:value,portfolio_goal_year:null};assert.equal(await h.helper.updatePortfolioGoal(0,null,h.scope),false);await assert.rejects(h.helper.fetchPortfolioGoal(h.scope),/unavailable/);}
 for(const value of [...values.filter(x=>x!==null),2040.5,'2040.5']){const h=harness();h.control.result.data={id:A,portfolio_goal:0,portfolio_goal_year:value};assert.equal(await h.helper.updatePortfolioGoal(0,0,h.scope),false);await assert.rejects(h.helper.fetchPortfolioGoal(h.scope),/unavailable/);}
 const h=harness();h.control.result.data={id:A,portfolio_goal:'0',portfolio_goal_year:'0'};assert.equal(await h.helper.updatePortfolioGoal(0,0,h.scope),true);assert.equal((await h.helper.fetchPortfolioGoal(h.scope)).goalYear,0);
});
test('account rows require genuine balance and supplied updated timestamp',async()=>{
 for(const patch of [{balance:true},{balance:''},{balance:null},{balance:'0x1'},{balance:'Infinity'},{updated_at:undefined},{updated_at:false},{updated_at:''}]){const h=harness();Object.assign(h.control.result.data,patch);assert.equal(await invoke(h,'add'),null);assert.equal(await invoke(h,'edit'),null);h.control.result.data=[h.control.result.data];await assert.rejects(h.helper.fetchPortfolioAccounts(h.scope),/unavailable/);}
});
