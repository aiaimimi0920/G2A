// 独立手写候选 profile 客户端：不导入 Python schema 或信任其公开绑定断言。
import assert from 'node:assert/strict';
import { canonical, decode } from './codec_peer.mjs';

export function validateBinding(binding, expected) {
  assert.deepEqual(Object.keys(binding).sort(), ['authority', 'epoch', 'instance_id', 'kind',
    'mailbox_id', 'principal', 'role', 'version']);
  assert.equal(binding.version, 'g2a-epoch-binding-1');
  for (const key of ['authority', 'instance_id', 'principal', 'role', 'kind']) {
    assert.equal(typeof binding[key], 'string');
    assert.ok([...binding[key]].length > 0 && [...binding[key]].length <= 128);
  }
  assert.ok(Number.isSafeInteger(binding.epoch) && binding.epoch >= 0);
  assert.ok(['pairing', 'mailbox'].includes(binding.kind));
  assert.ok(['controller', 'agent', 'game', 'receipt_reader'].includes(binding.role));
  if (binding.kind === 'pairing') {
    assert.equal(binding.mailbox_id, null);
    assert.equal(binding.role, 'controller');
  } else assert.ok(Number.isSafeInteger(binding.mailbox_id) && binding.mailbox_id >= 1 && binding.mailbox_id <= 8);
  for (const [key, value] of Object.entries(expected)) assert.deepEqual(binding[key], value);
  return binding;
}

