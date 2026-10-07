// 配对数据通过 stdin 输入，不把邀请或会话令牌暴露在进程参数和输出中。
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const moduleUrl = process.env.G2A_JS_MODULE
  ? pathToFileURL(process.env.G2A_JS_MODULE)
  : new URL('../sdk/javascript/client.mjs', import.meta.url);
const {Client, ProtocolError} = await import(moduleUrl.href);
let raw = '';
for await (const chunk of process.stdin) {
  raw += chunk;
  if (raw.length > 65536) throw new Error('Configuration too large');
}
const config = JSON.parse(raw);
const client = new Client(config.endpoint, {expectedGameId: config.game_id});
await client.join(config.invitation, config.request);
assert.equal(client.desktopVisible, false);
const deadline = Date.now() + 10000;
let receivedContext = false;
while (Date.now() < deadline && !receivedContext) {
  const page = await client.poll();
  receivedContext = page.events.some(e => e.message.type === 'game.context');
  if (!receivedContext) await new Promise(resolve => setTimeout(resolve, 20));
}
assert.ok(receivedContext, 'Game context did not arrive');
await client.send('chat.message', {
  text: config.companion_text ?? '你撑一下，我去拿钥匙。', channel: 'team', recipients: ['alice', 'bob'],
  provenance: {kind: 'shared_experience', source_id: 'hall-1', player_id: 'alice'},
}, {messageId: 'js-chat'});
const request = {action: 'find-key', arguments: {room: 'hall'}, capability_revision: client.session.capability_revision};
const receipt = await client.send('action.request', request, {messageId: 'js-action'});
assert.deepEqual(await client.send('action.request', request, {messageId: 'js-action'}), receipt);
await assert.rejects(client.send('action.request', {...request, arguments: {room: 'other'}}, {messageId: 'js-action'}), e => e instanceof ProtocolError && e.code === 'id_conflict');
await assert.rejects(client.send('action.request', {...request, action: 'reveal-boss'}, {messageId: 'js-unauthorized'}), e => e.code === 'permission_denied');
let result;
while (Date.now() < deadline && !result) {
  const page = await client.poll();
  result = page.events.find(e => e.message.type === 'action.result')?.message.data;
  if (!result) await new Promise(resolve => setTimeout(resolve, 20));
}
assert.equal(result?.status, config.expected_action_status ?? 'succeeded');
if (result.status === 'succeeded') assert.equal(result.details.item, 'gold-key');
else assert.equal(result.details.reason, 'world_condition');
await client.leave();
assert.equal(client.desktopVisible, true);
process.stdout.write(JSON.stringify({implementation: 'javascript', context_received: receivedContext,
  proactive_chat: true, action_result: result, duplicate_receipt: true, conflicting_id_rejected: true,
  unauthorized_action_rejected: true, desktop_restored: client.desktopVisible}) + '\n');
