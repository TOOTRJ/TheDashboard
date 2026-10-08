import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as durable from '../../src/lib/probes/durable-read-model.ts';

const owner='00000000-0000-0000-0000-000000000001',run='00000000-0000-0000-0000-000000000002',
 start='00000000-0000-0000-0000-000000000003',stop='00000000-0000-0000-0000-000000000004';
const newer='00000000-0000-0000-0000-000000000006',otherOwner='00000000-0000-0000-0000-000000000007';
function load(path,modules,globals={}) {
 const exports={};const code=ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInNewContext(code,{exports,require(name){assert.ok(Object.hasOwn(modules,name),name);return modules[name];},
  AbortController,TextEncoder,setTimeout,clearTimeout,URL,Uint8Array,TextDecoder,
  fetch(){throw Error('Real network is forbidden');},...globals});return exports;
}
const paper=load('src/lib/probes/paper-api.ts',{'./durable-read-model':durable});
const assessment=JSON.parse(fs.readFileSync('tests/probes/fixtures/paper-assessment.json','utf8'));
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
function harness(options={}) {
 const hooks=[],effects=[],requests=[],reads=[];let index=0,dirty=false,tree;
 const timers=new Map();let timerId=0,now=0;
 const later=(fn,delay)=>{const id=++timerId;timers.set(id,{fn,at:now+delay});return id;};
 let phase=options.phase??'fresh',failed=false,workerRun=options.workerRun??run,activeOwner=owner;
 const directoryRuns=options.directoryRuns??[run];
 const same=(a,b)=>a&&b&&a.length===b.length&&a.every((x,i)=>Object.is(x,b[i]));
 const memo=(fn,deps)=>{const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps))hooks[i]={deps,value:fn()};return hooks[i].value;};
 const effect=(fn,deps)=>{const i=index++;if(!hooks[i]||!same(hooks[i].deps,deps)){
  const old=hooks[i];hooks[i]={deps,cleanup:old?.cleanup};effects.push(()=>{hooks[i].cleanup?.();hooks[i].cleanup=fn();});}};
 const react={useMemo:memo,useRef:v=>memo(()=>({current:v}),[]),useEffect:effect,useLayoutEffect:effect,
  useState(v){const i=index++;hooks[i]??={value:typeof v==='function'?v():v};return [hooks[i].value,next=>{
   const value=typeof next==='function'?next(hooks[i].value):next;if(!Object.is(value,hooks[i].value)){hooks[i].value=value;dirty=true;}}];}};
 const row={id:run,durability_version:5,account_currency:'USD',initial_cash:'1000',reserve:'1000',reference_equity:null,
  status:'stopped',generation:0,open_position_count:1,requires_reconciliation:true,committed_at:'2026-10-08',source_at:null};
 const state=()=>({version:1,owner_id:activeOwner,run_id:workerRun,request_id:start,phase,stop_requested:phase==='stopped',busy:false,
  requires_reconciliation:['failed','drained','pending'].includes(phase)});
 const api={
  async read(name,args,signal){reads.push({name,args,signal});
   if(options.readGate)await options.readGate.promise;
   if(name==='archive_run'){
    if(options.archiveFails&&!failed){failed=true;throw Error('lost archive reply');}
    return {owner_id:owner,run_id:run,request_id:args.request_id,revision:args.expected_revision,archived:true};
   }
   if(name==='discover')return {version:1,owner_id:activeOwner,through_id:directoryRuns.at(-1)??null,
    records:directoryRuns.map(id=>({run_id:id,revision:2,data:{...row,id},archive_receipt:null})),next_id:directoryRuns.at(-1)??null,has_more:false};
   if(name==='events')return {version:1,owner_id:activeOwner,run_id:args.run,through_sequence:0,records:[],has_more:false,next_sequence:0};
   const details=options.assessment;
   const data=args.kind==='runs'?[{...row,id:args.run,...(details?{execution_policy:details.execution_policy,generation:1}:{})}]
    :args.kind==='probes'?details?.probes??[]:args.kind==='evaluations'?details?.evaluations??[]:[];
   const records=data.map(d=>({revision:2,key:args.kind==='evaluations'?d.cohort.iteration_id:d.id,command_id:start,data:d}));
   return {version:1,owner_id:activeOwner,run_id:args.run,kind:args.kind,through_revision:2,records,has_more:false,next_cursor:records.length?{revision:2,key:records.at(-1).key}:null};
  },
  async worker(name,args,signal){requests.push({name,args,signal});
   if(options.workerClosed)throw new paper.PaperWorkerClosedError();
   if(options.workerFails)throw Error('private worker failure');
   if(name==='status')return state();
   if(name==='controls')return {...state(),start_id:start,stop_id:stop};
   if(options.controlGate)await options.controlGate.promise;
   if(options.startFails&&name==='start'){phase='pending';throw Error('private transport failure');}
   phase=name==='stop'?'stopped':'running';return state();
  },
 };
 const {PaperDashboardSession:PaperDashboard,PaperDashboard:Outer}=load('src/components/probes/PaperDashboard.tsx',{
  react,'react/jsx-runtime':{jsx:(type,props,key)=>({type,props,key}),jsxs:(type,props,key)=>({type,props,key})},
  '@/lib/probes/paper-api':paper,'@/lib/probes/durable-read-model':durable,
  '@/lib/probes/probes-supabase':{fetchColonyRuns:async()=>[]},
 },{process:{env:{}},crypto:{randomUUID:()=>stop},
  setTimeout:later,clearTimeout:id=>timers.delete(id),
  setInterval:(fn,delay)=>later(fn,delay),clearInterval:id=>timers.delete(id)});
 let props={owner,token:'synthetic-A',apiOverride:api,legacyReader:async()=>[]};
 assert.equal(Outer(props).key,owner);
 let mountedOwner=owner;
 function render(){
  if(mountedOwner!==props.owner){for(const h of hooks)h.cleanup?.();hooks.length=0;mountedOwner=props.owner;}
  assert.equal(Outer(props).key,props.owner);
  index=0;dirty=false;tree=PaperDashboard(props);while(effects.length)effects.shift()();
 }
 function nodes(node){if(!node||typeof node!=='object')return [];return [node,...[node.props?.children].flat(Infinity).flatMap(nodes)];}
 const text=node=>nodes(node).flatMap(n=>[n.props?.children].flat(Infinity).filter(v=>typeof v==='string'||typeof v==='number')).join(' ').replace(/\s+/g,' ').trim();
 render();
 return {requests,reads,api,
  async flush(){for(let i=0;i<4;i++){await new Promise(setImmediate);if(dirty)render();}},
  click(label){const b=nodes(tree).find(n=>n.type==='button'&&text(n)===label);assert.ok(b,label);assert.ok(!b.props.disabled,label+' disabled');b.props.onClick();if(dirty)render();},
  doubleClick(label){const b=nodes(tree).find(n=>n.type==='button'&&text(n)===label);assert.ok(b);b.props.onClick();b.props.onClick();if(dirty)render();},
  changeToken(){props={...props,token:'synthetic-B'};render();},
  changeOwner(){activeOwner=otherOwner;props={...props,owner:otherOwner,token:'synthetic-other'};directoryRuns.length=0;render();},
  changeWorker(id){workerRun=id;phase='pending';},
  addRun(id){directoryRuns.push(id);directoryRuns.sort();},
  selectRun(id){nodes(tree).find(n=>n.type==='select').props.onChange({target:{value:id}});if(dirty)render();},
  advance(ms){now+=ms;for(const [id,timer] of [...timers])if(timer.at<=now){timers.delete(id);timer.fn();}if(dirty)render();},
  timerCount(){return timers.size;},
  dispose(){for(const h of hooks)h.cleanup?.();},
  text(){return text(tree);},
 };
}
test('actual paper view retains the original uncertain start and settles it without a second launch',async()=>{
 const h=harness({startFails:true});await h.flush();h.click('Start configured pilot');await h.flush();
 assert.match(h.text(),/Original start request retained/);assert.doesNotMatch(h.text(),/private transport failure/);
 h.click('Refresh status and history');await h.flush();
 h.click('Settle original operation');await h.flush();
 const controls=h.requests.filter(r=>r.args);assert.deepEqual(controls.map(r=>r.name),['start','settle']);
 assert.ok(controls.every(r=>r.args.request_id===start));h.dispose();
});
test('synchronous double click cannot create two retained starts',async()=>{
 const gate=deferred(),h=harness({controlGate:gate});await h.flush();h.doubleClick('Start configured pilot');
 assert.equal(h.requests.filter(r=>r.name==='start').length,1);
 gate.resolve();await h.flush();assert.equal(h.requests.filter(r=>r.name==='start').length,1);h.dispose();
});
test('token replacement aborts old history and retired control replies cannot publish',async()=>{
 const gate=deferred(),h=harness({controlGate:gate});await h.flush();h.click('Start configured pilot');
 const oldSignals=h.reads.map(r=>r.signal).filter(Boolean);h.changeToken();await h.flush();
 assert.ok(oldSignals.every(s=>s.aborted));gate.resolve();await h.flush();
 assert.match(h.text(),/Original start request retained/);h.dispose();
});
test('uncertain archive refresh and retry reuse exactly the original revision and ID',async()=>{
 const h=harness({phase:'stopped',archiveFails:true});await h.flush();h.click('Archive stopped run, retain history');await h.flush();
 assert.match(h.text(),/Archive outcome is uncertain/);h.click('Refresh status and history');await h.flush();
 h.click('Archive stopped run, retain history');await h.flush();
 const a=h.reads.filter(r=>r.name==='archive_run');assert.equal(a.length,2);assert.deepEqual(a[0].args,a[1].args);
 assert.equal(a[0].args.expected_revision,2);h.dispose();
});
test('unmount cancels the complete read and late discovery does not publish private data',async()=>{
 const gate=deferred(),h=harness({readGate:gate});h.dispose();assert.ok(h.reads.every(r=>r.signal.aborted));
 gate.resolve();await h.flush();assert.doesNotMatch(h.text(),/Committed revision/);
});
test('worker outage still publishes owner-bound committed history and blocks controls',async()=>{
 const h=harness({workerFails:true});await h.flush();
 assert.match(h.text(),/Committed revision 2/);assert.match(h.text(),/Unable to verify the paper worker/);
 assert.doesNotMatch(h.text(),/private worker failure/);assert.throws(()=>h.click('Start configured pilot'),/disabled/);h.dispose();
});
test('failed worker identifies reconciliation separately from retained committed history',async()=>{
 const h=harness({phase:'failed'});await h.flush();
 assert.match(h.text(),/The worker requires reconciliation/);
 assert.match(h.text(),/Committed history may precede the failure/);
 assert.match(h.text(),/Committed revision 2/);
 assert.throws(()=>h.click('Start configured pilot'),/disabled/);h.dispose();
});
test('slow complete history is not cancelled by periodic worker status polling',async()=>{
 const gate=deferred(),h=harness({readGate:gate});await h.flush();
 const original=h.reads[0].signal;
 h.advance(10000);await h.flush();h.advance(10000);await h.flush();
 assert.equal(original.aborted,false);assert.equal(h.reads.length,1);
 assert.equal(h.requests.filter(r=>r.name==='status').length,3);
 assert.doesNotMatch(h.text(),/Committed revision/);
 gate.resolve();await h.flush();assert.match(h.text(),/Committed revision 2/);
 const completedReads=h.reads.length;
 h.advance(9999);await h.flush();assert.equal(h.reads.length,completedReads);
 h.advance(1);await h.flush();assert.ok(h.reads.length>completedReads);
 h.dispose();assert.equal(h.timerCount(),0);
});
test('explicit refresh cancels a pending history cycle and keeps one replacement',async()=>{
 const gate=deferred(),h=harness({readGate:gate});await h.flush();
 const original=h.reads[0].signal;h.click('Refresh status and history');await h.flush();
 assert.equal(original.aborted,true);assert.equal(h.reads.length,2);
 assert.equal(h.reads[1].signal.aborted,false);
 gate.resolve();await h.flush();assert.match(h.text(),/Committed revision 2/);h.dispose();
 assert.equal(h.timerCount(),0);
});
test('refresh while Start is in flight cannot unlock a second command or settlement',async()=>{
 const gate=deferred(),h=harness({controlGate:gate});await h.flush();h.click('Start configured pilot');
 h.click('Refresh status and history');await h.flush();
 assert.throws(()=>h.click('Start configured pilot'),/disabled/);
 assert.throws(()=>h.click('Settle original operation'),/disabled/);
 assert.equal(h.requests.filter(r=>r.args).length,1);gate.resolve();await h.flush();h.dispose();
});
test('explicit closed worker response is distinct from outage and preserves history',async()=>{
 const h=harness({workerClosed:true});await h.flush();
 assert.match(h.text(),/closed by configuration/);assert.match(h.text(),/Committed revision 2/);
 assert.match(h.text(),/does not verify a configured owner or run/);
 assert.doesNotMatch(h.text(),/Unable to verify the paper worker/);
 assert.throws(()=>h.click('Start configured pilot'),/disabled/);h.dispose();
});
test('a historical selection never becomes a command target; acknowledged Start follows only discovered history',async()=>{
 const h=harness({workerRun:newer});await h.flush();
 assert.match(h.text(),new RegExp('Configured worker run: '+newer));assert.match(h.text(),/different historical run/);
 h.click('Start configured pilot');await h.flush();
 assert.match(h.text(),/waiting for owner-bound discovery/);
 assert.match(h.text(),new RegExp('Selected history: '+run));
 assert.equal(h.requests.find(r=>r.name==='start').args.request_id,start);
 h.addRun(newer);h.advance(10000);await h.flush();
 assert.match(h.text(),new RegExp('Selected history: '+newer));
 assert.doesNotMatch(h.text(),/waiting for owner-bound discovery/);h.dispose();
});
test('deliberate browsing during delayed Start is preserved when acknowledgment arrives',async()=>{
 const gate=deferred(),h=harness({controlGate:gate,workerRun:newer,directoryRuns:[run,newer]});await h.flush();
 h.click('Start configured pilot');h.selectRun(run);await h.flush();gate.resolve();await h.flush();
 assert.match(h.text(),new RegExp('Selected history: '+run));
 assert.match(h.text(),/different historical run/);assert.doesNotMatch(h.text(),/waiting for owner-bound discovery/);h.dispose();
});
test('deployment turnover blocks settlement with old retained IDs on the new configured run',async()=>{
 const h=harness({startFails:true});await h.flush();h.click('Start configured pilot');await h.flush();
 h.changeWorker(newer);h.click('Refresh status and history');await h.flush();
 assert.match(h.text(),/configured worker changed/);assert.match(h.text(),new RegExp('Original control run: '+run));
 assert.throws(()=>h.click('Settle original operation'),/disabled/);
 assert.equal(h.requests.filter(r=>r.args).length,1);h.dispose();
});
test('account replacement immediately remounts private history and ignores old control replies',async()=>{
 const gate=deferred(),h=harness({controlGate:gate});await h.flush();h.click('Start configured pilot');
 h.changeOwner();assert.doesNotMatch(h.text(),/Committed revision|Original start request/);
 gate.resolve();await h.flush();assert.doesNotMatch(h.text(),/Committed revision|Original start request/);h.dispose();
});
test('richer view labels candidate evidence, completed scores and aborted children without claiming live promotion',async()=>{
 const h=harness({workerClosed:true,assessment});await h.flush();
 assert.match(h.text(),/3 \/ 20/);assert.match(h.text(),/generation 1/);
 assert.match(h.text(),/crossover_mutation/);assert.match(h.text(),/genetic_parent\s*:\s*Synthetic-0-0/);
 assert.match(h.text(),/Observed maximum drawdown 0.0900%/);
 assert.match(h.text(),/last observed closed-trade count 0/);
 assert.match(h.text(),/fitness -0.001100 · 1 trades/);
 assert.match(h.text(),/last_observed_before_replacement/);assert.match(h.text(),/Retained, worker not running/);
 assert.match(h.text(),/Recorded ROI 0.0700% · fitness -0.001100/);
 assert.match(h.text(),/Recorded ROI unavailable · fitness unavailable/);
 assert.match(h.text(),/completed cohort; selection input/);assert.match(h.text(),/withheld from selection/);
 assert.match(h.text(),/Fee 0 bps · slippage 0 bps · half-spread 0 bps/);
 assert.match(h.text(),/Formula\/version metadata and final-score drawdown are not persisted/);
 assert.match(h.text(),/does not establish profitability or promotion/);h.dispose();
});
test('malformed richer read preserves the last complete snapshot instead of publishing partial values',async()=>{
 const data=structuredClone(assessment),h=harness({workerClosed:true,assessment:data});await h.flush();
 assert.match(h.text(),/Recorded ROI 0.0700%/);
 data.probes[0].genome.ema_fast='inf';h.click('Refresh status and history');await h.flush();
 assert.match(h.text(),/Unable to refresh committed history/);
 assert.match(h.text(),/Recorded ROI 0.0700%/);assert.match(h.text(),/3 \/ 20/);h.dispose();
});
test('a stale status read started before command acknowledgment cannot regress the worker to fresh',async()=>{
 const gate=deferred(),h=harness();await h.flush();const worker=h.api.worker;
 let blocked=true;
 h.api.worker=async(name,...args)=>{
  if(name==='status'&&blocked){blocked=false;const before=await worker(name,...args);await gate.promise;return before;}
  return worker(name,...args);
 };
 h.advance(10000);await h.flush();h.click('Start configured pilot');await h.flush();
 gate.resolve();await h.flush();assert.match(h.text(),/Worker: running/);
 assert.throws(()=>h.click('Start configured pilot'),/disabled/);h.dispose();
});
