import assert from 'node:assert/strict';
import test from 'node:test';
import childProcess from 'node:child_process';
import { EventEmitter } from 'node:events';
import { syncBuiltinESMExports } from 'node:module';
import { inspect } from 'node:util';
import { ownedGroupIsQuiescent, fixtureFailureMetadata, runFixtureChild } from '../browser-fixture.mjs';

const handle = { pid: 11 };
const fields = ['queryKind', 'phase', 'cleanupPhase', 'status', 'signal', 'errno',
  'stdoutChars', 'stdoutBytes', 'stderrPresent', 'elapsedMs'].sort();
function refused(result, platform = 'darwin') {
  let failure, calls = 0;
  assert.throws(() => ownedGroupIsQuiescent(handle, (command, args, options) => {
    calls++; assert.equal(command, '/bin/ps');
    assert.deepEqual(args, ['-g', '11', '-o', 'pid=,pgid=,stat=']);
    assert.deepEqual(options, { env: { COMMAND_MODE: 'unix2003', LC_ALL: 'C' },
      encoding: 'utf8', timeout: 1000, maxBuffer: 262144 });
    return result;
  }, platform), error => {
    failure = error; return error.message === 'Cannot inspect exact owned process group';
  });
  assert.equal(calls, 1, 'No diagnostic retry or altered command');
  const data = fixtureFailureMetadata(failure);
  assert.deepEqual(Object.keys(data.inspection).sort(), fields);
  assert.ok(data.inspection.elapsedMs === null || (data.inspection.elapsedMs >= 0 && data.inspection.elapsedMs <= 10000));
  assert.doesNotMatch(JSON.stringify(data), /private|credential|raw body/i);
  return { failure, data };
}

