import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as read from '../../src/lib/probes/durable-read-model.ts';

const owner='11111111-1111-4111-8111-111111111111',run='22222222-2222-4222-8222-222222222222',
 requestId='33333333-3333-4333-8333-333333333333',member='44444444-4444-4444-8444-444444444444';
function module(fetch) {
 const exports={};
 const code=ts.transpileModule(fs.readFileSync('src/lib/probes/paper-v6-api.ts','utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{exports,require(name){assert.equal(name,'./durable-read-model');return read;},
  fetch,URL,Response,TextDecoder,Uint8Array,AbortController,setTimeout,clearTimeout});
 return exports;
}
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const status=()=>({version:6,owner_id:owner,run_id:run,phase:'running',sequence:3,revision:2,generation:0,epoch:0,
 busy:false,requires_reconciliation:false,last_request_id:requestId,projection:{reserve_cash:'200',total_equity:'1000.000000000000000001',
 asset:'SOL/USD',population:8,members:[{id:member,name:'Synthetic candidate',generation:0,ema_fast:3,ema_slow:20,
 cash:'100',initial_cash:'100',equity:null}],positions:[]}});
const assessment=()=>({owner_id:owner,run_id:run,probe_id:member,generation:0,status:'completed',reason:'deadline',selection_eligible:true,
 fitness_float64:'0x1.0000000000000p-3',roi_float64:'0x1.0000000000000p-2'});
const history=()=>({version:6,owner_id:owner,run_id:run,through_sequence:3,next_sequence:2,has_more:true,
 records:[{sequence:2,kind:'decision',data:{assessments:[assessment()]}}]});

test('v6 uses only authenticated bounded worker routes and exact original control IDs',async()=>{
 const calls=[],m=module(async(url,options)=>{calls.push({url,options});return json({ok:true});});
 const api=m.paperV6API('synthetic-user-token','https://worker.invalid');
 await api.status();await api.command('start',requestId);await api.command('stop',requestId);await api.history(10,25);
 assert.deepEqual(calls.map(c=>c.url),['https://worker.invalid/v6/status','https://worker.invalid/v6/start',
  'https://worker.invalid/v6/stop','https://worker.invalid/v6/history?after_sequence=10&limit=25']);
 assert.deepEqual(JSON.parse(calls[1].options.body),{request_id:requestId});
 for(const {options} of calls){assert.equal(options.headers.Authorization,'Bearer synthetic-user-token');
  assert.equal(options.headers.apikey,undefined);assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');assert.equal(options.credentials,'omit');}
 assert.throws(()=>api.command('swap',requestId));assert.throws(()=>api.command('start','new-id'));
 for(const limit of [0,101,1.2])assert.throws(()=>api.history(0,limit));
 for(const origin of ['http://worker.invalid','https://user:password@worker.invalid','https://worker.invalid/path','https://worker.invalid?secret=x'])
  assert.throws(()=>m.paperV6API('x',origin));
});
test('curated v6 status preserves exact balances and validates owner, run, genes and reconciliation',()=>{
 const m=module(),s=m.parsePaperV6Status(status(),owner,run);
 assert.equal(s.projection.totalEquity,'1000.000000000000000001');assert.equal(s.projection.members[0].fast,3);
 for(const change of [s=>s.version=5,s=>s.owner_id=run,s=>s.run_id=owner,s=>s.sequence=-1,
  s=>s.phase='live',s=>s.busy='false',s=>s.last_request_id='invalid',s=>s.projection.total_equity=1000,
  s=>s.projection.members[0].ema_fast=20,s=>s.projection.members.push(s.projection.members[0])]){
  const value=status();change(value);assert.throws(()=>m.parsePaperV6Status(value,owner,run));
 }
 const idle=status();idle.projection=null;idle.revision=null;
 idle.warmup={observed_minutes:42,required_minutes:915};
 assert.equal(m.parsePaperV6Status(idle,owner).projection,null);
 assert.equal(m.parsePaperV6Status(idle,owner).revision,null);
 assert.equal(m.parsePaperV6Status(idle,owner).warmup.observed,42);
 for(const phase of ['recovering','risk_halted'])assert.equal(m.parsePaperV6Status({...idle,phase},owner).phase,phase);
});
test('v6 history is owner-bound and contiguous; aborted assessments cannot become selection inputs',()=>{
 const m=module(),page=m.parsePaperV6History(history(),owner,run,1,25);
 assert.equal(page.records[0].assessments[0].fitness,.125);assert.equal(page.records[0].assessments[0].roi,.25);
 for(const change of [h=>h.owner_id=run,h=>h.run_id=owner,h=>h.next_sequence=1,h=>h.has_more=false,
  h=>h.records[0].sequence=3,h=>h.records[0].data.assessments[0].owner_id=run,
  h=>h.records[0].data.assessments[0].status='aborted']){
  const value=history();change(value);assert.throws(()=>m.parsePaperV6History(value,owner,run,1,25));
 }
 const aborted=history();Object.assign(aborted.records[0].data.assessments[0],{
  status:'aborted',selection_eligible:false,fitness_float64:null,roi_float64:null});
 assert.equal(m.parsePaperV6History(aborted,owner,run,1,25).records[0].assessments[0].fitness,null);
});
test('v6 responses have a finite byte budget and never reveal private server errors',async()=>{
 for(const response of [new Response('private-driver-secret',{status:500}),new Response('x'.repeat(262145)),
  new Response(new Uint8Array([255])),json({detail:'private-provider-key'},401)]){
  const m=module(async()=>response);await assert.rejects(m.paperV6API('x','https://worker.invalid').status(),
   error=>!error.message.includes('private'));
 }
 const m=module(async()=>json({detail:'Paper service is closed'},503));
 await assert.rejects(m.paperV6API('x','https://worker.invalid').status(),error=>error instanceof m.PaperV6ClosedError);
});
test('v6 parent cancellation reaches the owned request signal',async()=>{
 let observed;const m=module(async(url,options)=>{observed=options.signal;throw Error('private transport failure');});
 const controller=new AbortController();controller.abort();
 await assert.rejects(m.paperV6API('x','https://worker.invalid').status(controller.signal));assert.equal(observed.aborted,true);
});
test('exact real service held-position status preserves kernel money through36decimal places',()=>{
 const fixture=JSON.parse(fs.readFileSync('tests/probes/fixtures/paper-v6-held-status.json','utf8'));
 const m=module(),parsed=m.parsePaperV6Status(fixture,fixture.owner_id,fixture.run_id);
 assert.equal(parsed.projection.openPositions,8);assert.equal(parsed.projection.members.length,8);
 const original=fixture.projection.members[0];
 assert.ok(original.cash.split('.')[1].length>18);
 assert.equal(parsed.projection.members[0].cash,original.cash);
 assert.equal(parsed.projection.members[0].equity,original.equity);
 assert.doesNotThrow(()=>read.displayUSD(parsed.projection.members[0].cash));
 const exact=structuredClone(fixture);exact.projection.members[0].cash='0.'+'1'.repeat(36);
 assert.equal(m.parsePaperV6Status(exact,fixture.owner_id).projection.members[0].cash,exact.projection.members[0].cash);
 exact.projection.members[0].cash='0.'+'1'.repeat(37);
 assert.throws(()=>m.parsePaperV6Status(exact,fixture.owner_id));
});
