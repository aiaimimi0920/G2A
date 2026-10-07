import test from 'node:test';
import assert from 'node:assert/strict';
import {Client, validate} from '../client.mjs';

const session = () => ({id: 's1', state: 'active', game_id: 'game', agent_id: 'fox', player_id: 'alice',
  avatar: {id: 'fox', format: 'text', label: '狐狸'}, policy: {}, desktop_visible: false,
  restore_desktop_visible: true, capability_revision: 1, allowed_actions: [], sequence: 0});
const descriptor = () => ({protocol: '0.1.0-dev', game_id: 'game', name: 'Game', bindings: ['http-poll'],
  avatar_formats: ['text'], presentation: 'hide_desktop', policy: {}, actions: []});
const request = () => ({protocol: '0.1.0-dev', agent_id: 'fox', player_id: 'alice',
  default_avatar: {id: 'fox', format: 'text', label: '狐狸'}, desktop_visible: true,
  user_policy: {}, allowed_actions: []});
function fakeClient() {
  let now = 0;
  const queue = [];
  const calls = [];
  const client = new Client('http://127.0.0.1:4000', {expectedGameId: 'game', clock: () => now,
    fetchImpl: async (url, options) => {
      calls.push({url: url.href, options});
      const next = queue.shift();
      if (next instanceof Error) throw next;
      return next instanceof Response ? next : new Response(JSON.stringify(next), {headers: {'Content-Type': 'application/json'}});
    }});
  return {client, queue, calls, setTime: t => {now = t;}};
}
async function joined(f) {
  f.queue.push(descriptor(), {session: session(), session_token: 'a'.repeat(43), lease_seconds: 30});
  await f.client.join('invitation', request());
}

test('schema rejects invalid fields and unsupported versions', () => {
  assert.throws(() => validate('join', {...request(), permission_override: true}), {code: 'invalid_message'});
  assert.throws(() => validate('join', {...request(), protocol: '9.0'}), {code: 'invalid_message'});
  assert.throws(() => validate('message', {id: 'x', type: 'arbitrary', sender: 'fox', data: {}}), {code: 'invalid_message'});
});
test('plaintext, credential and alternate-loopback origins are rejected', () => {
  for (const url of ['http://example.com', 'http://localhost:1', 'http://127.1', 'http://2130706433', 'https://u:p@example.com', 'https://example.com/path']) {
    assert.throws(() => new Client(url, {expectedGameId: 'game'}));
  }
});
test('SDK does not follow redirects or leak token across origin', async () => {
  const f = fakeClient(); f.queue.push({});
  await f.client.call('/endpoint', {}, 'secret');
  assert.equal(f.calls[0].options.redirect, 'error');
  await assert.rejects(f.client.call('//other.example/path', {}, 'secret'));
  assert.equal(f.calls.length, 1);
});
test('wrong descriptor does not submit invitation', async () => {
  const f = fakeClient(); f.queue.push({...descriptor(), game_id: 'other'});
  await assert.rejects(f.client.join('secret', request()), {code: 'wrong_game'});
  assert.equal(f.calls.length, 1);
  assert.equal(f.client.desktopVisible, null);
});
test('join checks participant identities', async () => {
  const f = fakeClient(); f.queue.push(descriptor(), {session: {...session(), player_id: 'eve'}, session_token: 'a'.repeat(43), lease_seconds: 30});
  await assert.rejects(f.client.join('i', request()), {code: 'identity_mismatch'});
  assert.equal(f.client.session, null);
});
test('poll checks identity and cursor ordering without mutating state', async () => {
  const f = fakeClient(); await joined(f);
  f.queue.push({session: {...session(), id: 'other'}, events: [], cursor: 0});
  await assert.rejects(f.client.poll(), {code: 'identity_mismatch'});
  f.queue.push({session: session(), events: [], cursor: 1});
  await assert.rejects(f.client.poll(), {code: 'invalid_cursor'});
  assert.equal(f.client.cursor, 0);
});
test('lease fallback and successful poll reapply correct presentation', async () => {
  const f = fakeClient(); await joined(f);
  f.setTime(31); assert.equal(f.client.checkLease(), true); assert.equal(f.client.desktopVisible, true);
  f.queue.push({session: session(), events: [], cursor: 0});
  await f.client.poll(); assert.equal(f.client.desktopVisible, false);
  f.setTime(32); assert.equal(f.client.checkLease(), false);
});
test('old submit receipt does not prolong client presentation lease', async () => {
  const f = fakeClient(); await joined(f);
  f.setTime(20); f.queue.push({accepted: true, sequence: 1});
  await f.client.send('chat.message', {text: 'hi', channel: 'private', recipients: ['alice']}, {messageId: 'same'});
  f.setTime(31); assert.equal(f.client.checkLease(), true);
});
test('leave restores local snapshot despite transport failure', async () => {
  const f = fakeClient(); await joined(f); f.queue.push(new Error('offline'));
  await assert.rejects(f.client.leave(), /offline/);
  assert.equal(f.client.desktopVisible, true);
});
test('oversized and malformed responses fail closed', async () => {
  const f = fakeClient(); f.queue.push(new Response('x'.repeat(262145)));
  await assert.rejects(f.client.call('/x'), {code: 'response_too_large'});
  f.queue.push(new Response('not json'));
  await assert.rejects(f.client.call('/x'), {code: 'transport_error'});
});
test('known protocol errors preserve machine-readable error code', async () => {
  const f = fakeClient(); f.queue.push(new Response(JSON.stringify({error: {code: 'permission_denied', message: 'Denied'}}), {status: 403}));
  await assert.rejects(f.client.call('/x'), e => e.code === 'permission_denied' && e.status === 403);
});