test('owned ps refusal records known errno and exact query without raw output', () => {
  const result = { error: Object.assign(new Error('private credential error'), { code: 'EPERM' }),
    status: null, signal: null, stdout: '', stderr: '' };
  const { data } = refused(result);
  assert.equal(data.errorCode, 'EPERM');
  assert.deepEqual({ ...data.inspection, elapsedMs: null }, { queryKind: 'darwin-group-ps', phase: 'state',
    cleanupPhase: 'untracked', status: null, signal: null, errno: 'EPERM',
    stdoutChars: 0, stdoutBytes: 0, stderrPresent: false, elapsedMs: null });
  assert.equal(result.error.message, 'private credential error', 'Original result is neither rewritten nor serialized');
});
test('status1 with stderr remains refusal while literal empty status1 remains quiescent', () => {
  const { data } = refused({ status: 1, signal: null, stdout: '', stderr: 'private kernel detail' });
  assert.equal(data.inspection.status, 1); assert.equal(data.inspection.stderrPresent, true);
  assert.equal(data.inspection.errno, null);
  assert.equal(ownedGroupIsQuiescent(handle, () => ({ status: 1, stdout: '', stderr: '' }), 'darwin'), true);
});
test('command timeout retains closed status/signal/errno and preserves1000ms limit', () => {
  const { data } = refused({ error: Object.assign(new Error('private raw body'), { code: 'ETIMEDOUT' }),
    status: null, signal: 'SIGTERM', stdout: '', stderr: '' });
  assert.equal(data.inspection.errno, 'ETIMEDOUT'); assert.equal(data.inspection.signal, 'SIGTERM');
});
test('unknown objects and serialization hooks cannot escape closed scalar diagnostics', () => {
  let serialization = 0;
  const raw = { toJSON() { serialization++; throw new Error('private credential'); } };
  const { data } = refused({ error: { code: raw }, status: NaN, signal: raw,
    stdout: 'private credential 🦉', stderr: 'private raw body' });
  assert.equal(data.inspection.status, null); assert.equal(data.inspection.errno, 'UNKNOWN');
  assert.equal(data.inspection.signal, 'UNKNOWN'); assert.equal(data.inspection.stderrPresent, true);
  assert.equal(serialization, 0);
});
test('result error-code and unused output getters are never invoked by diagnostics', () => {
  let reads = 0;
  const error = Object.defineProperty({}, 'code', { get() { reads++; throw new Error('private credential'); } });
  const result = { error, status: null, stderr: '' };
  Object.defineProperty(result, 'stdout', { get() { reads++; throw new Error('private body'); } });
  const { data } = refused(result);
  assert.equal(reads, 0); assert.equal(data.inspection.errno, 'UNKNOWN');
  assert.equal(data.inspection.stdoutChars, null); assert.equal(data.inspection.stdoutBytes, null);
});
test('overlong or multibyte output reports bounded lengths while still refusing', () => {
  const tooLong = refused({ status: 0, stdout: 'x'.repeat(262145), stderr: '' }).data;
  assert.equal(tooLong.inspection.stdoutChars, 'OVER_LIMIT'); assert.equal(tooLong.inspection.stdoutBytes, 'OVER_LIMIT');
  const multibyte = refused({ status: 2, stdout: '🦉'.repeat(65537), stderr: '' }).data;
  assert.equal(multibyte.inspection.stdoutChars, 131074); assert.equal(multibyte.inspection.stdoutBytes, 'OVER_LIMIT');
});
test('only helper-created refusal errors can publish inspection metadata and views are detached', () => {
  const { failure, data } = refused({ status: 2, stdout: '', stderr: '' });
  data.inspection.errno = 'private replacement'; data.inspection.queryKind = 'private command';
  Object.defineProperty(failure, 'inspection', { get() { throw new Error('private credential'); } });
  const again = fixtureFailureMetadata(failure);
  assert.equal(again.inspection.errno, null); assert.equal(again.inspection.queryKind, 'darwin-group-ps');
  const forged = Object.assign(new Error('private credential'), { inspection: again.inspection });
  assert.equal(Object.hasOwn(fixtureFailureMetadata(forged), 'inspection'), false);
});
test('Node refusal formatting retains only a frozen detached safe cause and fabricated causes gain no trust', () => {
  const { failure, data } = refused({ error: Object.assign(new Error('private credential'), { code: 'ETIMEDOUT' }),
    status: null, signal: 'SIGTERM', stdout: 'private raw body', stderr: 'private diagnostic' });
  assert.equal(Object.isFrozen(failure.cause), true); assert.equal(Object.isFrozen(failure.cause.inspection), true);
  assert.notEqual(failure.cause.inspection, data.inspection);
  assert.deepEqual(failure.cause.inspection, data.inspection);
  assert.match(inspect(failure), /darwin-group-ps/); assert.match(inspect(failure), /ETIMEDOUT/);
  assert.doesNotMatch(inspect(failure), /private credential|private raw body|private diagnostic/);
  const forged = new Error('private fabricated', { cause: failure.cause });
  assert.equal(Object.hasOwn(fixtureFailureMetadata(forged), 'inspection'), false);
  failure.cause = { code: 'private replacement', get inspection() { throw new Error('private getter'); } };
  assert.equal(fixtureFailureMetadata(failure).inspection.errno, 'ETIMEDOUT');
  assert.doesNotMatch(JSON.stringify(fixtureFailureMetadata(failure)), /private/);
});
test('malicious error/prepared/group getters and proxies remain unknown without getter invocation', () => {
  let reads = 0;
  const getter = () => { reads++; throw new Error('private credential'); };
  const error = {}, prepared = {}, groups = [11];
  for (const key of ['name', 'code', 'cause', 'inspection', 'toJSON']) Object.defineProperty(error, key, { get: getter });
  Object.defineProperty(prepared, 'directory', { get: getter }); Object.defineProperty(prepared, 'owner', { get: getter });
  Object.defineProperty(groups, '0', { get: getter });
  const data = fixtureFailureMetadata(error, prepared, groups);
  assert.equal(reads, 0); assert.equal(data.errorName, 'UnknownError'); assert.equal(data.errorCode, 'UNKNOWN');
  assert.deepEqual(data.ownedProcessGroups, []); assert.equal(data.markerDirectory, null);
  assert.equal(Object.hasOwn(data, 'inspection'), false);
  const proxy = new Proxy({}, { get() { reads++; throw new Error('private proxy'); },
    getOwnPropertyDescriptor() { throw new Error('private proxy'); }, getPrototypeOf() { throw new Error('private proxy'); } });
  assert.doesNotThrow(() => fixtureFailureMetadata(proxy, proxy, proxy));
  const { proxy: revoked, revoke } = Proxy.revocable([], {}); revoke();
  assert.doesNotThrow(() => fixtureFailureMetadata(revoked, revoked, revoked));
  assert.equal(reads, 0);
});
test('Linux membership-before and membership-after refusals retain their exact stages', () => {
  for (const after of [false, true]) {
    const calls = [], replies = after ? [
      { status: 0, stdout: '12\n', stderr: '' }, { status: 0, stdout: '12 11 Z\n', stderr: '' },
      { status: 2, stdout: '', stderr: 'private membership' },
    ] : [{ status: 2, stdout: '', stderr: 'private membership' }];
    let failure;
    assert.throws(() => ownedGroupIsQuiescent(handle, (command, args, options) => {
      calls.push({ command, args }); assert.equal(options.timeout, 1000); return replies.shift();
    }, 'linux'), error => { failure = error; return /exact owned process group/.test(error.message); });
    const data = fixtureFailureMetadata(failure);
    assert.equal(data.inspection.queryKind, 'linux-group-pgrep');
    assert.equal(data.inspection.phase, after ? 'membership-after' : 'membership-before');
    assert.equal(calls.length, after ? 3 : 1); assert.doesNotMatch(JSON.stringify(data), /private/);
  }
});
test('Linux selected-member ps errors are distinguished from pgrep without changing membership guards', () => {
  const replies = [{ status: 0, stdout: '12\n', stderr: '' },
    { status: null, signal: 'SIGKILL', error: Object.assign(new Error('private'), { code: 'ENOBUFS' }), stdout: '', stderr: '' }];
  let failure;
  assert.throws(() => ownedGroupIsQuiescent(handle, () => replies.shift(), 'linux'), error => {
    failure = error; return /exact owned process group/.test(error.message);
  });
  const data = fixtureFailureMetadata(failure);
  assert.equal(data.inspection.queryKind, 'linux-member-ps'); assert.equal(data.inspection.phase, 'state');
  assert.equal(data.inspection.errno, 'ENOBUFS'); assert.equal(data.inspection.signal, 'SIGKILL'); assert.equal(replies.length, 0);
});
test('thrown inspection commands are sanitized refusals with no retry', () => {
  let calls = 0, failure;
  assert.throws(() => ownedGroupIsQuiescent(handle, () => {
    calls++; throw Object.assign(new Error('private command error'), { code: 'EPERM' });
  }, 'darwin'), error => { failure = error; return /exact owned process group/.test(error.message); });
  assert.equal(calls, 1); assert.equal(fixtureFailureMetadata(failure).inspection.errno, 'EPERM');
  assert.doesNotMatch(JSON.stringify(fixtureFailureMetadata(failure)), /private/);
});

