import assert from 'node:assert/strict';
import { test } from 'node:test';
import vm from 'node:vm';
import fs from 'node:fs';
import ts from 'typescript';
import * as read from '../../src/lib/probes/durable-read-model.ts';
const owner='00000000-0000-0000-0000-000000000001',run='00000000-0000-0000-0000-000000000002',
 command='00000000-0000-0000-0000-000000000003';
function module(fetch) {
 const exports={};
 const code=ts.transpileModule(fs.readFileSync('src/lib/probes/paper-api.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{exports,require(name){assert.equal(name,'./durable-read-model');return read;},
  fetch,URL,Response,TextDecoder,Uint8Array,AbortController,TextEncoder,setTimeout,clearTimeout});return exports;
}
function json(value,status=200){return new Response(JSON.stringify(value),{status});}
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
test('completed evaluation scores decode tagged research floats; aborted scores stay unavailable',()=>{
 const m=module();const cohort={iteration_id:'run:0',phase:'completed',member_ids:[owner],evaluations:[{
  probe_id:owner,iteration_id:'run:0',status:'completed',reason:'deadline',num_trades:2,fitness:{float64:'0x1.8000000000000p+0'}}]};
 assert.equal(m.evaluationDetails({account_currency:'USD',cohort}).results[0].fitness,1.5);
 const aborted={...cohort,phase:'aborted',evaluations:[{...cohort.evaluations[0],status:'aborted',fitness:null}]};
 assert.equal(m.evaluationDetails({account_currency:'USD',cohort:aborted}).results[0].fitness,null);
 assert.throws(()=>m.evaluationDetails({account_currency:'USD',cohort:{...cohort,evaluations:[...cohort.evaluations,...cohort.evaluations]}}));
});
