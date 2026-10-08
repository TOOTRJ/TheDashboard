import assert from 'node:assert/strict';
import { test } from 'node:test';
import vm from 'node:vm';
import fs from 'node:fs';
import ts from 'typescript';
import * as read from '../../src/lib/probes/durable-read-model.ts';
const owner='00000000-0000-0000-0000-000000000001',run='00000000-0000-0000-0000-000000000002',
 command='00000000-0000-0000-0000-000000000003';
function module(fetch,globals={}) {
 const exports={};
 const code=ts.transpileModule(fs.readFileSync('src/lib/probes/paper-api.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{exports,require(name){assert.equal(name,'./durable-read-model');return read;},
  fetch,URL,Response,TextDecoder,Uint8Array,AbortController,TextEncoder,setTimeout,clearTimeout,...globals});return exports;
}
function json(value,status=200){return new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});}
const directory=()=>({version:1,owner_id:owner,through_id:run,records:[{run_id:run,revision:2,
 data:{id:run,account_currency:'USD',durability_version:5},archive_receipt:null}],next_id:run,has_more:false});
test('pinned read URL and user token; worker calls contain only original control ID',async()=>{
 const calls=[];const m=module(async(url,options)=>{calls.push([url,options]);return json({ok:true});});
 const api=m.paperAPI('synthetic-user-token','synthetic-public-key','https://worker.invalid');
 await api.read('discover',{});await api.worker('start',{request_id:command});
 assert.equal(calls[0][0],'https://fxpxsciltakyypunglzr.supabase.co/rest/v1/rpc/discover');
 assert.equal(calls[0][1].headers['Content-Profile'],'vn_read');assert.equal(calls[0][1].redirect,'error');
 assert.equal(calls[1][1].headers.apikey,undefined);assert.deepEqual(JSON.parse(calls[1][1].body),{request_id:command});
 for(const name of ['create_run','commit_command','delete','accept_event'])assert.throws(()=>api.read(name,{}));
 for(const url of ['http://worker.invalid','https://u:p@worker.invalid','https://worker.invalid/path','https://worker.invalid?token=x'])assert.throws(()=>m.paperAPI('x','y',url));
});
test('oversized, redirected, invalid UTF-8 and failed responses never expose raw content',async()=>{
 for(const response of [new Response('secret',{status:401}),new Response('x'.repeat(65537)),new Response(new Uint8Array([255])),new Response('not json')]){
  const m=module(async()=>response);await assert.rejects(m.paperAPI('x','y','https://worker.invalid').read('page',{}),e=>!e.message.includes('secret'));
 }
});
test('only bounded exact closed read responses expose the safe closed state',async()=>{
 const m=module(async()=>json({detail:'Paper service is closed'},503));
 const api=m.paperAPI('x','y','https://worker.invalid');
 for(const name of ['status','controls'])await assert.rejects(api.worker(name),e=>e instanceof m.PaperWorkerClosedError);
 for(const action of [()=>api.read('page',{}),()=>api.worker('start',{request_id:command})])
  await assert.rejects(action,e=>!(e instanceof m.PaperWorkerClosedError));
 for(const response of [json({detail:'Authentication service unavailable'},503),json({detail:'Paper service is closed',extra:true},503),
  json({detail:'Paper service is closed'},401),new Response(JSON.stringify({detail:'Paper service is closed'}),{status:503}),
  json({detail:'x'.repeat(65536)},503)]){
  const n=module(async()=>response);await assert.rejects(n.paperAPI('x','y','https://worker.invalid').worker('status'),e=>!(e instanceof n.PaperWorkerClosedError));
 }
});
test('owner-bound discovery validates cutoff, ordering and archive identity',async()=>{
 const m=module();const signal=new AbortController().signal;
 const result=await m.discoverRuns({read:async()=>directory()},owner,signal);assert.equal(result[0].runId,run);
 for(const change of [p=>({...p,owner_id:run}),p=>({...p,next_id:owner}),p=>({...p,records:[...p.records,...p.records]}),p=>({...p,records:[{...p.records[0],archive_receipt:{owner_id:run,run_id:run,archived:true}}]})]){
  await assert.rejects(m.discoverRuns({read:async()=>change(directory())},owner,signal));
 }
});
test('all detail kinds share one revision even if the run advances between RPCs',async()=>{
 const m=module();const calls=[];
 const api={read:async(name,args)=>{
  assert.equal(name,'page');calls.push(args);
  const records=args.kind==='runs'?[{revision:2,key:run,command_id:command,data:{id:run,account_currency:'USD',durability_version:5,initial_cash:'1000',reserve:'200',reference_equity:null}}]:[];
  return {version:1,owner_id:owner,run_id:run,kind:args.kind,through_revision:2,records,has_more:false,next_cursor:records.length?{revision:2,key:run}:null};
 }};
 const result=await m.runSnapshot(api,owner,run,new AbortController().signal);
 assert.equal(result.revision,2);assert.equal(calls[0].through_revision,null);assert.ok(calls.slice(1).every(c=>c.through_revision===2));
});
test('durable event replay is contiguous, owner-bound and deduplicated on reconnect',async()=>{
 const m=module();const signal=new AbortController().signal;
 const events={version:1,owner_id:owner,run_id:run,through_sequence:1,records:[{sequence:1,revision:2,command_id:command,
 data:{event_id:`${run}:${command}:0`,event_index:0,event:{type:'run_status'}}}],has_more:false,next_sequence:1};
 const first=await m.eventSnapshot({read:async()=>events},owner,run,signal),second=await m.eventSnapshot({read:async()=>events},owner,run,signal);
 assert.deepEqual(first,second);assert.equal(new Set([...first,...second].map(e=>e.eventId)).size,1);
 for(const change of [p=>({...p,owner_id:run}),p=>({...p,next_sequence:0}),p=>({...p,through_sequence:2}),p=>({...p,records:[{...p.records[0],sequence:2}]}),p=>({...p,records:[...p.records,...p.records]})]){
  await assert.rejects(m.eventSnapshot({read:async()=>change(events)},owner,run,signal));
 }
});
test('trade display keeps exact fees and does not invent open-position P&L',()=>{
 const m=module();const value={id:command,account_id:owner,asset:'SOL/USD',account_currency:'USD',quantity:'1.25',
  closed:false,opened_at:'2026-10-08',closed_at:null,exit_reason:null,exit:null,
  entry:{fill_price:'123.123456789',notional:'153.90432098625',fee:'0.15390432098625'}};
 const open=m.tradeDetails(value);assert.equal(open.entryPrice,'123.123457');assert.equal(open.netPnl,null);
 const closed=m.tradeDetails({...value,closed:true,exit:{fill_price:'120',fee:'0.15',net_pnl:'-4.05822530723625'}});
 assert.equal(closed.netPnl,'-4.06');assert.throws(()=>m.tradeDetails({...value,closed:true}));
 assert.throws(()=>m.tradeDetails({...value,entry:{...value.entry,fee:0.15}}));
});
test('complete snapshots accept exact 18-place ledger trade quantities without rounding them',async()=>{
 const fixture=JSON.parse(fs.readFileSync('tests/probes/fixtures/exact-paper-trade.json','utf8'));
 const m=module();
 const api={read:async(name,args)=>{
  assert.equal(name,'page');
  const records=args.kind==='runs'?[{revision:3,key:run,command_id:command,
   data:{id:run,account_currency:'USD',durability_version:5,initial_cash:'1000',reserve:'200',reference_equity:'1000'}}]
   :args.kind==='trades'?[fixture.open,fixture.closed].map((data,index)=>({revision:index+2,
    key:`${command}:0000`,command_id:command,data})):[];
  return {version:1,owner_id:owner,run_id:run,kind:args.kind,through_revision:3,records,
   has_more:false,next_cursor:records.length?{revision:records.at(-1).revision,key:records.at(-1).key}:null};
 }};
 const snapshot=await m.runSnapshot(api,owner,run,new AbortController().signal);
 assert.equal(snapshot.revision,3);assert.equal(snapshot.trades.length,2);
 const open=m.tradeDetails(snapshot.trades[0].data),closed=m.tradeDetails(snapshot.trades[1].data);
 assert.equal(open.quantity,'0.202511138112596192');assert.equal(closed.quantity,open.quantity);
 assert.equal(open.netPnl,null);assert.equal(closed.netPnl,'0.11');
 for(const quantity of ['0.2025111381125961921','2e-1',0.2,'-0.2','01.2'])
  assert.throws(()=>m.tradeDetails({...fixture.open,quantity}));
});
test('completed evaluation scores decode tagged research floats; aborted scores stay unavailable',()=>{
 const m=module();const cohort={iteration_id:`${run}:0`,phase:'completed',member_ids:[owner],evaluations:[{
  probe_id:owner,iteration_id:`${run}:0`,status:'completed',reason:'deadline',num_trades:2,fitness:{float64:'0x1.8000000000000p+0'}}]};
 assert.equal(m.evaluationDetails({account_currency:'USD',cohort}).results[0].fitness,1.5);
 const aborted={...cohort,phase:'aborted',evaluations:[{...cohort.evaluations[0],status:'aborted',fitness:null}]};
 assert.equal(m.evaluationDetails({account_currency:'USD',cohort:aborted}).results[0].fitness,null);
 assert.throws(()=>m.evaluationDetails({account_currency:'USD',cohort:{...cohort,evaluations:[...cohort.evaluations,...cohort.evaluations]}}));
});
test('complete paginated snapshots may exceed eight seconds but have one finite sixty-second budget',async()=>{
 for(const pages of [12,61]){
  let now=0,id=0,calls=0;const timers=new Map();let observedSignal;
  const advance=()=>{now+=1000;for(const [key,t] of [...timers])if(t.at<=now){timers.delete(key);t.fn();}};
  const m=module(undefined,{setTimeout:(fn,ms)=>{timers.set(++id,{fn,at:now+ms});return id;},clearTimeout:key=>timers.delete(key)});
  const api={read:async(name,args,signal)=>{
   observedSignal=signal;
   const number=args.kind==='runs'?++calls:0;
   if(number)advance();
   const records=number?[{revision:number,key:run,command_id:command,data:{id:run,account_currency:'USD',durability_version:5,initial_cash:'1000',reserve:'200',reference_equity:null}}]:[];
   return {version:1,owner_id:owner,run_id:run,kind:args.kind,through_revision:pages,records,has_more:number>0&&number<pages,
    next_cursor:records.length?{revision:number,key:run}:null};
  }};
  const request=m.runSnapshot(api,owner,run,new AbortController().signal);
  if(pages===12){const snapshot=await request;assert.equal(snapshot.runs.length,12);assert.equal(snapshot.revision,12);}
  else{await assert.rejects(request);assert.equal(calls,60);}
  assert.equal(observedSignal.aborted,true);assert.equal(timers.size,0);
 }
});
const assessment=JSON.parse(fs.readFileSync('tests/probes/fixtures/paper-assessment.json','utf8'));
test('assessment decodes exact genes, observed drawdown, ancestry, costs and comparable windows',()=>{
 const m=module();const founder=m.probeDetails(assessment.probes[0]),child=m.probeDetails(assessment.probes[8]);
 assert.deepEqual(JSON.parse(JSON.stringify(founder.genes)),{fast:3,slow:20});
 assert.equal(founder.balance.terminalCash,'100.07');assert.equal(founder.drawdown,'0.0900%');
 assert.equal(founder.balance.metricsBasis,'last_observed_before_replacement');
 assert.equal(child.generation,1);assert.equal(child.lineage.sources[0].id,founder.balance.id);
 const complete=m.evaluationDetails(assessment.evaluations[0]),abort=m.evaluationDetails(assessment.evaluations[1]);
 assert.equal(complete.started,10000);assert.equal(complete.ends,13600);assert.equal(complete.horizon,3600);
 assert.equal(complete.results[0].roi,.0007);assert.equal(complete.results[0].fitness,-.0011);
 assert.equal(abort.results[0].roi,null);assert.equal(abort.results[0].eligible,false);
 assert.equal(m.executionDetails(assessment.execution_policy).fee,'0');
});
test('early terminal score survives an aborted cohort but is withheld from selection',()=>{
 const m=module(),row=structuredClone(assessment.evaluations[1]);
 const result=row.cohort.evaluations[0];Object.assign(result,{status:'completed',reason:'drawdown',
  roi:{float64:'-0x1.999999999999ap-3'},fitness:{float64:'-0x1.3333333333334p-1'},
  terminated_at:{float64:'0x1.a91p+13'}});row.cohort.completed_count=1;
 const r=m.evaluationDetails(row).results[0];assert.equal(r.early,true);assert.equal(r.eligible,false);
 assert.equal(r.status,'completed');assert.ok(r.fitness<0);
});
test('missing historical metadata stays unavailable and unknown policy versions are not rewritten',()=>{
 const m=module(),row=structuredClone(assessment.evaluations[0]);
 row.cohort.policy.version='future-window-v9';row.scoring_policy='future-score-v2';
 assert.equal(m.evaluationDetails(row).windowPolicy,'future-window-v9');
 const old=m.probeDetails({id:command,account_currency:'USD',initial_cash:'100',economic_cash:'0',retired:true,
  terminal_cash:'99.999999999999999999',equity:null,equity_basis:'terminal_frozen',metrics_basis:'last_observed_before_replacement'});
 assert.equal(old.genes,null);assert.equal(old.drawdown,null);assert.equal(old.lineage,null);
});
test('malformed genes, ancestry, costs and cohort records reject publication',()=>{
 const m=module();
 for(const change of [p=>p.genome.ema_fast='NaN',p=>p.genome.ema_fast='0x1.8p+0',p=>p.generation=3,
  p=>p.lineage.child_id=run,p=>p.max_drawdown.denominator='0',p=>p.lineage.sources=[{role:'genetic_parent',ordinal:0,source_id:p.id}]]){
  const p=structuredClone(assessment.probes[0]);change(p);assert.throws(()=>m.probeDetails(p));
 }
 for(const change of [e=>e.cohort.member_ids[1]=e.cohort.member_ids[0],e=>e.cohort.evaluations.pop(),
  e=>e.cohort.completed_count=0,e=>e.cohort.evaluations[0].roi={float64:'inf'},
  e=>e.cohort.evaluations[0].window_ends_at=null,e=>e.cohort.evaluations[0].cohort_complete=false,
  e=>e.cohort.ends_at=e.cohort.started_at]){
  const e=structuredClone(assessment.evaluations[0]);change(e);assert.throws(()=>m.evaluationDetails(e));
 }
 for(const fee_bps of [0,'1e2','-1','10000','1.0000001'])
  assert.throws(()=>m.executionDetails({...assessment.execution_policy,config:{...assessment.execution_policy.config,fee_bps}}));
 for(const change of [p=>p.lineage.sources[0].role='wrong_role',p=>p.lineage.sources[1].ordinal=0,p=>p.genome.parent_ids.pop()]){
  const p=structuredClone(assessment.probes[8]);change(p);assert.throws(()=>m.probeDetails(p));
 }
});
test('complete assessment snapshot checks source ancestry and evaluation membership at its pinned revision',async()=>{
 const m=module();
 function api(fixture){return {read:async(name,args)=>{
  assert.equal(name,'page');const data=args.kind==='runs'?[{id:run,account_currency:'USD',durability_version:5,
   initial_cash:'1000',reserve:'200',reference_equity:'1000.07',execution_policy:fixture.execution_policy}]
   :args.kind==='probes'?fixture.probes:args.kind==='evaluations'?fixture.evaluations:[];
  const records=data.map(d=>({revision:2,key:args.kind==='evaluations'?d.cohort.iteration_id:d.id,command_id:command,data:d}));
  return {version:1,owner_id:owner,run_id:run,kind:args.kind,through_revision:2,records,has_more:false,
   next_cursor:records.length?{revision:2,key:records.at(-1).key}:null};
 }};}
 const complete=await m.runSnapshot(api(assessment),owner,run,new AbortController().signal);
 assert.equal(complete.probes.length,16);assert.equal(complete.evaluations.length,2);assert.equal(complete.revision,2);
 for(const change of [f=>{f.probes.pop();},f=>{f.probes[8].lineage.source_iteration_id='foreign:0';},
  f=>{f.evaluations[0].cohort.iteration_id='foreign:0';},f=>{f.probes[0].max_drawdown.numerator='10001';}]){
  const f=structuredClone(assessment);change(f);
  await assert.rejects(m.runSnapshot(api(f),owner,run,new AbortController().signal));
 }
});
