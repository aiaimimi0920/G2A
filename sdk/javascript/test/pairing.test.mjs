import test from 'node:test';
import assert from 'node:assert/strict';
import {PairingClient} from '../pairing.mjs';
import {validate} from '../client.mjs';

test('pairing decisions require explicit typed consent and exact snapshot', () => {
  validate('pairing_decision', {scope: 'a'.repeat(64), allow: false, remember: false});
  for (const bad of [
    {scope: 'a'.repeat(64), allow: 'true', remember: false},
    {scope: 'a'.repeat(64), allow: true, remember: false, admin: true},
    {scope: 'missing', allow: true, remember: false},
  ]) assert.throws(() => validate('pairing_decision', bad));
});

test('pairing ticket must not redirect the invitation to another origin', async () => {
  const calls = [];
  const client = new PairingClient('http://127.0.0.1:1', {token: 'enrolled', expectedGameId: 'game',
    fetchImpl: async (url, options) => {
      calls.push({url, options});
      return new Response(JSON.stringify({endpoint: 'https://other.example', invitation: 'a'.repeat(43), request: {
        protocol: '0.1.0-dev', agent_id: 'fox', player_id: 'alice',
        default_avatar: {id: 'fox', format: 'text', label: 'Fox'}, desktop_visible: true,
        user_policy: {}, allowed_actions: [],
      }}));
    }});
  await assert.rejects(client.redeem('abc', {desktopVisible: true}), {code: 'identity_mismatch'});
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.headers.Authorization, 'Bearer enrolled');
});
