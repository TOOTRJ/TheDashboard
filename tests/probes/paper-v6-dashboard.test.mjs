import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as durable from '../../src/lib/probes/durable-read-model.ts';

const owner='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222',
 run='33333333-3333-4333-8333-333333333333';
function load(file,modules,globals={}) {
 const exports={};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,
 {exports,require(name){assert.ok(Object.hasOwn(modules,name),name);return modules[name];},
 AbortController,URL,setTimeout,clearTimeout,...globals});
 return exports;
}
const protocol=load('src/lib/probes/paper-v6-api.ts',{'./durable-read-model':durable});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
function harness(options={}) {
 const hooks=[],effects=[],calls=[],timers=new Map();let index=0,dirty=false,rendering=false,tree,timerId=0,random=0;
 const same=(a,b)=>a&&b&&a.length===b.length&&a.every((value,i)=>Object.is(value,b[i]));
 const memo=(fn,deps)=>{const cell=index++;if(!hooks[cell]||!same(hooks[cell].deps,deps))hooks[cell]={deps,value:fn()};return hooks[cell].value;};
 const effect=layout=>(fn,deps)=>{const cell=index++;if(!hooks[cell]||!same(hooks[cell].deps,deps)){
  const entry={deps,cleanup:hooks[cell]?.cleanup};hooks[cell]=entry;effects.push({layout,run(){entry.cleanup?.();entry.cleanup=fn();}});}};
 const react={useMemo:memo,useEffect:effect(false),useLayoutEffect:effect(true),
  useRef:value=>memo(()=>new Proxy({current:value},{get(target,key){if(key==='current')assert.equal(rendering,false);return Reflect.get(target,key);},
   set(target,key,value){if(key==='current')assert.equal(rendering,false);return Reflect.set(target,key,value);}}),[]),
  useState(value){const cell=index++;hooks[cell]??={value:typeof value==='function'?value():value};const entry=hooks[cell];
   return [entry.value,next=>{if(hooks[cell]!==entry)return;const result=typeof next==='function'?next(entry.value):next;
    if(!Object.is(entry.value,result)){entry.value=result;dirty=true;}}];}};
 let activeOwner=owner,failures=options.failures??0,workerFails=false;
 const state={version:6,owner_id:owner,run_id:run,phase:options.phase??'idle',sequence:0,revision:0,generation:0,epoch:0,
  busy:false,requires_reconciliation:options.requiresReconciliation??false,last_request_id:null,projection:null,
  warmup:options.warmup??null};
 const api={async status(signal){calls.push({kind:'status',signal});if(workerFails)throw Error('private-server-error');return {...state,owner_id:activeOwner};},
  async history(after,limit,signal){calls.push({kind:'history',after,limit,signal});if(options.historyFails)throw Error('private-history-error');
   return {version:6,owner_id:activeOwner,run_id:run,through_sequence:state.sequence,next_sequence:state.sequence,
    has_more:false,records:Array.from({length:state.sequence-after},(_,i)=>({sequence:after+i+1,kind:'decision',data:{assessments:[]}}))};},
  async command(action,request,signal){calls.push({kind:action,request,signal});
   if(options.gate)await options.gate.promise;
   if(failures-->0)throw Error('private-transport-error');
   state.phase=action==='start'?'running':'stopped';state.last_request_id=request;state.sequence++;state.revision++;
   return {...state,owner_id:activeOwner};}};
 const {PaperV6DashboardSession:Session,PaperV6Dashboard:Outer}=load('src/components/probes/PaperV6Dashboard.tsx',{
  react,'react/jsx-runtime':{jsx:(type,props,key)=>({type,props,key}),jsxs:(type,props,key)=>({type,props,key})},
  '@/lib/probes/durable-read-model':durable,'@/lib/probes/paper-v6-api':protocol},
  {process:{env:{}},crypto:{randomUUID:()=>`44444444-4444-4444-8444-${String(++random).padStart(12,'0')}`},
   setTimeout:(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;},clearTimeout:id=>timers.delete(id)});
 let props={owner,token:'synthetic-A',apiOverride:api},mountedOwner=owner;
 const nodes=node=>!node||typeof node!=='object'?[]:[node,...[node.props?.children].flat(Infinity).flatMap(nodes)];
 const text=node=>nodes(node).flatMap(n=>[n.props?.children].flat(Infinity).filter(v=>typeof v==='string'||typeof v==='number')).join(' ').replace(/\s+/g,' ').trim();
 function render(){
  if(mountedOwner!==props.owner){for(const hook of hooks)hook.cleanup?.();hooks.length=0;effects.length=0;mountedOwner=props.owner;}
  assert.equal(Outer(props).key,props.owner);index=0;dirty=false;rendering=true;try{tree=Session(props);}finally{rendering=false;}
  for(const layout of [true,false]){let i;while((i=effects.findIndex(effect=>effect.layout===layout))>=0)effects.splice(i,1)[0].run();}
 }
 function button(label){const result=nodes(tree).find(n=>n.type==='button'&&text(n)===label);assert.ok(result,label);return result;}
 render();
 return {calls,state,
  async flush(){for(let i=0;i<5;i++){await new Promise(setImmediate);if(dirty)render();}},
  click(label){const b=button(label);assert.equal(!!b.props.disabled,false,label);b.props.onClick();if(dirty)render();},
  doubleClick(label){const b=button(label);b.props.onClick();b.props.onClick();if(dirty)render();},
  disabled:label=>!!button(label).props.disabled,
  text:()=>text(tree),
  changeToken(){props={...props,token:'synthetic-B'};render();},
  changeOwner(){activeOwner=other;props={...props,owner:other,token:'synthetic-other'};render();},
  failWorker(){workerFails=true;},
  tick(){for(const [id,timer]of[...timers]){timers.delete(id);timer.fn();}if(dirty)render();},
  dispose(){for(const hook of hooks)hook.cleanup?.();},
  timerCount:()=>timers.size};
}

