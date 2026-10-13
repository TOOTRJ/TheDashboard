import test from 'node:test';
import assert from 'node:assert/strict';
import {A,B,account,deferred,harness} from './helpers/portfolio-harness.mjs';
const set=(h,id,value)=>h.input(id).onChange({target:{value}});
const changeGoal=async(h,amount)=>{set(h,'goal-amount',String(amount));await h.flush();};
for(const kind of ['add','edit','delete','goal']) test(`retired ${kind} response cannot publish into B`,async()=>{
 const h=harness();await h.flush();const gate=deferred();let old;
 if(kind==='add'){set(h,'new-account-name','A new secret');set(h,'new-account-balance','789');await h.flush();}
 if(kind==='edit'){h.button(`Edit Private ${A}`).onClick();await h.flush();set(h,`edit-name-account-${A}`,'A edit secret');await h.flush();}
 if(kind==='goal')await changeGoal(h,333);
 h.controllers[kind]=()=>gate.promise;
 if(kind==='add')old=h.button('Add account').onClick();
 if(kind==='edit')old=h.button('Save').onClick();
 if(kind==='delete')old=h.button(`Delete Private ${A}`).onClick();
 if(kind==='goal')old=h.button('Save goal').onClick();
 h.change(B,'B-1');assert.ok(!h.text().includes('A new secret'));assert.ok(!h.text().includes(`Private ${A}`));await h.flush();
 gate.resolve(kind==='add'||kind==='edit'?account(A,'A reply secret',789):true);await old;await h.flush();
 assert.ok(h.text().includes('B private'));assert.ok(!h.text().includes('A reply secret'));assert.equal(h.input('goal-amount').value,'200');
 assert.equal(h.input('new-account-name').value,'');assert.equal(h.retiredWrites(),0);assert.equal(h.toasts.length,0);h.dispose();
});
test('logout and same-owner new login retire drafts, editor and pending hydration',async()=>{
 const h=harness();await h.flush();const oldKey=h.key();set(h,'new-account-name','private draft');set(h,'goal-amount','999');h.button(`Edit Private ${A}`).onClick();await h.flush();
 h.change(null);assert.match(h.text(),/Sign in/);assert.equal(h.input('goal-amount'),undefined);
 h.controllers.read=()=>Promise.resolve([account(A)]);h.change(A,'A-2');assert.notEqual(h.key(),oldKey);await h.flush();
 assert.equal(h.input('new-account-name').value,'');assert.equal(h.input(`edit-name-account-${A}`),undefined);assert.equal(h.input('goal-amount').value,'100');h.dispose();
});
test('delayed A hydration and failed read cannot publish or fabricate B zero',async()=>{
 const h=harness();await h.flush();h.change(null);const gate=deferred();h.controllers.read=call=>call.scope.ownerId===A?gate.promise:Promise.reject(new Error('private provider detail'));
 h.change(A,'A-2');h.change(B,'B-1');await h.flush();assert.match(h.text(),/data is unavailable/);assert.ok(!h.text().includes('No accounts yet'));assert.equal(h.input('goal-amount'),undefined);
 gate.resolve([account(A,'late secret')]);await h.flush();assert.ok(!h.text().includes('late secret'));assert.ok(!h.text().includes('private provider detail'));
 delete h.controllers.read;h.button('Retry portfolio read').onClick();await h.flush();assert.ok(h.text().includes('B private'));h.dispose();
});
test('same-login token refresh preserves draft; Strict Mode replacement invalidates old requests',async()=>{
 const h=harness();await h.flush();set(h,'new-account-name','keep draft');await h.flush();const key=h.key();h.refresh();await h.flush();assert.equal(h.key(),key);assert.equal(h.input('new-account-name').value,'keep draft');
 const gate=deferred();h.controllers.add=()=>gate.promise;const old=h.button('Add account').onClick();h.strictReplace();await h.flush();gate.resolve(account(A,'retired strict'));await old;await h.flush();assert.ok(!h.text().includes('retired strict'));assert.equal(h.retiredWrites(),0);h.dispose();
});
test('failed Undo retains acknowledged goal; retired Undo never writes',async()=>{
 const h=harness();await h.flush();await changeGoal(h,333);await h.button('Save goal').onClick();await h.flush();
 const undo=h.toasts.find(t=>t.args[0]==='Portfolio goal saved').args[1].action.onClick;
 h.controllers.goal=()=>Promise.resolve(false);await undo();await h.flush();assert.equal(h.input('goal-amount').value,'333');assert.ok(h.toasts.some(t=>t.args[0]==='Could not revert goal'));assert.ok(!h.toasts.some(t=>t.args[0]==='Goal reverted'));
 const count=h.calls.length;h.change(null);h.change(A,'A-2');await h.flush();await undo();assert.equal(h.calls.filter(c=>c.kind==='goal').length,2);assert.ok(h.calls.length>=count);h.dispose();
});
test('late Undo response cannot overwrite newer login; newer draft invalidates saved Undo',async()=>{
 const h=harness();await h.flush();await changeGoal(h,333);await h.button('Save goal').onClick();await h.flush();const undo=h.toasts[0].args[1].action.onClick;
 const gate=deferred();h.controllers.goal=()=>gate.promise;const old=undo();h.change(B,'B-1');await h.flush();gate.resolve(true);await old;await h.flush();assert.equal(h.input('goal-amount').value,'200');assert.ok(!h.toasts.some(t=>t.args[0]==='Goal reverted'));assert.equal(h.retiredWrites(),0);
 h.change(A,'A-2');await h.flush();delete h.controllers.goal;await changeGoal(h,444);await h.button('Save goal').onClick();await h.flush();const latest=h.toasts.at(-1).args[1].action.onClick;await changeGoal(h,555);const calls=h.calls.length;await latest();assert.equal(h.calls.length,calls);assert.equal(h.input('goal-amount').value,'555');h.dispose();
});
test('one mutation owns pending state before repaint and failure preserves account/draft',async()=>{
 const h=harness();await h.flush();set(h,'new-account-name','retry retained');await h.flush();const add=h.button('Add account').onClick,gate=deferred();h.controllers.add=()=>gate.promise;
 const first=add();await add();await h.flush();assert.equal(h.calls.filter(c=>c.kind==='add').length,1);assert.equal(h.button(`Delete Private ${A}`).disabled,true);
 gate.reject(new Error('private detail'));await first;await h.flush();assert.equal(h.input('new-account-name').value,'retry retained');assert.ok(!h.toasts.some(t=>t.name==='success'));assert.ok(!h.text().includes('private detail'));assert.equal(h.button('Add account').disabled,false);h.dispose();
});
test('zero-row delete and failed goal acknowledge no change; successful Undo restores original',async()=>{
 const h=harness();await h.flush();h.controllers.delete=()=>Promise.resolve(false);await h.button(`Delete Private ${A}`).onClick();await h.flush();assert.ok(h.text().includes(`Private ${A}`));assert.ok(h.toasts.some(t=>t.args[0]==='Could not delete account'));
 h.controllers.goal=()=>Promise.resolve(false);await changeGoal(h,333);await h.button('Save goal').onClick();await h.flush();assert.equal(h.button('Save goal').disabled,false);assert.ok(!h.toasts.some(t=>t.args[0]==='Portfolio goal saved'));
 delete h.controllers.goal;await h.button('Save goal').onClick();await h.flush();await h.toasts.at(-1).args[1].action.onClick();await h.flush();assert.equal(h.input('goal-amount').value,'100');assert.ok(h.toasts.some(t=>t.args[0]==='Goal reverted'));h.dispose();
});
test('Strict Mode effect cycle retires old mutation without unlocking a new one',async()=>{
 const h=harness();await h.flush();set(h,'new-account-name','first');await h.flush();const first=deferred();h.controllers.add=()=>first.promise;const old=h.button('Add account').onClick();
 h.strictCycle();await h.flush();assert.equal(h.button('Add account').disabled,false);const second=deferred();h.controllers.add=()=>second.promise;const next=h.button('Add account').onClick();await h.flush();assert.equal(h.button('Adding…').disabled,true);
 first.resolve(account(A,'old cycle secret'));await old;await h.flush();assert.ok(!h.text().includes('old cycle secret'));assert.equal(h.button('Adding…').disabled,true);
 second.resolve({...account(A,'new cycle'),id:'new-cycle'});await next;await h.flush();assert.ok(h.text().includes('new cycle'));assert.equal(h.retiredWrites(),0);h.dispose();
});
test('successful add/edit/delete use actual rows; an older Undo cannot replace a newer goal save',async()=>{
 const h=harness();await h.flush();set(h,'new-account-name','New account');set(h,'new-account-balance','777');await h.flush();await h.button('Add account').onClick();await h.flush();assert.ok(h.text().includes('New account'));
 h.button(`Edit Private ${A}`).onClick();await h.flush();set(h,`edit-name-account-${A}`,'Updated account');set(h,`edit-bal-account-${A}`,'888');await h.flush();await h.button('Save').onClick();await h.flush();assert.ok(h.text().includes('Updated account'));assert.ok(h.toasts.every(t=>!JSON.stringify(t.args).includes('Updated account')));
 await h.button('Delete Updated account').onClick();await h.flush();assert.ok(!h.text().includes('Updated account'));
 await changeGoal(h,333);await h.button('Save goal').onClick();await h.flush();const oldUndo=h.toasts.at(-1).args[1].action.onClick;
 await changeGoal(h,444);await h.button('Save goal').onClick();await h.flush();const count=h.calls.filter(c=>c.kind==='goal').length;await oldUndo();assert.equal(h.calls.filter(c=>c.kind==='goal').length,count);assert.equal(h.input('goal-amount').value,'444');h.dispose();
});
for(const replacement of ['account','logout','relogin','strict'])test(`owned generic toast is retired on ${replacement} while unrelated toast survives`,async()=>{
 const h=harness();await h.flush();h.unrelatedToast();set(h,'new-account-name','A private toast name');await h.flush();await h.button('Add account').onClick();await h.flush();
 await changeGoal(h,333);await h.button('Save goal').onClick();await h.flush();const undo=h.toasts.at(-1).args[1].action.onClick;
 assert.ok(h.toasts.some(t=>t.args[0]==='Account added'));assert.ok(h.toasts.every(t=>!JSON.stringify(t.args).includes('A private toast name')));const owned=[...h.visibleToasts.keys()].filter(id=>id!=='outside');const calls=h.calls.filter(c=>c.kind==='goal').length;
 if(replacement==='account')h.change(B,'B-1');else if(replacement==='logout')h.change(null);else if(replacement==='relogin')h.change(A,'A-2');else h.strictCycle();
 await h.flush();assert.deepEqual([...h.visibleToasts.keys()],['outside']);assert.ok(owned.every(id=>h.dismissed.includes(id)));assert.ok(!h.dismissed.includes('outside'));await undo();assert.equal(h.calls.filter(c=>c.kind==='goal').length,calls);h.dispose();
});
test('toast registry is bounded and auto-closed IDs are removed without global dismissal',async()=>{
 const h=harness();await h.flush();h.unrelatedToast();await changeGoal(h,333);await h.button('Save goal').onClick();await h.flush();const first=[...h.visibleToasts.keys()].find(id=>id!=='outside');h.autoClose(first);
 for(let i=0;i<12;i++){await changeGoal(h,400+i);await h.button('Save goal').onClick();await h.flush();}
 assert.equal(h.visibleToasts.size,9);assert.ok(h.visibleToasts.has('outside'));h.change(null);await h.flush();assert.deepEqual([...h.visibleToasts.keys()],['outside']);assert.ok(!h.dismissed.includes(first));assert.ok(!h.dismissed.includes('outside'));h.dispose();
});