for (const stage of ['initial', 'term', 'kill']) test(`registered child refusal reports genuine controller phase ${stage} with final failure preserved`, async () => {
  // Entirely controlled ChildProcess: no operating-system process or signal.
  const child = Object.assign(new EventEmitter(), { pid: 2147483000 });
  const spawn = childProcess.spawn, spawnSync = childProcess.spawnSync, kill = process.kill;
  const signals = []; let sentTerm = false, failure;
  try {
    childProcess.spawn = (command, args, options) => {
      assert.equal(command, 'synthetic-child-only'); assert.deepEqual(args, []);
      assert.equal(options.detached, true); assert.equal(options.shell, false); return child;
    };
    process.kill = (pid, signal) => {
      assert.equal(pid, -child.pid); signals.push(signal);
      if (signal === 'SIGTERM') {
        sentTerm = true;
        if (stage === 'term') throw Object.assign(new Error('private signal refusal'), { code: 'EPERM' });
      }
      if (signal === 0 && (stage === 'initial' || sentTerm)) throw Object.assign(new Error('private signal probe'), { code: 'EPERM' });
      return true;
    };
    childProcess.spawnSync = (command, args, options) => {
      assert.equal(command, '/bin/ps'); assert.deepEqual(args, ['-g', String(child.pid), '-o', 'pid=,pgid=,stat=']);
      assert.equal(options.timeout, 1000); return { status: 2, stdout: '', stderr: 'private unavailable metadata' };
    };
    syncBuiltinESMExports();
    await assert.rejects(runFixtureChild('synthetic-child-only', [], { env: {}, stdio: 'ignore' }, 0), error => {
      failure = error; return /exact owned process group/.test(error.message);
    });
    assert.equal(fixtureFailureMetadata(failure).inspection.cleanupPhase, stage);
    assert.deepEqual(signals, stage === 'initial' ? [0] : stage === 'term' ? [0, 'SIGTERM'] : [0, 'SIGTERM', 0, 'SIGKILL', 0]);
    assert.doesNotMatch(JSON.stringify(fixtureFailureMetadata(failure)), /private/);
  } finally {
    process.kill = kill; childProcess.spawn = spawn; childProcess.spawnSync = spawnSync; syncBuiltinESMExports();
  }
});