test('actual v6 dashboard starts, observes later generations, then stops the owner run',async()=>{
 const h=harness();await h.flush();h.click('Start paper trading');await h.flush();
 assert.match(h.text(),/Worker: running/);assert.equal(h.disabled('Start paper trading'),true);
 h.state.generation=2;h.state.epoch=3;h.tick();await h.flush();assert.match(h.text(),/Generation 2 · source epoch 3/);
 h.click('Stop and retain holdings');await h.flush();assert.match(h.text(),/Worker: stopped/);
 assert.deepEqual(h.calls.filter(call=>['start','stop'].includes(call.kind)).map(call=>call.kind),['start','stop']);h.dispose();
});
test('uncertain v6 control retry preserves its original request identity',async()=>{
 const h=harness({failures:1});await h.flush();h.click('Start paper trading');await h.flush();
 assert.match(h.text(),/control acknowledgment is uncertain/);assert.doesNotMatch(h.text(),/private-transport/);
 h.click('Retry original start');await h.flush();const controls=h.calls.filter(call=>call.kind==='start');
 assert.equal(controls.length,2);assert.equal(controls[0].request,controls[1].request);assert.match(h.text(),/Worker: running/);h.dispose();
});
test('v6 double click creates only one owned command; token replacement aborts the original request',async()=>{
 const gate=deferred(),h=harness({gate});await h.flush();h.doubleClick('Start paper trading');
 assert.equal(h.calls.filter(call=>call.kind==='start').length,1);const signal=h.calls.find(call=>call.kind==='start').signal;
 h.changeToken();assert.equal(signal.aborted,true);gate.resolve();await h.flush();
 assert.doesNotMatch(h.text(),/private/);h.dispose();
});
test('v6 worker outage disables controls and cleanup cancels polling',async()=>{
 const h=harness();await h.flush();h.failWorker();h.tick();await h.flush();
 assert.equal(h.disabled('Start paper trading'),true);assert.match(h.text(),/Unable to verify worker status/);
 assert.doesNotMatch(h.text(),/private-server-error/);h.dispose();assert.equal(h.timerCount(),0);
});
test('owner replacement unmounts private retained v6 control state',async()=>{
 const gate=deferred(),h=harness({gate});await h.flush();h.click('Start paper trading');h.changeOwner();
 gate.resolve();await h.flush();assert.doesNotMatch(h.text(),/Original start request retained/);h.dispose();
});
test('verified recovery status keeps Stop available before committed history is readable',async()=>{
 const h=harness({phase:'recovering'});h.state.busy=true;await h.flush();
 assert.equal(h.disabled('Stop and retain holdings'),false);assert.match(h.text(),/Stop remains available during recovery/);
 assert.equal(h.calls.filter(call=>call.kind==='history').length,0);
 h.click('Stop and retain holdings');await h.flush();assert.equal(h.calls.filter(call=>call.kind==='stop').length,1);h.dispose();
});
test('waiting for valid data remains an explicit stoppable state',async()=>{
 const h=harness({phase:'waiting_data'});await h.flush();
 assert.match(h.text(),/Waiting for the next valid provider observation/);assert.equal(h.disabled('Stop and retain holdings'),false);
 h.dispose();
});
test('failed and pending verified runs remain stoppable even when history or reconciliation is unavailable',async()=>{
 for(const phase of ['failed','pending','risk_halted']){
  const h=harness({phase,requiresReconciliation:true,historyFails:true});await h.flush();
  assert.equal(h.disabled('Stop and retain holdings'),false);h.click('Stop and retain holdings');await h.flush();
  assert.equal(h.calls.filter(call=>call.kind==='stop').length,1);assert.doesNotMatch(h.text(),/private-history-error/);h.dispose();
 }
});
test('an independent Stop can supersede uncertain Start while retaining its original identity',async()=>{
 const h=harness({failures:1});await h.flush();h.click('Start paper trading');await h.flush();
 const original=h.calls.find(call=>call.kind==='start').request;
 assert.equal(h.disabled('Stop and retain holdings'),false);h.click('Stop and retain holdings');await h.flush();
 const controls=h.calls.filter(call=>['start','stop'].includes(call.kind));
 assert.equal(controls.length,2);assert.deepEqual(controls.map(call=>call.kind),['start','stop']);
 assert.notEqual(controls[0].request,controls[1].request);assert.ok(h.text().includes(original));
 assert.match(h.text(),/Earlier uncertain Start retained/);h.dispose();
});
test('a genuine retained history gap explicitly requires a new pilot instead of implying retry repairs it',async()=>{
 const h=harness({phase:'waiting_data',warmup:{observed_minutes:4,required_minutes:915,history_gap:true}});await h.flush();
 assert.match(h.text(),/This run cannot reconstruct it/);assert.match(h.text(),/Stop this run and configure a new paper pilot/);
 assert.equal(h.disabled('Stop and retain holdings'),false);h.dispose();
});
