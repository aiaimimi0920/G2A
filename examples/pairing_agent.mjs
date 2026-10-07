import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';

const moduleUrl = process.env.G2A_JS_MODULE
  ? new URL('./pairing.mjs', pathToFileURL(process.env.G2A_JS_MODULE))
  : new URL('../sdk/javascript/pairing.mjs', import.meta.url);
const {PairingClient} = await import(moduleUrl);
let raw = '';
for await (const chunk of process.stdin) {
  raw += chunk;
  if (raw.length > 65536) throw new Error('Configuration too large');
}
const config = JSON.parse(raw);
const pairing = new PairingClient(config.endpoint, {token: config.agent_token, expectedGameId: 'key-quest'});
const games = await pairing.discover();
assert.equal(games[0].game_id, 'key-quest');
const id = config.entry === 'desktop' ? (await pairing.request(config.request)).id : config.request_id;
const deadline = Date.now() + 55000;
let offer;
while (Date.now() < deadline) {
  offer = await pairing.offer(id);
  if (offer.state === 'denied') {
    process.stdout.write(JSON.stringify({denied: true, joined: false}) + '\n');
    process.exit(0);
  }
  if (offer.state === 'authorized') break;
  await new Promise(resolve => setTimeout(resolve, 30));
}
assert.equal(offer.state, 'authorized', 'No user decision within request lifetime');
const client = await pairing.redeem(id, {desktopVisible: config.request.desktop_visible});
let sent = false, result;
try {
  while (Date.now() < deadline && !result) {
    const page = await client.poll();
    if (!sent && page.events.some(e => e.message.type === 'game.context')) {
      await client.send('chat.message', {text: '我去拿钥匙。', channel: 'private', recipients: ['alice']});
      await client.send('action.request', {action: 'find-key', arguments: {room: 'hall'},
        capability_revision: client.session.capability_revision});
      sent = true;
    }
    result = page.events.find(e => e.message.type === 'action.result')?.message.data;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  assert.equal(result?.status, 'succeeded');
} finally {
  await client.leave();
}
process.stdout.write(JSON.stringify({joined: true, result, desktop_restored: client.desktopVisible,
  consent_required: true}) + '\n');