export async function runEpochBindingCases(command) {
  let wireCalls = 0, fixtureCalls = 0;
  const invoke = async (action, fields = {}) => {
    fixtureCalls++;
    return command({ kind: 'epoch_binding', action, ...fields });
  };
  const description = await invoke('describe');
  const context = { authority: description.authority, instance_id: description.instance_id };
  const delivered = (value, expected) => {
    const raw = Buffer.from(value.binding, 'base64');
    const binding = JSON.parse(JSON.stringify(decode(raw)));
    assert.ok(raw.equals(canonical(binding)));
    validateBinding(binding, { ...context, ...expected });
    assert.equal(typeof value.credential, 'string');
    assert.ok(!raw.includes(value.credential));
    return { token: value.credential, binding };
  };
  const wire = async (operation, evidence, request_id, binding = evidence.binding, now = 0) => {
    wireCalls++;
    const output = await invoke('wire', { operation, credential: evidence.token, request_id, now,
      raw: canonical(binding).toString('base64') });
    const raw = Buffer.from(output.reply, 'base64');
    const reply = JSON.parse(JSON.stringify(decode(raw)));
    assert.ok(raw.equals(canonical(reply)));
    assert.equal(reply.request_id, request_id);
    assert.equal(Object.keys(reply).length, 2);
    assert.notEqual(Object.hasOwn(reply, 'result'), Object.hasOwn(reply, 'error'));
    return reply;
  };
  const pairing = delivered(await invoke('pairing', { principal: 'player' }),
    { epoch: 0, kind: 'pairing', principal: 'player', role: 'controller' });
  const identity = (await wire('register', pairing, 'register')).result.identity;
  assert.deepEqual(identity, [0, 1]);
  const controller = delivered(await invoke('credential', { identity, principal: 'player', role: 'controller' }),
    { epoch: 0, kind: 'mailbox', mailbox_id: 1, principal: 'player', role: 'controller' });
  const agent = delivered(await invoke('credential', { identity, principal: 'agent', role: 'agent' }),
    { epoch: 0, kind: 'mailbox', mailbox_id: 1, principal: 'agent', role: 'agent' });
  const game = delivered(await invoke('credential', { identity, principal: 'game', role: 'game' }),
    { epoch: 0, kind: 'mailbox', mailbox_id: 1, principal: 'game', role: 'game' });

  // 双向拒绝：本地独立校验拒绝坏公开结构，Python 端另外验证可信 token 完整绑定。
  const missing = { ...agent.binding }; delete missing.epoch;
  for (const bad of [missing, { ...agent.binding, epoch: false }, { ...agent.binding, mailbox_id: true },
    { ...agent.binding, version: 'old' }, { ...agent.binding, extra: 'ignored?' }]) {
    assert.throws(() => validateBinding(bad, context));
    const reply = await wire('claim', agent, 'bad-shape', bad);
    assert.ok(['invalid_arguments', 'unsupported_version'].includes(reply.error.code));
  }
  for (const change of [{ authority: 'other' }, { instance_id: 'other' }, { mailbox_id: 2 },
    { principal: 'player' }, { role: 'controller' }]) {
    assert.equal((await wire('claim', agent, 'bad-evidence', { ...agent.binding, ...change })).error.code, 'permission_denied');
  }
  assert.equal((await wire('close', agent, 'agent-close')).error.code, 'permission_denied');
  assert.equal((await wire('claim', game, 'game-claim')).error.code, 'permission_denied');
  assert.equal((await wire('register', pairing, 'pairing-replay')).error.code, 'id_conflict');

  const first = (await wire('claim', agent, 'original')).result.claim;
  assert.equal((await invoke('begin', { claim: first })).effects, 0);
  const reader = delivered(await invoke('receipt_reader', { claim: first, principal: 'agent', expires_at: 70000 }),
    { epoch: 0, kind: 'mailbox', mailbox_id: 1, principal: 'agent', role: 'receipt_reader' });
  assert.equal((await invoke('restart')).restarted, true);
  assert.equal((await wire('receipt', reader, 'original')).result.phase, 'accepted');
  const duplicate = (await wire('claim', agent, 'original')).result.claim;
  assert.equal((await invoke('begin', { claim: duplicate })).fixture_rejected, 'already_seen');
  assert.equal((await invoke('finish', { claim: first })).effects, 1);
  assert.equal((await wire('receipt', reader, 'original')).result.phase, 'completed');
  assert.equal((await wire('close', controller, 'close')).result.closed, true);
  assert.equal((await invoke('seal', { epoch: 0 })).epoch, 1);
  assert.equal((await invoke('advance_game', { epoch: 1, fault: 'after_commit' })).fixture_fault, 'after_commit');
  assert.equal((await invoke('restart')).restarted, true);
  assert.equal((await invoke('pairing', { principal: 'player' })).fixture_rejected, 'request_gone');
  assert.equal((await invoke('advance_game', { epoch: 1 })).epoch, 1);
  assert.equal((await invoke('advance_relay', { epoch: 1, fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.equal((await invoke('advance_relay', { epoch: 1 })).epoch, 1);
  assert.equal((await wire('claim', agent, 'old-epoch')).error.code, 'generation_conflict');
  assert.equal((await wire('claim', agent, 'relabel', { ...agent.binding, epoch: 1 })).error.code, 'unauthenticated');
  assert.equal((await invoke('begin', { claim: first })).fixture_rejected, 'request_gone');
  assert.equal((await wire('receipt', reader, 'original')).result.phase, 'completed');

  const newPairing = delivered(await invoke('pairing', { principal: 'player' }),
    { epoch: 1, kind: 'pairing', principal: 'player', role: 'controller' });
  const nextIdentity = (await wire('register', newPairing, 'register-new')).result.identity;
  assert.deepEqual(nextIdentity, [1, 1]);
  const nextAgent = delivered(await invoke('credential', { identity: nextIdentity, principal: 'agent', role: 'agent' }),
    { epoch: 1, kind: 'mailbox', mailbox_id: 1, principal: 'agent', role: 'agent' });
  const nextClaim = (await wire('claim', nextAgent, 'original')).result.claim;
  await invoke('begin', { claim: nextClaim });
  assert.equal((await invoke('finish', { claim: nextClaim })).effects, 2);
  assert.deepEqual(await invoke('observe'), { relay_epoch: 1, game_epoch: 1, effects: 2, inflight: 0 });
  assert.equal((await wire('receipt', reader, 'original', reader.binding, 60000)).error.code, 'request_gone');
  assert.equal((await invoke('receipt_compact', { now: 60000 })).removed, 2);
  assert.equal((await invoke('receipt_revoke', { credential: reader.token })).revoked, true);
  assert.equal((await wire('receipt', reader, 'original', reader.binding, 60000)).error.code, 'permission_denied');
  return { passed: true, wire_calls: wireCalls, fixture_calls: fixtureCalls,
    archived_receipt: true,
    profile: 'g2a-epoch-binding-1', relay_epoch: 1, game_epoch: 1, effects: 2,
    limitations: ['candidate profile only', 'trusted fixture commands are not public operations', 'no third-party implementation'] };
}
