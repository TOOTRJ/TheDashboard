// Compile the pure module in a disposable directory, with no application env.
import assert from 'node:assert/strict';
import { test, after } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import cp from 'node:child_process';
import { pathToFileURL } from 'node:url';
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dashboard-read-model-'));
after(() => fs.rmSync(dir, { recursive: true, force: true }));
cp.execFileSync(process.execPath, ['node_modules/typescript/bin/tsc', 'src/lib/probes/durable-read-model.ts',
  '--target', 'ES2017', '--lib', 'esnext,dom', '--module', 'commonjs', '--strict', '--skipLibCheck', '--outDir', dir], { env: { PATH: process.env.PATH } });
const m = (await import(pathToFileURL(path.join(dir, 'durable-read-model.js')).href)).default;
const owner='00000000-0000-0000-0000-000000000001', run='00000000-0000-0000-0000-000000000002',
 command='00000000-0000-0000-0000-000000000003', probe='00000000-0000-0000-0000-000000000004';
const row=(revision,key=probe) => ({ revision, command_id:command, key, data:{ id:probe, account_currency:'USD' } });
const page=(records, more=false, revision=2) => ({ version:1, owner_id:owner, run_id:run, kind:'probes',
 through_revision:revision, records, has_more:more, next_cursor:records.length ? { revision:records.at(-1).revision, key:records.at(-1).key } : null });
test('exact USD display uses integer rounding, including signed tiny amounts and large cash', () => {
 assert.equal(m.displayUSD('9999999999999.995'), '10000000000000.00');
 assert.equal(m.displayUSD('0.000000000000000000000000000000000001',36), '0.000000000000000000000000000000000001');
 assert.equal(m.displayUSD('-1.005'), '-1.01'); assert.equal(m.displayUSD('-0.0001'), '0.00');
 for(const bad of [1.1,'NaN','1e2','01','0.1234567890123456789012345678901234567']) assert.throws(()=>m.displayUSD(bad));
});
test('exact drawdown fractions have explicit bounded percentage display', () => {
 assert.equal(m.displayDrawdownPct({numerator:'1',denominator:'3'}),'33.33%');
 assert.equal(m.displayDrawdownPct({numerator:'1',denominator:'20000'}),'0.01%');
 for (const bad of [{numerator:'1',denominator:'0'},{numerator:'2',denominator:'1'},{numerator:1,denominator:'2'}]) assert.throws(()=>m.displayDrawdownPct(bad));
});
test('tagged genes/scores decode finite hex floats without using them for money', () => {
 assert.equal(m.taggedFloat64({float64:'0x1.8000000000000p+1'}),3);
 assert.equal(m.taggedFloat64({float64:'-0x1.0000000000000p-1'}),-.5);
 assert.equal(m.taggedFloat64({float64:'0x0.0000000000001p-1022'}),Number.MIN_VALUE);
 for(const bad of [{float64:'inf'},{float64:'0x1.0p+1024'},{float64:'0x1.0p+0',other:1}]) assert.throws(()=>m.taggedFloat64(bad));
});
test('retired terminal capital stays separate from zero account cash and unavailable equity', () => {
 const p={id:probe, account_currency:'USD',initial_cash:'100',economic_cash:'0.000',retired:true,
 terminal_cash:'87.1234567890123456789',equity:null,equity_basis:'terminal_frozen',metrics_basis:'last_observed_before_replacement'};
 assert.equal(m.probeBalances(p).terminalCash,p.terminal_cash);
 for(const bad of [{...p,economic_cash:'87'},{...p,equity:'87'},{...p,account_currency:'USDC'},{...p,terminal_cash:null}]) assert.throws(()=>m.probeBalances(bad));
});
test('collector pins revision, checks cursor, and publishes all pages once complete', async () => {
 let calls=0;
 const r=await m.collectProjectionPages(async args=>{calls++; assert.equal(args.through_revision,calls===1?null:2);
 return calls===1?page([row(1)],true):page([row(2)]);},owner,run,'probes');
 assert.equal(r.records.length,2);assert.equal(r.throughRevision,2);
 assert.equal(m.latestEntities(r.records).length,1); assert.equal(m.latestEntities(r.records)[0].revision,2);
});
test('foreign identity, changing snapshots, lying cursor and repeated rows fail without partial publication', async()=>{
 for(const mutate of [p=>({...p,owner_id:run}),p=>({...p,through_revision:3}),p=>({...p,next_cursor:{revision:2,key:run}}),p=>({...p,records:[row(1)]})]) {
 let calls=0;
 await assert.rejects(m.collectProjectionPages(async()=>++calls===1?page([row(1)],true):mutate(page([row(2)])),owner,run,'probes'));
 }
});
test('caller cancellation settles even if injected RPC ignores its signal', async()=>{
 const control=new AbortController();
 const pending=m.collectProjectionPages(()=>new Promise(()=>{}),owner,run,'probes',control.signal);
 control.abort(); await assert.rejects(pending);
});
