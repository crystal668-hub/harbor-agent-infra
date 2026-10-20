import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(process.env.HAI_RETRY_SOURCE, 'utf8');
const error = (code, extra = {}) => Object.assign(new Error(code), {code, ...extra});
function fixture() {
  const logs = [], sleeps = [];
  const ctx = vm.createContext({process: {pid: 42}, setTimeout, clearTimeout,
    console: {warn: (line) => logs.push(JSON.parse(line.split('] ')[1]))}});
  vm.runInContext(source, ctx);
  vm.runInContext('Math.random = () => 0.5;', ctx);
  ctx.haiNetworkSleep = async (ms) => {sleeps.push(ms);};
  const init = {body: '{"message":"private"}', headers: {Authorization: 'secret'},
    method: 'POST', signal: new AbortController().signal};
  const run = (fetch) => ctx.haiFetchWithNetworkRetry(fetch, 'https://fixture.invalid?secret=1', init,
    {provider: 'anthropic', model: 'test', session_id: 'parent'});
  return {ctx, run, init, logs, sleeps};
}
test('first success has no retry overhead or log', async () => {
  const f = fixture(), response = {status: 200};
  let calls = 0;
  assert.equal(await f.run(async () => {calls++; return response;}), response);
  assert.equal(calls, 1);
  assert.deepEqual(f.sleeps, []);
  assert.deepEqual(f.logs, []);
});
for (const code of ['ENOTFOUND', 'EAI_AGAIN', 'ECONNREFUSED', 'UND_ERR_CONNECT_TIMEOUT']) {
  test(code + ' retries the same request and signal, preserving response identity', async () => {
    const f = fixture(), response = {status: 200};
    const seen = [];
    assert.equal(await f.run(async (url, init) => {
      seen.push(init);
      if (seen.length < 3) throw new TypeError('fetch failed', {cause: error(code)});
      return response;
    }), response);
    assert.equal(seen.length, 3);
    assert.ok(seen.every(init => init === f.init));
    assert.deepEqual(f.sleeps, [1000, 2000]);
    assert.deepEqual(f.logs.map(x => x.event), ['retry', 'retry', 'response']);
    assert.equal(new Set(f.logs.map(x => x.request_id)).size, 1);
    assert.ok(f.logs.every(x => x.session_id === 'parent'));
    assert.ok(!JSON.stringify(f.logs).includes('secret'));
    assert.ok(!JSON.stringify(f.logs).includes('private'));
  });
}
test('exhaustion throws last original error with cause after exactly four attempts', async () => {
  const f = fixture(), errors = Array.from({length: 4}, () =>
    new Error('fetch failed', {cause: error('ENOTFOUND')}));
  let calls = 0;
  await assert.rejects(f.run(async () => {throw errors[calls++];}), e => e === errors[3]);
  assert.equal(calls, 4);
  assert.deepEqual(f.sleeps, [1000, 2000, 4000]);
  assert.deepEqual(f.logs.map(x => x.event), ['retry', 'retry', 'retry', 'exhausted']);
});
test('jitter stays within approved envelope and individual cap', () => {
  const f = fixture();
  for (const [random, expected] of [[0, [800, 1600, 3200]], [1, [1200, 2400, 4800]]]) {
    vm.runInContext('Math.random = () => ' + random, f.ctx);
    assert.deepEqual([0, 1, 2].map(n => f.ctx.haiNetworkDelay(n)), expected);
    assert.equal(f.ctx.haiNetworkDelay(10), 5000);
  }
});
test('only explicit connect ETIMEDOUT qualifies; blocked/aborted/cyclic causes do not', () => {
  const f = fixture();
  assert.equal(f.ctx.haiNetworkErrorCode(error('ETIMEDOUT', {syscall: 'connect'})), 'ETIMEDOUT');
  assert.equal(f.ctx.haiNetworkErrorCode(error('ETIMEDOUT')), null);
  assert.equal(f.ctx.haiNetworkErrorCode(error('ETIMEDOUT', {syscall: 'read'})), null);
  for (const name of ['AbortError', 'SsrFBlockedError'])
    assert.equal(f.ctx.haiNetworkErrorCode(error('ENOTFOUND', {name})), null);
  const cyclic = error('ENOTFOUND'); cyclic.cause = cyclic;
  assert.equal(f.ctx.haiNetworkErrorCode(cyclic), null);
  let deep = error('EAI_AGAIN');
  for (let i = 0; i < 8; i++) deep = new Error('outer', {cause: deep});
  assert.equal(f.ctx.haiNetworkErrorCode(deep), null);
});
for (const e of [error('ECONNRESET'), error('EPIPE'), error('ETIMEDOUT'),
  error('CERT_HAS_EXPIRED'), new Error('fetch failed'), error('ENOTFOUND', {name: 'AbortError'})]) {
  test('non-retryable ' + e.name + '/' + e.message, async () => {
    const f = fixture(); let calls = 0;
    await assert.rejects(f.run(async () => {calls++; throw e;}), actual => actual === e);
    assert.equal(calls, 1); assert.deepEqual(f.sleeps, []);
  });
}
test('HTTP responses and later SSE failures never re-enter fetch', async () => {
  for (const status of [401, 403, 429, 500, 503, 200]) {
    const f = fixture(); let calls = 0;
    const response = {status, body: {async *[Symbol.asyncIterator]() {
      yield 'first event'; throw error('ECONNRESET');
    }}};
    const result = await f.run(async () => {calls++; return response;});
    assert.equal(result, response);
    await assert.rejects(async () => {for await (const _ of result.body) {}}, /ECONNRESET/);
    assert.equal(calls, 1); assert.deepEqual(f.sleeps, []);
  }
});
test('cancellation before send and between wait and resend preserves reason', async () => {
  for (const before of [true, false]) {
    const f = fixture(), controller = new AbortController(), reason = new Error('cancelled');
    f.init.signal = controller.signal;
    if (before) controller.abort(reason);
    f.ctx.haiNetworkSleep = async () => {controller.abort(reason);};
    let calls = 0;
    await assert.rejects(f.run(async () => {calls++; throw error('ENOTFOUND');}), e => e === reason);
    assert.equal(calls, before ? 0 : 1);
  }
});
test('real cancellable sleep clears timer and listener and prevents resend', async () => {
  const f = fixture(), controller = new AbortController(), reason = new Error('deadline');
  const timers = new Set();
  let removed = 0;
  f.ctx.setTimeout = (fn, ms) => {const timer = setTimeout(fn, ms); timers.add(timer); return timer;};
  f.ctx.clearTimeout = timer => {timers.delete(timer); clearTimeout(timer);};
  const original = controller.signal.removeEventListener.bind(controller.signal);
  controller.signal.removeEventListener = (...args) => {removed++; original(...args);};
  vm.runInContext(source.slice(source.indexOf('function haiNetworkSleep'),
    source.indexOf('async function haiFetchWithNetworkRetry')), f.ctx);
  f.init.signal = controller.signal;
  let calls = 0;
  const pending = f.run(async () => {calls++; throw error('ENOTFOUND');});
  await new Promise(setImmediate);
  assert.equal(timers.size, 1);
  controller.abort(reason);
  await assert.rejects(pending, e => e === reason);
  assert.equal(calls, 1); assert.equal(timers.size, 0); assert.equal(removed, 1);
});
