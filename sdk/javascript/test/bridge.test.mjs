import test from 'node:test';
import assert from 'node:assert/strict';
import {BridgeClient} from '../bridge.mjs';
import {validate} from '../client.mjs';

test('bridge credentials stay separate from session credentials', async () => {
  const calls = [];
  const client = new BridgeClient('http://127.0.0.1:1', {expectedGameId: 'game', bridgeToken: 'bridge-token',
    fetchImpl: async (url, options) => {
      calls.push({url, options});
      return new Response('{}', {status: 200});
    }});
  await client.call('/sessions/s1/events?cursor=9', undefined, 'session-token');
  assert.equal(calls[0].url.pathname, '/bridge/call');
  assert.equal(calls[0].options.headers.Authorization, 'Bearer bridge-token');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    operation: 'poll', arguments: {session_id: 's1', cursor: 9}, credential: 'session-token',
  });
  for (const path of ['/sessions/s1/actions/a1/claim', '//evil.test', '/sessions/s1/events?cursor=1&cursor=2',
    '/sessions/s1/events?cursor=10000000000', '/sessions/s1/leave?other=1']) {
    await assert.rejects(client.call(path, path.includes('leave') ? {reason: 'x'} : undefined));
  }
  assert.equal(calls.length, 1);
});

test('bridge wire schema excludes redirects, bad credentials and unknown operations', () => {
  for (const status of [201, 302, 399, 600]) {
    assert.throws(() => validate('bridge_reply', {id: 'r1', status, result: {}}));
  }
  assert.throws(() => validate('bridge_call', {operation: 'describe', arguments: {}, credential: '令牌'}));
  assert.throws(() => validate('bridge_call', {operation: 'execute', arguments: {}, credential: ''}));
  validate('bridge_reply', {id: 'r1', status: 403, result: {error: {code: 'denied', message: 'Denied'}}});
});
