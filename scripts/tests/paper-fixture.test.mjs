import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import test from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as durable from '../../src/lib/probes/durable-read-model.ts';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
function load(path,modules){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(root+'/'+path,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports,require(name){assert.ok(Object.hasOwn(modules,name),name);return modules[name];},URL,Response,TextDecoder,TextEncoder,Uint8Array,AbortController,setTimeout,clearTimeout,structuredClone,fetch(){throw Error('Real network is forbidden');}});return exports;}
const paper=load('src/lib/probes/paper-api.ts',{'./durable-read-model':durable});
const fixture=load('scripts/browser-fixtures/paper-data.ts',{'@/lib/probes/paper-api':paper});
test('public paper fixtures exercise both owners through actual adapters without network access', async () => {
let checked=0;
for(const actor of ['alice','bob']){
 const owner=fixture.PAPER_FIXTURE_ACTORS[actor].owner,c=fixture.createPaperFixtureController(owner),signal=new AbortController().signal;
 const directory=await paper.discoverRuns(c.api,owner,signal);assert.equal(directory.length,2);checked++;
 const snapshot=await paper.runSnapshot(c.api,owner,c.historyRun,signal);assert.equal(snapshot.probes.length,16);assert.equal(snapshot.trades.length,2);assert.equal(snapshot.evaluations.length,2);checked++;
 const events=await paper.eventSnapshot(c.api,owner,c.historyRun,signal);assert.equal(events.length,1);checked++;
 const controls=paper.workerControls(await c.api.worker('controls'),owner);assert.equal(controls.start,c.originalStart);checked++;
 assert.equal(paper.workerStatus(await c.api.worker('status'),owner,controls.run).phase,'fresh');checked++;
 c.setScenario('lost-start-ack');await assert.rejects(c.api.worker('start',{request_id:c.originalStart}));
 assert.equal(paper.workerStatus(await c.api.worker('status'),owner,controls.run).phase,'pending');
 assert.equal(paper.workerStatus(await c.api.worker('settle',{request_id:c.originalStart}),owner,controls.run).phase,'running');checked++;
 c.setScenario('lost-stop-ack');await assert.rejects(c.api.worker('stop',{request_id:c.originalStop}));
 assert.equal(paper.workerStatus(await c.api.worker('status'),owner,controls.run).stop_requested,true);
 assert.equal(paper.workerStatus(await c.api.worker('settle',{request_id:c.originalStart}),owner,controls.run).phase,'stopped');checked++;
 await assert.rejects(c.api.worker('start',{request_id:c.originalStop}));checked++;
 c.setScenario('unknown-policy');const future=await paper.runSnapshot(c.api,owner,c.historyRun,signal);
 assert.equal(paper.evaluationDetails(future.evaluations[0].data).windowPolicy,'future-window-v9');checked++;
 for(const mode of ['unknown-version','read-error','oversized-read']){c.setScenario(mode);await assert.rejects(paper.runSnapshot(c.api,owner,c.historyRun,signal));checked++;}
 c.resetWorker();c.holdNext('read','discover');const abort=new AbortController();
 const held=c.api.read('discover',{},abort.signal);const gate=c.snapshot().pending[0];assert.ok(gate);abort.abort();
 assert.equal(c.snapshot().pending[0].signalAborted,true);c.release(gate.id);const original=await held;assert.equal(original.owner_id,owner);checked++;
 c.holdNext('worker','start');const ack=c.api.worker('start',{request_id:c.originalStart});const pending=c.snapshot().pending[0];assert.equal(pending.trace.requestId,c.originalStart);
 c.reject(pending.id);await assert.rejects(ack);checked++;
 c.setScenario('closed-worker');await assert.rejects(c.api.worker('controls'),error=>error instanceof paper.PaperWorkerClosedError);checked++;
 c.dispose();
}
assert.throws(()=>fixture.createPaperFixtureController('30000000-0000-4000-8000-000000000003'));checked++;
assert.equal(checked,31);
});
