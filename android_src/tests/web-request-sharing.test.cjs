const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/src/main/assets/web_adapter.js'), 'utf8');

function browser({cached = false} = {}) {
  const calls = [], results = new Map(), writes = [];
  const context = {
    window: {
      PortalBridgeResult: (id, raw) => results.set(id, JSON.parse(raw)),
      chrome: {webview: {hostObjects: {sync: {portalDesktopCache: {
        Read: (scope, key) => cached ? JSON.stringify({v: 2, key, savedAt: Date.now(), data: {ok: true, data: ['cached']}}) : null,
        Write: (...args) => { writes.push(args); return true; }, MarkStale: () => true
      }}}}}
    },
    location: {protocol: 'https:', origin: 'https://portal.test'},
    document: {documentElement: {classList: {add() {}}}},
    URL, AbortController, setTimeout, clearTimeout,
    fetch: (target, options) => new Promise((resolve, reject) => calls.push({target, options, resolve, reject}))
  };
  vm.runInNewContext(source, context);
  const api = context.window.PortalNative;
  api.setCacheCompany('1'); api.setCacheIdentity('1', 'admin', '[]');
  const finish = (index, data = {ok: true, data: []}) => calls[index].resolve({ok: true, status: 200, json: async () => data});
  const request = (id, token = 'session-a', company = '1', method = 'GET', body = '') =>
    api.requestAsync(id, method, method === 'GET' ? '/api/v3/tasks' : '/api/v3/work', body, token, company);
  return {api, calls, results, writes, finish, request};
}

test('concurrent identical authenticated reads share one request and deliver both results', async () => {
  const b = browser(); const first = b.request('one'), second = b.request('two');
  const count = b.calls.length;
  b.calls.forEach((_, i) => b.finish(i)); await Promise.all([first, second]);
  assert.equal(count, 1);
  assert.deepEqual(b.results.get('one'), b.results.get('two'));
  const later = b.request('later'); assert.equal(b.calls.length, count + 1);
  b.finish(count); await later;
});

test('request sharing never crosses session or company boundaries', async () => {
  const b = browser(); const requests = [b.request('one'), b.request('two', 'session-b'), b.request('three', 'session-a', '2')];
  assert.equal(b.calls.length, 3); b.calls.forEach((_, i) => b.finish(i)); await Promise.all(requests);
});

test('a successful mutation separates subsequent reads and prevents stale cache writes', async () => {
  const b = browser(); const oldRead = b.request('old');
  const write = b.request('write', 'session-a', '1', 'POST', '{"request_id":"test"}');
  b.finish(1); await write;
  const newRead = b.request('new'); assert.equal(b.calls.length, 3);
  b.finish(2, {ok: true, data: ['new']}); await newRead;
  b.finish(0, {ok: true, data: ['old']}); await oldRead;
  assert.equal(b.writes.length, 1);
  assert.deepEqual(JSON.parse(b.writes[0][2]).data.data, ['new']);
});

test('cached reads return immediately while sharing their background refresh', async () => {
  const b = browser({cached: true}); await Promise.all([b.request('one'), b.request('two')]);
  assert.equal(b.results.get('one').cached, true);
  assert.equal(b.results.get('two').cached, true);
  const count = b.calls.length; b.calls.forEach((_, i) => b.finish(i));
  await new Promise(resolve => setImmediate(resolve)); assert.equal(count, 1);
});

test('failed reads are removed from the shared request map so retry reaches the server', async () => {
  const b = browser(); const first = b.request('one');
  b.calls[0].resolve({ok: false, status: 503, json: async () => ({ok: false})}); await first;
  const retry = b.request('retry'); assert.equal(b.calls.length, 2); b.finish(1); await retry;
  assert.equal(b.results.get('retry').ok, true);
});

test('changing company or user invalidates in-flight cache writes', async () => {
  const b = browser(); const oldRead = b.request('old');
  b.api.setCacheCompany('2'); b.api.setCacheIdentity('2', 'packer', '[]');
  b.finish(0); await oldRead; assert.equal(b.writes.length, 0);
});

test('concurrent mutations always remain separate requests', async () => {
  const b = browser(); const requests = [b.request('one', 'session-a', '1', 'POST', '{}'), b.request('two', 'session-a', '1', 'POST', '{}')];
  assert.equal(b.calls.length, 2); b.calls.forEach((_, i) => b.finish(i)); await Promise.all(requests);
});

test('rejected shared fetch reports network errors to both callers and allows retry', async () => {
  const b = browser(); const first = b.request('one'), second = b.request('two');
  assert.equal(b.calls.length, 1); b.calls[0].reject(new Error('synthetic transport failure'));
  await Promise.all([first, second]);
  assert.equal(b.results.get('one').network, true); assert.equal(b.results.get('two').network, true);
  const retry = b.request('retry'); assert.equal(b.calls.length, 2); b.finish(1); await retry;
});

test('company-only and identity-only changes suppress old cache writes', async () => {
  for (const change of [b => b.api.setCacheCompany('2'), b => b.api.setCacheIdentity('2', 'admin', '[]')]) {
    const b = browser(); const old = b.request('old'); change(b); b.finish(0); await old;
    assert.equal(b.writes.length, 0);
  }
});

test('cached background refresh cannot overwrite data after a mutation', async () => {
  const b = browser({cached: true}); await b.request('cached');
  const mutation = b.request('write', 'session-a', '1', 'POST', '{}'); b.finish(1); await mutation;
  b.finish(0); await new Promise(resolve => setImmediate(resolve)); assert.equal(b.writes.length, 0);
});
