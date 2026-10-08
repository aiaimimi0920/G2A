// 手写独立客户端：不导入 Python fixture、schema 生成器或 Python 消费器。
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { createHash } from 'node:crypto';
import { canonical, decode, digest } from '../docs/protocol/codec_peer.mjs';

const child = spawn(process.argv[2], [process.argv[3], '--serve'], { stdio: ['pipe', 'pipe', 'pipe'] });
let stderr = '';
child.stderr.on('data', data => { stderr = (stderr + data).slice(-8192); });
const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]();
let calls = 0, wireCalls = 0, codecCases = 0;
const operations = new Set();
async function command(frame) {
  calls++;
  child.stdin.write(JSON.stringify(frame) + '\n');
  const { value, done } = await lines.next();
  assert.ok(!done, `fixture server closed: ${stderr}`);
  return JSON.parse(value);
}

const principal = (subject, kind) => ({ issuer: 'fixture-enrollment', subject, kind });
const agent = principal('fox', 'agent'), player = principal('alice', 'player'), game = principal('key-quest', 'game');
const instance = { game, instance_id: 'fixture-instance', epoch: 'epoch-1' };
const request = (operation, payload, request_id) => ({ version: 'fixture-only', operation, request_id, payload, extensions: {} });
const envelope = (id, type, sender, payload) => ({ version: 'fixture-only', session_id: 's1', id, type,
  sender, audience: [agent, player], payload, extensions: {} });
const plain = value => JSON.parse(JSON.stringify(value));
async function wire(req, credential = 'agent-fixture', options = {}) {
  wireCalls++; operations.add(req.operation);
  const result = await command({ kind: 'wire', raw: canonical(req).toString('base64'), credential, ...options });
  if (result.fixture_fault) return result;
  const bytes = Buffer.from(result.reply, 'base64'), reply = plain(decode(bytes));
  assert.ok(bytes.equals(canonical(reply)), 'reply must be canonical');
  assert.equal(reply.request_id, req.request_id);
  assert.notEqual(Object.hasOwn(reply, 'result'), Object.hasOwn(reply, 'error'));
  assert.equal(Object.keys(reply).length, 2);
  return reply;
}

// 仅此夹具用到的三个事件类型；整页验证成功前不写 cursor/业务视图。
function reducePage(previous, page) {
  const next = structuredClone(previous);
  assert.equal(page.next_cursor.session_id, 's1');
  assert.equal(page.next_cursor.instance_epoch, 'epoch-1');
  assert.equal(page.high_watermark.session_id, 's1');
  assert.equal(page.high_watermark.instance_epoch, 'epoch-1');
  assert.ok(next.cursor <= page.next_cursor.sequence && page.next_cursor.sequence <= page.high_watermark.sequence);
  let last = next.cursor;
  for (const event of page.events) {
    assert.ok(last < event.sequence && event.sequence <= page.next_cursor.sequence);
    const e = event.envelope;
    assert.equal(e.session_id, 's1'); assert.equal(e.version, 'fixture-only');
    assert.ok(e.audience.some(p => digest('message', p) === digest('message', agent)));
    if (e.type === 'chat.message') next.chats.push(e.payload.text);
    else if (e.type === 'game.context') next.contexts[e.payload.category] = e.payload.content;
    else if (e.type === 'action.state') {
      const action = e.payload.action, old = next.actions[action.request_id];
      assert.equal(action.session_id, 's1');
      assert.ok(!old || action.result_revision > old.result_revision);
      assert.ok(!old || old.effect === 'none' || action.effect !== 'none');
      next.actions[action.request_id] = structuredClone(action);
    } else assert.fail('unsupported fixture event');
    last = event.sequence;
  }
  next.cursor = page.next_cursor.sequence;
  return next;
}

const timeout = setTimeout(() => { child.kill(); process.exitCode = 1; }, 60000);
try {
  // 整数形键顺序、非 BMP 标量排序、控制转义、组合字符和特殊对象键均为手写见证。
  const valid = ['null', 'true', '-9007199254740991', '9007199254740991',
    '{"10":"十","2":"二","😀":"face","￿":"bmp","é":"é","é":"é"}',
    '{"__proto__":{"constructor":1},"value":"\\u0000\\b\\t\\n\\f\\r\\\"\\\\/"}',
    '["\\ud83d\\ude00","中文",false,0,{"z":1,"a":2}]',
    ' { "nested": [[], {}, [1, 2]] } '];
  const invalid = [['{"a":1,"\\u0061":2}', 'duplicate_key'], ['1.0', 'invalid_number'],
    ['1e0', 'invalid_number'], ['-0', 'invalid_number'], ['NaN', 'invalid_number'],
    ['9007199254740992', 'integer_out_of_range'], ['"\\ud800"', 'invalid_unicode'],
    ['{"x":}', 'invalid_json'], ['[1,]', 'invalid_json'], ['01', 'invalid_json'],
    ['['.repeat(33) + '0' + ']'.repeat(33), 'depth_limit'],
    [Buffer.from([239, 187, 191, 123, 125]), 'bom_forbidden'], [Buffer.from([255]), 'invalid_utf8'],
    ['"' + 'x'.repeat(65537) + '"', 'string_limit'], ['[' + Array(4097).fill('0').join(',') + ']', 'container_limit']];
  for (const text of valid) {
    const raw = Buffer.from(text), value = decode(raw);
    const other = await command({ kind: 'codec', raw: raw.toString('base64') });
    assert.equal(other.canonical, canonical(value).toString('hex'));
    assert.equal(other.digest, digest('message', value));
    codecCases++;
  }
  for (const [text, error] of invalid) {
    const raw = Buffer.isBuffer(text) ? text : Buffer.from(text);
    assert.throws(() => decode(raw), e => e.message === error);
    const other = await command({ kind: 'codec', raw: raw.toString('base64') });
    assert.equal(other.error, error); codecCases++;
  }

  const start = (await wire(request('session.snapshot', { session_id: 's1' }, 'snapshot-start'))).result;
  assert.equal(start.cursor.sequence, 0); assert.deepEqual(start.actions, []);
  const heartbeat = request('session.heartbeat', { session_id: 's1' }, 'heartbeat-1');
  const lease = (await wire(heartbeat)).result.lease_deadline;
  assert.equal((await wire(heartbeat, 'agent-fixture', { now: 2000 })).result.lease_deadline, lease);
  const chat = request('chat.send', envelope('m1', 'chat.message', agent,
    { channel: 'private', text: '你好，寻找钥匙 🗝', source_refs: [], provenance: [] }), 'chat-1');
  assert.equal((await wire(chat, 'agent-fixture', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  const receipt = (await wire(chat)).result;
  assert.equal(receipt.duplicate, true); assert.equal(receipt.record_digest, digest('message', chat.payload));
  const conflict = structuredClone(chat); conflict.payload.payload.text = 'changed';
  assert.equal((await wire(conflict)).error.code, 'id_conflict');
  await wire(request('context.publish', envelope('c1', 'game.context', game,
    { category: 'room', content: 'hall', provenance: [] }), 'context-1'), 'game-fixture');
  const action = request('action.request', { ...envelope('a1', 'action.request', agent,
    { action: 'find-key', arguments: { room: 'hall' }, deadline: 30000 }), expected_capabilities_revision: 1 }, 'action-1');
  assert.equal((await wire(action)).result.record_digest, digest('message', action.payload));
  assert.equal((await wire(action)).result.duplicate, true);
  const ticket = (await wire(request('action.claim', { session_id: 's1', action_id: 'a1', worker: principal('worker-1', 'service') },
    'claim-1'), 'worker-1-fixture')).result.ticket;
  assert.equal(ticket.request_id, 'a1');
  for (const step of [1, 2]) assert.equal((await command({ kind: 'effect', ticket, step })).world_effects, step);
  const fact = { state: 'succeeded', effect: 'committed', result: { item: 'gold-key' },
    steps: [1, 2].map(step => ({ step, effect: 'committed', evidence_ref: `${ticket.proof_ref}-step-${step}` })) };
  const report = request('action.commit_result', { ticket, fact }, 'commit-1');
  assert.equal((await wire(report, 'worker-1-fixture', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  const final = (await wire(report, 'worker-1-fixture')).result;
  assert.deepEqual(final.known_result, { item: 'gold-key' });
  assert.equal((await command({ kind: 'effect', ticket, step: 1 })).world_effects, 2);
  assert.deepEqual((await wire(request('action.query', { session_id: 's1', action_id: 'a1' }, 'query-1'))).result, final);

  const poll = request('session.events', { session_id: 's1', cursor: start.cursor, page_size: 64 }, 'poll-1');
  const page = (await wire(poll)).result;
  assert.equal(page.events.length, 7); assert.equal(page.next_cursor.sequence, 7);
  const initial = { cursor: 0, chats: [], contexts: {}, actions: {} };
  const invalidPage = structuredClone(page); invalidPage.events.at(-1).sequence = 8;
  assert.throws(() => reducePage(initial, invalidPage)); assert.equal(initial.cursor, 0);
  const view = reducePage(initial, page);
  assert.deepEqual(view.actions.a1, final); assert.deepEqual(view.chats, ['你好，寻找钥匙 🗝']);
  assert.equal(view.contexts.room, 'hall');
  const snapshot = (await wire(request('session.snapshot', { session_id: 's1' }, 'snapshot-end'))).result;
  assert.deepEqual(snapshot.actions, [final]); assert.equal(snapshot.cursor.sequence, view.cursor);
  await command({ kind: 'compact' });
  const gap = await wire(request('session.events', poll.payload, 'poll-gap'));
  assert.equal(gap.error.code, 'history_gap'); assert.deepEqual(gap.error.details.snapshot.actions, [final]);
  assert.deepEqual(gap.error.details.next_cursor, snapshot.cursor);

  assert.equal((await wire(request('capability.replace', { instance, expected_revision: 1, definitions: [] }, 'cap-1'), 'game-fixture')).result.revision, 2);
  const members = { instance, expected_revision: 1, verified_members: [player, agent], membership_proof_ref: 'members-1' };
  await command({ kind: 'membership_proof', payload: members });
  assert.equal((await wire(request('membership.replace', members, 'members-1'), 'game-fixture')).result.revision, 2);
  await wire(request('permission.revoke', { object_type: 'result_read', object_id: 's1', expected_revision: 1 }, 'revoke-1'), 'player-fixture');
  assert.deepEqual((await wire(request('session.snapshot', { session_id: 's1' }, 'snapshot-revoked'))).result.actions, []);
  assert.deepEqual(view.actions.a1.known_result, { item: 'gold-key' }); // 已收到的明文不能远程收回。
  assert.equal((await wire(request('action.query', { session_id: 's1', action_id: 'a1' }, 'query-revoked'))).error.code, 'permission_denied');
  assert.equal((await wire(request('session.close', { session_id: 's1', reason: 'left' }, 'close-1'), 'player-fixture')).result.state, 'closed');
  assert.ok((await wire(heartbeat)).error);

  // 从空 authority 进入，而非直接拿一个预置 active session；此处不复用 Python Requested fixture。
  await command({ kind: 'admission_start' });
  const describe = await wire(request('describe', { instance }, 'describe-1'), 'agent-identity');
  const d = describe.result;
  assert.equal(d.instance.instance_id, 'fixture-instance');
  const requested = { player, agent, supported_versions: ['fixture-only'], bindings: d.bindings,
    trust_profiles: ['test-enrolled'], privacy_model: d.privacy_model, supported_features: d.supported_features,
    required_features: [], action_ids: ['find-key'], context_categories: ['room'], audiences: [player, agent],
    policy: { proactive_chat: false, extensions: {} }, companion_defaults: { extensions: {} },
    limits: d.limits, maximum_grant_duration_ms: 300000, ledger_durability: 'volatile', extensions: {} };
  const create = request('offer.create', { entry: 'companion', descriptor_id: d.descriptor_id,
    expected_descriptor_revision: d.revision, requested }, 'offer-create-1');
  const offer = (await wire(create, 'agent-identity')).result;
  assert.equal(offer.state, 'pending'); assert.equal(offer.scope_digest, digest('scope', offer.immutable_scope));
  assert.deepEqual((await wire(create, 'agent-identity')).result, offer);
  const decision = { offer_id: offer.offer_id, scope_digest: offer.scope_digest, allow: true, remember: false,
    launch_permission: false, decision_ref: 'player-decision-1' };
  const approve = request('offer.decide', decision, 'approve-1');
  assert.equal((await wire(approve, 'player-fixture')).error.code, 'consent_required');
  await command({ kind: 'admission_decision', payload: decision });
  assert.equal((await wire(approve, 'player-fixture', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  assert.equal((await wire(approve, 'player-fixture')).result.state, 'approved');
  assert.equal((await wire(request('offer.get', { offer_id: offer.offer_id }, 'offer-read'), 'agent-identity')).result.state, 'approved');
  const invitation = (await wire(request('invitation.redeem', { offer_id: offer.offer_id,
    join_intent: { scope_digest: offer.scope_digest } }, 'redeem-1'), 'agent-identity')).result;
  const joinRequest = request('session.join', { invitation_id: invitation.invitation_id, join_intent: invitation.join_intent }, 'join-1');
  assert.equal((await wire(joinRequest, 'agent-identity')).error.code, 'permission_denied');
  const pending = (await wire(joinRequest, invitation.invitation_credential)).result;
  assert.deepEqual(pending, { status: 'join_pending', session_id: 's1' });
  const lookup = request('operation.get', { operation: 'session.join', original_request_id: 'join-1' }, 'join-status');
  assert.equal((await wire(lookup, 'agent-identity')).result.state, 'pending');
  const readyState = (await command({ kind: 'admission_finish' })).session;
  assert.equal(readyState.ready, true); assert.equal(readyState.sequence, 1);
  const delivery = (await wire(joinRequest, invitation.invitation_credential)).result;
  assert.equal(delivery.status, 'ready'); assert.equal(delivery.event_high_watermark.sequence, 1);
  const publicStatus = (await wire(lookup, 'agent-identity')).result;
  assert.equal(publicStatus.state, 'done');
  assert.ok(!canonical(publicStatus).includes(Buffer.from(delivery.control_credential)));
  assert.equal((await wire(lookup, 'player-fixture')).error.code, 'permission_denied');
  const readyPage = (await wire(request('session.events', { session_id: 's1', cursor: start.cursor, page_size: 64 }, 'ready-page'), delivery.control_credential)).result;
  assert.equal(readyPage.events.length, 1); assert.equal(readyPage.events[0].envelope.type, 'session.ready');
  assert.equal(readyPage.events[0].envelope.payload.session.ready, true);
  const joinedSnapshot = (await wire(request('session.snapshot', { session_id: 's1' }, 'joined-snapshot'), delivery.control_credential)).result;
  assert.deepEqual(joinedSnapshot.cursor, delivery.event_high_watermark);
  await wire(request('session.close', { session_id: 's1', reason: 'left' }, 'joined-close'), 'player-fixture');
  assert.equal((await wire(joinRequest, invitation.invitation_credential)).result.status, 'completed_without_secret');

  // 最小 core 不依赖服务器夹具中的虚构 action；独立客户端实际完成加入到关闭。
  await command({ kind: 'admission_start', core_only: true });
  const coreDescriptor = (await wire(request('describe', { instance }, 'core-describe'), 'agent-identity')).result;
  assert.deepEqual(coreDescriptor.actions, []);
  const coreOffer = (await wire(request('offer.create', { entry: 'companion', descriptor_id: coreDescriptor.descriptor_id,
    expected_descriptor_revision: coreDescriptor.revision, requested: { ...requested,
      supported_features: coreDescriptor.supported_features, action_ids: [], limits: coreDescriptor.limits,
      ledger_durability: 'volatile' } }, 'core-offer'), 'agent-identity')).result;
  assert.deepEqual(coreOffer.immutable_scope.features, ['core.events', 'core.session']);
  const coreDecision = { ...decision, offer_id: coreOffer.offer_id, scope_digest: coreOffer.scope_digest, decision_ref: 'core-approve' };
  await command({ kind: 'admission_decision', payload: coreDecision });
  assert.equal((await wire(request('offer.decide', coreDecision, 'core-approve'), 'player-fixture')).result.state, 'approved');
  const coreInvitation = (await wire(request('invitation.redeem', { offer_id: coreOffer.offer_id,
    join_intent: { scope_digest: coreOffer.scope_digest } }, 'core-redeem'), 'agent-identity')).result;
  const coreJoin = request('session.join', { invitation_id: coreInvitation.invitation_id,
    join_intent: coreInvitation.join_intent }, 'core-join');
  assert.equal((await wire(coreJoin, coreInvitation.invitation_credential)).result.status, 'join_pending');
  await command({ kind: 'admission_finish' });
  const coreDelivery = (await wire(coreJoin, coreInvitation.invitation_credential)).result;
  const coreSnapshot = (await wire(request('session.snapshot', { session_id: 's1' }, 'core-snapshot'), coreDelivery.control_credential)).result;
  assert.deepEqual(coreSnapshot.definitions, []); assert.deepEqual(coreSnapshot.actions, []);
  const coreChat = request('chat.send', envelope('core-chat', 'chat.message', agent,
    { channel: 'private', text: '只有 core 也能聊天', source_refs: [], provenance: [] }), 'core-chat');
  assert.equal((await wire(coreChat, coreDelivery.control_credential)).result.duplicate, false);
  assert.equal((await wire(coreChat, coreDelivery.control_credential)).result.duplicate, true);
  const corePage = (await wire(request('session.events', { session_id: 's1', cursor: coreSnapshot.cursor,
    page_size: 64 }, 'core-events'), coreDelivery.control_credential)).result;
  assert.deepEqual(corePage.events.map(e => e.envelope.type), ['chat.message']);
  assert.equal((await wire(request('action.query', { session_id: 's1', action_id: 'a1' }, 'core-no-action'),
    coreDelivery.result_read_handle)).error.code, 'feature_unsupported');
  assert.equal((await wire(request('capability.replace', { instance, expected_revision: 1, definitions: [] },
    'core-no-capabilities'), 'game-fixture')).error.code, 'feature_unsupported');
  assert.equal((await wire(request('session.close', { session_id: 's1', reason: 'left' }, 'core-close'), 'player-fixture')).result.state, 'closed');
  assert.equal((await wire(request('operation.get', { operation: 'session.join', original_request_id: 'core-join' },
    'core-completed'), 'agent-identity')).result.state, 'done');

  await command({ kind: 'control_start', high_risk: true });
  const controlDescriptor = (await wire(request('describe', { instance }, 'control-describe'), 'agent-identity')).result;
  const controlOffer = (await wire(request('offer.create', { entry: 'companion', descriptor_id: controlDescriptor.descriptor_id,
    expected_descriptor_revision: controlDescriptor.revision, requested: { ...requested,
      supported_features: controlDescriptor.supported_features, limits: controlDescriptor.limits, ledger_durability: 'durable' } },
  'control-offer'), 'agent-identity')).result;
  const controlDecision = { ...decision, offer_id: controlOffer.offer_id, scope_digest: controlOffer.scope_digest, decision_ref: 'control-approve' };
  await command({ kind: 'admission_decision', payload: controlDecision });
  await wire(request('offer.decide', controlDecision, 'control-approve'), 'player-fixture');
  const controlInvitation = (await wire(request('invitation.redeem', { offer_id: controlOffer.offer_id,
    join_intent: { scope_digest: controlOffer.scope_digest } }, 'control-redeem'), 'agent-identity')).result;
  const controlJoin = request('session.join', { invitation_id: controlInvitation.invitation_id, join_intent: controlInvitation.join_intent }, 'control-join');
  await wire(controlJoin, controlInvitation.invitation_credential);
  await command({ kind: 'admission_finish' });
  const originalControl = (await wire(controlJoin, controlInvitation.invitation_credential)).result;
  const resume = request('session.resume', { session_id: 's1', expected_generation: 1 }, 'resume-1');
  assert.equal((await wire(resume, 'agent-identity', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  const resumed = (await wire(resume, 'agent-identity')).result;
  assert.equal(resumed.session.control_generation, 2);
  assert.equal(resumed.session.lease_deadline, originalControl.session.lease_deadline);
  assert.ok((await wire(request('session.snapshot', { session_id: 's1' }, 'old-controller'), originalControl.control_credential)).error);
  await command({ kind: 'control_restart' });
  assert.equal((await wire(resume, 'agent-identity')).result.status, 'completed_without_secret');
  const afterRestart = request('session.resume', { session_id: 's1', expected_generation: 2 }, 'resume-after-restart');
  const restored = (await wire(afterRestart, 'agent-identity')).result;
  assert.equal(restored.session.transport_epoch, 'transport-2'); assert.equal(restored.session.control_generation, 3);
  const handoffPayload = { session_id: 's1', expected_generation: 3, target_device: 'device-b',
    decision_ref: 'handoff-decision', target_proof_ref: 'target-proof' };
  await command({ kind: 'control_handoff_proof', payload: handoffPayload });
  const transfer = (await wire(request('session.handoff', handoffPayload, 'handoff-1'), 'player-fixture')).result;
  assert.equal(transfer.status, 'acquiring'); assert.equal(transfer.new_generation, 4);
  assert.equal((await wire(afterRestart, 'agent-identity')).result.status, 'completed_without_secret');
  const claimTarget = request('session.claim_control', { session_id: 's1', transfer_id: transfer.transfer_id, target_device: 'device-b' }, 'claim-target');
  assert.equal((await wire(claimTarget, 'agent-identity')).error.code, 'permission_denied');
  assert.equal((await wire(claimTarget, 'agent-b')).result.status, 'pending');
  await command({ kind: 'control_finish', transfer_id: transfer.transfer_id });
  const targetControl = (await wire(claimTarget, 'agent-b')).result;
  assert.equal(targetControl.status, 'ready'); assert.equal(targetControl.session.controller_device, 'device-b');
  const transferStatus = (await wire(request('operation.get', { operation: 'session.handoff', original_request_id: 'handoff-1' }, 'handoff-status'), 'player-fixture')).result;
  assert.equal(transferStatus.state, 'done'); assert.ok(!canonical(transferStatus).includes(Buffer.from(targetControl.control_credential)));
  const controlPage = (await wire(request('session.events', { session_id: 's1', cursor: originalControl.event_high_watermark, page_size: 64 }, 'control-events'), targetControl.control_credential)).result;
  assert.deepEqual(controlPage.events.map(e => e.envelope.type), ['session.control_changed', 'session.control_changed', 'session.control_changed', 'session.ready']);
  assert.deepEqual(controlPage.events.map(e => e.envelope.payload.session.control_generation), [2, 3, 4, 4]);
  assert.equal(controlPage.next_cursor.sequence, targetControl.event_high_watermark.sequence);

  // 查询原控制/业务回执，不以关闭后的当前状态改写已完成事实，也不重放执行凭据。
  const statusLookup = (operation, id) => request('operation.get', { operation, original_request_id: id }, 'status-poll');
  const statusConfirmation = { session_id: 's1', action_request_id: 'status-action', action: 'find-key',
    arguments_digest: digest('action-arguments', { room: 'hall' }), definition_digest: digest('action-definition', controlDescriptor.actions[0]),
    expires_at: 5000, decision_ref: 'status-decision' };
  await command({ kind: 'action_decision', payload: statusConfirmation });
  const statusConfirmed = (await wire(request('action.confirm', statusConfirmation, 'status-confirm'), 'player-fixture')).result;
  const statusAction = request('action.request', { ...envelope('status-action', 'action.request', agent,
    { action: 'find-key', arguments: { room: 'hall' }, deadline: 30000, confirmation: statusConfirmed.confirmation_id }),
    expected_capabilities_revision: 1 }, 'status-transport');
  assert.equal((await wire(statusAction, targetControl.control_credential, { fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.equal((await wire(statusLookup('action.request', 'status-action'), 'agent-b')).error.code, 'permission_denied');
  assert.equal((await wire(statusAction, targetControl.control_credential, { fault: 'after_commit' })).fixture_fault, 'after_commit');
  const statusAccepted = (await wire(statusLookup('action.request', 'status-action'), 'agent-b')).result;
  assert.equal(statusAccepted.state, 'done'); assert.equal(statusAccepted.action.state, 'pending');
  assert.equal(statusAccepted.receipt.record_digest, digest('message', statusAction.payload));
  assert.equal((await wire(statusLookup('action.request', 'status-transport'), 'agent-b')).error.code, 'permission_denied');
  assert.equal((await wire({ ...statusAction, request_id: 'status-new-transport' }, targetControl.control_credential)).result.duplicate, true);
  const statusTicket = (await wire(request('action.claim', { session_id: 's1', action_id: 'status-action', worker: principal('worker-1', 'service') },
    'status-claim'), 'worker-1-fixture')).result.ticket;
  assert.equal((await command({ kind: 'effect', ticket: statusTicket, step: 1 })).world_effects, 1);
  await wire(request('action.cancel', envelope('status-cancel', 'action.cancel', agent, { request_id: 'status-action' }),
    'status-cancel-transport'), targetControl.control_credential);
  const statusPartialFact = { state: 'cancelled', effect: 'partial', steps: [{ step: 1, effect: 'committed', evidence_ref: `${statusTicket.proof_ref}-step-1` }] };
  await wire(request('action.commit_result', { ticket: statusTicket, fact: statusPartialFact }, 'status-commit'), 'worker-1-fixture');
  await wire(request('session.close', { session_id: 's1', reason: 'left' }, 'status-close'), 'player-fixture');
  const statusBeforeRestart = await command({ kind: 'operation_observe' });
  await command({ kind: 'control_restart' });
  for (const [operation, id, identity] of [['session.join', 'control-join', 'agent-b'], ['session.resume', 'resume-1', 'agent-identity'],
    ['session.handoff', 'handoff-1', 'player-fixture'], ['session.claim_control', 'claim-target', 'agent-b'],
    ['session.close', 'status-close', 'player-fixture'], ['session.events', 'control-events', 'agent-b'],
    ['action.confirm', 'status-confirm', 'player-fixture']]) {
    const result = (await wire(statusLookup(operation, id), identity)).result;
    assert.equal(result.state, 'done');
    for (const secret of [targetControl.control_credential, targetControl.result_read_handle, statusTicket.ticket_id, statusTicket.proof_ref])
      assert.ok(!canonical(result).includes(Buffer.from(secret)));
  }
  const statusPartial = (await wire(statusLookup('action.cancel', 'status-cancel'), 'agent-b')).result;
  assert.equal(statusPartial.state, 'done'); assert.equal(statusPartial.action.state, 'cancelled'); assert.equal(statusPartial.action.effect, 'partial');
  assert.equal((await wire(statusLookup('action.claim', 'status-claim'), 'agent-b')).error.code, 'permission_denied');
  assert.equal((await wire(statusLookup('action.confirm', 'status-confirm'), 'agent-b')).error.code, 'permission_denied');
  const statusAfterQueries = await command({ kind: 'operation_observe' });
  assert.deepEqual(statusAfterQueries, statusBeforeRestart);
  assert.equal(statusAfterQueries.world_effects, 1); assert.equal(statusAfterQueries.confirmations, 1);
  assert.equal(statusAfterQueries.consumed_confirmations, 1); assert.equal(statusAfterQueries.action_receipts, 2);
  const statusRevoke = { object_type: 'result_read', object_id: 's1', expected_revision: 1 };
  await wire(request('permission.revoke', statusRevoke, 'status-revoke'), 'player-fixture');
  assert.equal((await wire(statusLookup('permission.revoke', 'status-revoke'), 'player-fixture')).result.revocation.state, 'revoked');
  assert.equal((await wire(statusLookup('action.request', 'status-action'), 'agent-b')).error.code, 'permission_denied');
  assert.equal((await wire(statusLookup('action.cancel', 'status-cancel'), 'agent-b')).error.code, 'permission_denied');

  // 关闭且超过保留期才清理；账本假重启仍保留终态，绝不重放已发生效果。
  const receiptCompaction = await command({ kind: 'receipt_compact', now: 1000000 });
  assert.ok(receiptCompaction.removed >= 2); assert.equal(receiptCompaction.remaining, 0);
  assert.equal((await wire(statusAction, targetControl.control_credential, { now: 1000000 })).error.code, 'grant_revoked');
  await command({ kind: 'control_restart', now: 1000000 });
  const changedRetiredAction = structuredClone(statusAction);
  changedRetiredAction.payload.id = 'retired-new-id'; changedRetiredAction.request_id = 'retired-new-transport';
  assert.equal((await wire(changedRetiredAction, targetControl.control_credential, { now: 1000000 })).error.code, 'grant_revoked');
  assert.equal((await command({ kind: 'receipt_compact', now: 1000000 })).removed, 0);
  const afterReceiptCompaction = await command({ kind: 'operation_observe' });
  assert.equal(afterReceiptCompaction.action_receipts, 0);
  assert.equal(afterReceiptCompaction.world_effects, 1);
  assert.equal(afterReceiptCompaction.consumed_confirmations, 1);

  // 呈现设备为独立假效果域；authority 在设备应用后丢 ACK，客户端重试仍只应用一次。
  const deviceObservation = (await command({ kind: 'presentation_start' })).observation;
  const pd = (await wire(request('describe', { instance }, 'p-describe'), 'agent-identity')).result;
  const po = (await wire(request('offer.create', { entry: 'companion', descriptor_id: pd.descriptor_id,
    expected_descriptor_revision: pd.revision, requested: { ...requested, supported_features: pd.supported_features,
      limits: pd.limits, ledger_durability: 'durable', presentation_terms: { mode: 'hide_desktop', device_id: 'device-a' } } },
  'p-offer'), 'agent-identity')).result;
  const pDecision = { ...decision, offer_id: po.offer_id, scope_digest: po.scope_digest, decision_ref: 'p-approve' };
  await command({ kind: 'admission_decision', payload: pDecision });
  await wire(request('offer.decide', pDecision, 'p-approve'), 'player-fixture');
  const pi = (await wire(request('invitation.redeem', { offer_id: po.offer_id, join_intent: {
    scope_digest: po.scope_digest, selected_device: 'device-a', presentation_observation: deviceObservation } }, 'p-redeem'), 'agent-identity')).result;
  const pj = request('session.join', { invitation_id: pi.invitation_id, join_intent: pi.join_intent }, 'p-join');
  assert.equal((await wire(pj, pi.invitation_credential)).result.status, 'join_pending');
  assert.equal((await command({ kind: 'admission_finish' })).session.ready, false);
  async function acquireRequest(jid, device, generation) {
    const proof = await command({ kind: 'presentation_proof', job_id: jid });
    return request('presentation.acquire', { session_id: 's1', generation, device_id: device,
      terms: { mode: 'hide_desktop', device_id: device }, scope_digest: po.scope_digest, ...proof }, jid);
  }
  const pa = await acquireRequest('admission-s1', 'device-a', 1);
  assert.equal((await wire(pa, 'presentation-fixture', { fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.deepEqual(await command({ kind: 'presentation_observe', device_id: 'device-a' }),
    { actual_visible: false, render_calls: 1, occupation_count: 1 });
  assert.equal((await command({ kind: 'admission_finish' })).session.ready, false);
  const applied = (await wire(pa, 'presentation-fixture')).result;
  assert.equal(applied.applied, true); assert.equal(applied.actual_visible, false);
  assert.equal(applied.operation_id, pa.request_id); assert.equal(applied.generation, 1);
  await command({ kind: 'admission_finish' });
  const pInitial = (await wire(pj, pi.invitation_credential)).result;
  assert.equal(pInitial.status, 'ready');
  const pHandoff = { ...handoffPayload, expected_generation: 1, decision_ref: 'p-move', target_proof_ref: 'p-target' };
  await command({ kind: 'control_handoff_proof', payload: pHandoff });
  const pt = (await wire(request('session.handoff', pHandoff, 'p-handoff'), 'player-fixture')).result;
  assert.equal(pt.status, 'releasing');
  const pTarget = await acquireRequest('presentation-control-1', 'device-b', 2);
  assert.equal((await wire(pTarget, 'presentation-fixture')).error.code, 'transfer_in_progress');
  const oldRelease = request('presentation.release', { session_id: 's1', generation: 1, device_id: 'device-a' }, 'p-release-old');
  assert.equal((await wire(oldRelease, 'presentation-fixture', { fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.equal((await command({ kind: 'control_finish', transfer_id: pt.transfer_id })).transfer.status, 'releasing');
  assert.equal((await wire(oldRelease, 'presentation-fixture')).result.actual_visible, true);
  assert.equal((await command({ kind: 'control_finish', transfer_id: pt.transfer_id })).transfer.status, 'acquiring');
  const targetAck = (await wire(pTarget, 'presentation-fixture')).result;
  assert.equal(targetAck.applied, true); assert.equal(targetAck.generation, 2);
  assert.equal((await command({ kind: 'control_finish', transfer_id: pt.transfer_id })).transfer.status, 'ready');
  assert.deepEqual((await wire(pTarget, 'presentation-fixture')).result, targetAck);
  const pClaim = request('session.claim_control', { session_id: 's1', transfer_id: pt.transfer_id, target_device: 'device-b' }, 'p-claim');
  const pDelivery = (await wire(pClaim, 'agent-b')).result;
  assert.equal(pDelivery.status, 'ready'); assert.equal(pDelivery.session.controller_device, 'device-b');
  const pEvents = (await wire(request('session.events', { session_id: 's1', cursor: pInitial.event_high_watermark, page_size: 64 },
    'p-events'), pDelivery.control_credential)).result;
  assert.deepEqual(pEvents.events.map(e => e.envelope.type), ['session.control_changed', 'session.ready']);
  assert.deepEqual(pEvents.events.map(e => e.envelope.payload.session.ready), [false, true]);
  await wire(request('session.close', { session_id: 's1', reason: 'left' }, 'p-close'), 'player-fixture');
  const pReleased = (await wire(request('presentation.release', { session_id: 's1', generation: 2, device_id: 'device-b' },
    'p-release-target'), 'presentation-fixture')).result;
  assert.equal(pReleased.applied, true); assert.equal(pReleased.actual_visible, true);
  assert.ok((await wire(pTarget, 'presentation-fixture')).error);
  const pDeviceA = await command({ kind: 'presentation_observe', device_id: 'device-a' });
  const pDeviceB = await command({ kind: 'presentation_observe', device_id: 'device-b' });
  assert.deepEqual(pDeviceA, { actual_visible: true, render_calls: 2, occupation_count: 0 });
  assert.deepEqual(pDeviceB, { actual_visible: true, render_calls: 2, occupation_count: 0 });

  // 设备生命周期独立场景：JS 自己组请求，fixture 只给可信证明引用与版本值。
  const lifecycleObservation = (await command({ kind: 'presentation_start' })).observation;
  const ld = (await wire(request('describe', { instance }, 'l-describe'), 'agent-identity')).result;
  const lo = (await wire(request('offer.create', { entry: 'companion', descriptor_id: ld.descriptor_id,
    expected_descriptor_revision: ld.revision, requested: { ...requested, supported_features: ld.supported_features,
      limits: ld.limits, ledger_durability: 'durable', presentation_terms: { mode: 'hide_desktop', device_id: 'device-a' } } },
    'l-offer'), 'agent-identity')).result;
  const lDecision = { ...decision, offer_id: lo.offer_id, scope_digest: lo.scope_digest, decision_ref: 'l-approve' };
  await command({ kind: 'admission_decision', payload: lDecision });
  await wire(request('offer.decide', lDecision, 'l-approve'), 'player-fixture');
  const li = (await wire(request('invitation.redeem', { offer_id: lo.offer_id, join_intent: {
    scope_digest: lo.scope_digest, selected_device: 'device-a', presentation_observation: lifecycleObservation } },
    'l-redeem'), 'agent-identity')).result;
  const lj = request('session.join', { invitation_id: li.invitation_id, join_intent: li.join_intent }, 'l-join');
  await wire(lj, li.invitation_credential);
  const lBase = { session_id: 's1', generation: 1, device_id: 'device-a',
    terms: { mode: 'hide_desktop', device_id: 'device-a' }, scope_digest: lo.scope_digest };
  const lAcquireProof = await command({ kind: 'presentation_proof', job_id: 'admission-s1' });
  await wire(request('presentation.acquire', { ...lBase, ...lAcquireProof }, 'admission-s1'), 'presentation-fixture');
  await command({ kind: 'admission_finish' });
  const lReady = (await wire(lj, li.invitation_credential)).result;
  const lHeartbeat = request('session.heartbeat', { session_id: 's1' }, 'l-heartbeat');
  await wire(lHeartbeat, lReady.control_credential, { now: 2000 });
  const lProof = await command({ kind: 'presentation_lease', job_id: 'admission-s1' });
  const lRenew = request('presentation.renew', { ...lBase, ...lProof.proof }, lProof.request_id);
  assert.equal((await wire(lRenew, 'player-fixture', { now: 2000 })).error.code, 'permission_denied');
  assert.equal((await wire(lRenew, 'presentation-fixture', { now: 2000, fault: 'before_commit' })).fixture_fault, 'before_commit');
  const lStatus = request('operation.get', { operation: 'presentation.renew', original_request_id: lProof.request_id }, 'l-status');
  assert.equal((await wire(lStatus, 'player-fixture', { now: 2000 })).result.state, 'pending');
  const lRestart = await command({ kind: 'presentation_restart', device_id: 'device-a', now: 2000 });
  assert.equal(lRestart.kept_occupations, 1); assert.equal(lRestart.observation.device_epoch, 2);
  assert.equal((await wire(lStatus, 'player-fixture', { now: 2000 })).result.state, 'done');
  assert.equal((await wire(lRenew, 'presentation-fixture', { now: 2000 })).error.code, 'approval_stale');
  assert.deepEqual((await command({ kind: 'presentation_sweep', now: 2000 })).attempted, []);
  await wire(lHeartbeat, lReady.control_credential, { now: 3000 });
  assert.equal((await command({ kind: 'presentation_lease', job_id: 'admission-s1' })).request_id, lProof.request_id);
  await wire(request('session.heartbeat', { session_id: 's1' }, 'l-next-heartbeat'), lReady.control_credential, { now: 3000 });
  const lNext = await command({ kind: 'presentation_lease', job_id: 'admission-s1' });
  assert.equal(lNext.proof.device_epoch, 2); assert.equal(lNext.proof.lease_revision, 3);
  const lNextRenew = request('presentation.renew', { ...lBase, ...lNext.proof }, lNext.request_id);
  const lAck = (await wire(lNextRenew, 'presentation-fixture', { now: 3000 })).result;
  assert.equal(lAck.lease_deadline, lNext.proof.deadline);
  assert.deepEqual((await wire(lNextRenew, 'presentation-fixture', { now: 3000 })).result, lAck);
  await wire(request('session.close', { session_id: 's1', reason: 'left' }, 'l-close'), 'player-fixture', { now: 3000 });
  await command({ kind: 'presentation_reachable', device_id: 'device-a', reachable: false });
  assert.equal((await command({ kind: 'presentation_sweep', now: 3000 })).pending_releases, 1);
  await command({ kind: 'presentation_reachable', device_id: 'device-a', reachable: true });
  assert.equal((await command({ kind: 'presentation_sweep', now: 4000, fault: 'before_commit' })).fixture_fault, 'before_commit');
  const lReleased = await command({ kind: 'presentation_observe', device_id: 'device-a' });
  assert.equal(lReleased.actual_visible, true); assert.equal(lReleased.occupation_count, 0);
  const lRecovery = await command({ kind: 'presentation_sweep', now: 4000 });
  assert.equal(lRecovery.pending_releases, 0);
  assert.deepEqual(await command({ kind: 'presentation_observe', device_id: 'device-a' }), lReleased);
  assert.ok((await wire(lNextRenew, 'presentation-fixture', { now: 4000 })).error);

  // 独立编写 fixture 字节和 Manifest；服务端不为此客户端生成资源摘要或请求模板。
  const assetOrigin = 'https://assets.fixture.invalid', assetMedia = 'application/vnd.g2a.fixture-avatar+json';
  const compatibility = { profile: 'fixture-avatar', revision: '1', properties: { variant: 1 } };
  function makeAsset(id, dependencies = []) {
    const bytes = canonical({ fixture_format: 'fixture-1', compatibility, dependencies: dependencies.map(a => a.content_digest).sort(),
      entries: [{ path: `${id}.txt`, kind: 'file', content: 'fixture data' }], model: { label: id } });
    return { bytes, manifest: { asset_id: id, content_digest: createHash('sha256').update(bytes).digest('hex'), byte_size: bytes.length,
      media_type: assetMedia, format_version: 'fixture-1', compatibility, dependency_manifests: dependencies,
      approved_origins: [assetOrigin], license_claim: 'fixture-only', issuer: game, sandbox_requirements: ['declarative-only'], locator: `${assetOrigin}/${id}` } };
  }
  const leafAsset = makeAsset('leaf'), rootAsset = makeAsset('root', [leafAsset.manifest]);
  async function bootAssets(corrupt) {
    const observation = (await command({ kind: 'asset_start', assets: [leafAsset, rootAsset].map((a, index) => ({
      locator: a.manifest.locator, raw: (corrupt && index === 1 ? Buffer.concat([a.bytes.subarray(0, -1), Buffer.from('x')]) : a.bytes).toString('base64') })) })).observation;
    const ad = (await wire(request('describe', { instance }, 'a-describe'), 'agent-identity')).result;
    const ao = (await wire(request('offer.create', { entry: 'companion', descriptor_id: ad.descriptor_id, expected_descriptor_revision: ad.revision,
      requested: { ...requested, supported_features: ad.supported_features, limits: ad.limits, ledger_durability: 'durable',
        forced_avatar: { kind: 'manifest', manifest: rootAsset.manifest }, presentation_terms: { mode: 'hide_desktop', device_id: 'device-a' } } }, 'a-offer'), 'agent-identity')).result;
    assert.equal(ao.scope_digest, digest('scope', ao.immutable_scope));
    const aDecision = { ...decision, offer_id: ao.offer_id, scope_digest: ao.scope_digest, decision_ref: 'a-approve' };
    await command({ kind: 'admission_decision', payload: aDecision });
    await wire(request('offer.decide', aDecision, 'a-approve'), 'player-fixture');
    const ai = (await wire(request('invitation.redeem', { offer_id: ao.offer_id, join_intent: { scope_digest: ao.scope_digest,
      selected_device: 'device-a', presentation_observation: observation } }, 'a-redeem'), 'agent-identity')).result;
    const join = request('session.join', { invitation_id: ai.invitation_id, join_intent: ai.join_intent }, 'a-join');
    assert.equal((await wire(join, ai.invitation_credential)).result.status, 'join_pending');
    const resolve = request('asset.resolve', { session_id: 's1', manifest: rootAsset.manifest, scope_digest: ao.scope_digest }, 'a-resolve');
    return { join, invitation: ai, resolve, scope: ao.scope_digest };
  }
  const goodAssets = await bootAssets(false);
  assert.equal((await command({ kind: 'admission_finish' })).session.ready, false);
  const changedManifest = structuredClone(goodAssets.resolve);
  changedManifest.request_id = 'a-manifest-type-change';
  changedManifest.payload.manifest.compatibility.properties.variant = true;
  const deniedManifest = await wire(changedManifest, 'resource-fixture');
  assert.equal(deniedManifest.error.code, 'permission_denied');
  assert.equal(deniedManifest.error.outcome, 'not_accepted');
  assert.deepEqual(await command({ kind: 'asset_observe' }), { cache_count: 0, fetch_hops: 0, parse_calls: 0, session_state: 'active' });
  assert.equal((await wire(goodAssets.resolve, 'resource-fixture', { fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.deepEqual(await command({ kind: 'asset_observe' }), { cache_count: 0, fetch_hops: 2, parse_calls: 2, session_state: 'active' });
  assert.equal((await wire(goodAssets.resolve, 'resource-fixture', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  const assetReceipt = (await wire(goodAssets.resolve, 'resource-fixture')).result;
  assert.equal(assetReceipt.content_digest, rootAsset.manifest.content_digest);
  assert.equal(assetReceipt.parser_revision, 'fixture-parser-1'); assert.equal(assetReceipt.policy_revision, 'fixture-policy-1');
  assert.deepEqual((await wire({ ...goodAssets.resolve, request_id: 'a-cache-hit' }, 'resource-fixture')).result, assetReceipt);
  const successfulAssets = await command({ kind: 'asset_observe' });
  assert.deepEqual(successfulAssets, { cache_count: 2, fetch_hops: 4, parse_calls: 4, session_state: 'active' });
  const aProof = await command({ kind: 'presentation_proof', job_id: 'admission-s1' });
  await wire(request('presentation.acquire', { session_id: 's1', generation: 1, device_id: 'device-a',
    terms: { mode: 'hide_desktop', device_id: 'device-a' }, scope_digest: goodAssets.scope, ...aProof }, 'admission-s1'), 'presentation-fixture');
  assert.equal((await command({ kind: 'admission_finish' })).session.ready, true);
  assert.equal((await wire(goodAssets.join, goodAssets.invitation.invitation_credential)).result.status, 'ready');
  const badAssets = await bootAssets(true);
  const failedAsset = await wire(badAssets.resolve, 'resource-fixture');
  assert.equal(failedAsset.error.code, 'operation_failed'); assert.equal(failedAsset.error.outcome, 'accepted');
  assert.deepEqual(await wire(badAssets.resolve, 'resource-fixture'), failedAsset);
  const failedAssets = await command({ kind: 'asset_observe' });
  assert.deepEqual(failedAssets, { cache_count: 0, fetch_hops: 2, parse_calls: 1, session_state: 'closed' });
  const failedStatus = (await wire(request('operation.get', { operation: 'asset.resolve', original_request_id: 'a-resolve' }, 'a-status'), 'player-fixture')).result;
  assert.equal(failedStatus.state, 'failed'); assert.equal(failedStatus.error.outcome, 'accepted');
  assert.equal((await wire(badAssets.join, badAssets.invitation.invitation_credential)).result.status, 'completed_without_secret');

  // 启动许可使用独立可信交互夹具；wire 只能引用登记 ID，不能提交程序路径或命令。
  async function bootLaunch(outcome = null) {
    const registration = await command({ kind: 'launch_start', outcome });
    const ld = (await wire(request('describe', { instance }, 'l-describe'), 'player-fixture')).result;
    const lo = (await wire(request('offer.create', { entry: 'game', descriptor_id: ld.descriptor_id, expected_descriptor_revision: ld.revision,
      requested: { ...requested, supported_features: ld.supported_features, limits: ld.limits, ledger_durability: 'volatile' } }, 'l-offer'), 'player-fixture')).result;
    assert.equal(lo.launch_required, true);
    assert.equal(lo.scope_digest, digest('scope', lo.immutable_scope));
    const launchDecision = { ...decision, offer_id: lo.offer_id, scope_digest: lo.scope_digest, decision_ref: 'l-approve', launch_permission: true };
    await command({ kind: 'admission_decision', payload: launchDecision });
    await wire(request('offer.decide', launchDecision, 'l-approve'), 'player-fixture');
    const launch = request('launch.request', { offer_id: lo.offer_id, application_registration: registration.application_registration,
      launch_permission_ref: launchDecision.decision_ref }, 'l-launch');
    const poll = request('operation.get', { operation: 'launch.request', original_request_id: 'l-launch' }, 'l-status');
    const invite = request('invitation.redeem', { offer_id: lo.offer_id, join_intent: { scope_digest: lo.scope_digest } }, 'l-invite');
    return { launch, poll, invite };
  }
  const launched = await bootLaunch();
  assert.equal((await wire(launched.launch, 'player-fixture', { fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.deepEqual(await command({ kind: 'launch_observe' }), { start_calls: 0, effects: 0, has_session: false, grants: { 'grant-1': 'active' } });
  assert.equal((await wire(launched.launch, 'player-fixture', { fault: 'after_effect' })).fixture_fault, 'after_effect');
  await command({ kind: 'control_restart' });
  assert.equal((await wire(launched.poll, 'player-fixture')).result.state, 'done');
  assert.deepEqual((await wire(launched.launch, 'player-fixture')).result, { status: 'started' });
  assert.equal((await wire({ ...launched.launch, request_id: 'l-another-id' }, 'player-fixture')).error.code, 'id_conflict');
  const launchBeforeJoin = await command({ kind: 'launch_observe' });
  assert.deepEqual(launchBeforeJoin, { start_calls: 1, effects: 1, has_session: false, grants: { 'grant-1': 'active' } });
  const launchInvitation = (await wire(launched.invite, 'agent-identity')).result;
  const launchJoin = request('session.join', { invitation_id: launchInvitation.invitation_id, join_intent: launchInvitation.join_intent }, 'l-join');
  assert.equal((await wire(launchJoin, launchInvitation.invitation_credential)).result.status, 'join_pending');
  assert.equal((await command({ kind: 'admission_finish' })).session.ready, true);
  const launchDelivery = (await wire(launchJoin, launchInvitation.invitation_credential)).result;
  assert.equal(launchDelivery.status, 'ready');
  assert.equal((await wire(request('chat.send', envelope('l-chat', 'chat.message', agent,
    { channel: 'private', text: '启动后控制凭据可实际发送', source_refs: [], provenance: [] }), 'l-chat'), launchDelivery.control_credential)).result.duplicate, false);

  const uncertainLaunch = await bootLaunch('unknown_after_effect');
  const uncertainLaunchReply = await wire(uncertainLaunch.launch, 'player-fixture');
  assert.equal(uncertainLaunchReply.error.outcome, 'unknown');
  assert.deepEqual(await wire(uncertainLaunch.launch, 'player-fixture'), uncertainLaunchReply);
  assert.equal((await wire(uncertainLaunch.poll, 'player-fixture')).result.state, 'pending');
  assert.equal((await wire(uncertainLaunch.invite, 'agent-identity')).error.code, 'temporarily_unavailable');
  assert.equal((await command({ kind: 'launch_verify_existing', launch_permission_ref: 'l-approve' })).verified, true);
  assert.equal((await wire(uncertainLaunch.poll, 'player-fixture')).result.state, 'done');
  assert.equal((await wire(uncertainLaunch.launch, 'player-fixture')).result.status, 'started');
  const launchRecovered = await command({ kind: 'launch_observe' });
  assert.deepEqual(launchRecovered, { start_calls: 1, effects: 1, has_session: false, grants: { 'grant-1': 'active' } });

  const refusedLaunch = await bootLaunch('failed');
  const refusedLaunchReply = await wire(refusedLaunch.launch, 'player-fixture');
  assert.equal(refusedLaunchReply.error.code, 'launch_failed'); assert.equal(refusedLaunchReply.error.outcome, 'accepted');
  assert.deepEqual(await wire(refusedLaunch.launch, 'player-fixture'), refusedLaunchReply);
  assert.equal((await wire(refusedLaunch.poll, 'player-fixture')).result.state, 'failed');
  const launchFailed = await command({ kind: 'launch_observe' });
  assert.deepEqual(launchFailed, { start_calls: 1, effects: 0, has_session: false, grants: { 'grant-1': 'revoked' } });

  // 隐私 lane 不复用玩家/伙伴会话凭据；客户端只能提交来源引用，不能自报删除完成。
  function privacyReceipt(value, status) {
    assert.equal(value.privacy_request_id, 'privacy-1'); assert.equal(value.status, status);
    assert.deepEqual(value.controlled_scope, ['private-source']);
    assert.equal(Object.hasOwn(value, 'poll_after_ms'), status === 'pending');
    assert.equal(Object.hasOwn(value, 'exceptions'), status !== 'pending');
    if (status === 'pending') assert.ok(Number.isSafeInteger(value.poll_after_ms) && value.poll_after_ms > 0 && value.poll_after_ms <= 60000);
    return value;
  }
  const privacyDelete = request('privacy.request', { source_refs: ['private-source'], desired_action: 'delete_owned_copies' }, 'p-delete');
  const privacyPoll = request('privacy.receipt', { privacy_request_id: 'privacy-1' }, 'p-poll');
  await command({ kind: 'privacy_start', outcome: 'pending', retained: true });
  assert.equal((await wire(privacyDelete, 'player-fixture')).error.code, 'permission_denied');
  assert.equal((await wire(privacyDelete, 'other-subject')).error.code, 'permission_denied');
  assert.equal((await wire({ ...privacyDelete, payload: { ...privacyDelete.payload, source_refs: ['missing'] } }, 'subject-fixture')).error.code, 'permission_denied');
  assert.equal((await wire(privacyDelete, 'subject-fixture', { fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.equal((await command({ kind: 'privacy_observe' })).cutoffs, 0);
  assert.equal((await wire(privacyDelete, 'subject-fixture', { fault: 'after_accept' })).fixture_fault, 'after_accept');
  privacyReceipt((await wire(privacyPoll, 'subject-fixture')).result, 'pending');
  assert.equal((await command({ kind: 'privacy_observe' })).apply_calls, 0);
  privacyReceipt((await wire(privacyDelete, 'subject-fixture')).result, 'pending');
  await command({ kind: 'privacy_complete', privacy_request_id: 'privacy-1' });
  assert.equal((await wire(privacyPoll, 'subject-fixture', { fault: 'before_result_commit' })).fixture_fault, 'before_result_commit');
  const privatePartial = privacyReceipt((await wire(privacyPoll, 'subject-fixture')).result, 'partial');
  assert.deepEqual(privatePartial.exceptions, [{ source_id: 'private-source', reason: 'legal_hold', retain_until: 5000 }]);
  assert.deepEqual((await wire(privacyDelete, 'subject-fixture')).result, privatePartial);
  assert.equal((await wire(privacyPoll, 'other-subject')).error.code, 'permission_denied');
  assert.equal((await wire({ ...privacyDelete, payload: { ...privacyDelete.payload, desired_action: 'stop_disclosure' } }, 'subject-fixture')).error.code, 'id_conflict');
  const privacyPartialEffects = await command({ kind: 'privacy_observe' });
  assert.deepEqual(privacyPartialEffects, { apply_calls: 1, effects: 2, requests: 1, cutoffs: 1,
    copies: { primary: 'deleted', backup: 'deleted', held: 'present' } });

  await command({ kind: 'privacy_start' });
  assert.equal((await wire(privacyDelete, 'subject-fixture', { fault: 'after_effect' })).fixture_fault, 'after_effect');
  await command({ kind: 'control_restart' });
  const privateDone = privacyReceipt((await wire(privacyPoll, 'subject-fixture')).result, 'done');
  assert.deepEqual(privateDone.exceptions, []);
  assert.deepEqual((await wire(privacyDelete, 'subject-fixture')).result, privateDone);
  const privacyRecovered = await command({ kind: 'privacy_observe' });
  assert.equal(privacyRecovered.apply_calls, 1); assert.equal(privacyRecovered.effects, 2);

  await command({ kind: 'privacy_start' });
  assert.equal((await wire(privacyDelete, 'subject-fixture', { fault: 'after_dispatch' })).fixture_fault, 'after_dispatch');
  privacyReceipt((await wire(privacyPoll, 'subject-fixture')).result, 'pending');
  privacyReceipt((await wire(privacyDelete, 'subject-fixture')).result, 'pending');
  assert.equal((await wire({ ...privacyDelete, request_id: 'p-bypass' }, 'subject-fixture')).error.code, 'temporarily_unavailable');
  const privacyDispatchGap = await command({ kind: 'privacy_observe' });
  assert.equal(privacyDispatchGap.apply_calls, 0); assert.equal(privacyDispatchGap.effects, 0);

  // 隐私 cutoff 接到既有 outbox 过滤：已接受的游戏副本是 outside_control，而非冒充已删除。
  await command({ kind: 'privacy_start' });
  const privacyDescriptor = (await wire(request('describe', { instance }, 'p-describe'), 'player-fixture')).result;
  const privacyOffer = (await wire(request('offer.create', { entry: 'game', descriptor_id: privacyDescriptor.descriptor_id, expected_descriptor_revision: privacyDescriptor.revision,
    requested: { ...requested, supported_features: privacyDescriptor.supported_features, limits: privacyDescriptor.limits } }, 'p-offer'), 'player-fixture')).result;
  const privacyDecision = { ...decision, offer_id: privacyOffer.offer_id, scope_digest: privacyOffer.scope_digest, decision_ref: 'p-approve' };
  await command({ kind: 'admission_decision', payload: privacyDecision });
  await wire(request('offer.decide', privacyDecision, 'p-approve'), 'player-fixture');
  const privacyInvitation = (await wire(request('invitation.redeem', { offer_id: privacyOffer.offer_id, join_intent: { scope_digest: privacyOffer.scope_digest } }, 'p-invite'), 'agent-identity')).result;
  const privacyJoin = request('session.join', { invitation_id: privacyInvitation.invitation_id, join_intent: privacyInvitation.join_intent }, 'p-join');
  await wire(privacyJoin, privacyInvitation.invitation_credential);
  await command({ kind: 'admission_finish' });
  const privacyControl = (await wire(privacyJoin, privacyInvitation.invitation_credential)).result.control_credential;
  const privacySource = { source_id: 'private-source', source_kind: 'player_report', source_principals: [player], original_disclosure_scope: [player, agent, game] };
  const privacyChat = request('chat.send', envelope('p-chat', 'chat.message', agent,
    { channel: 'private', text: '有明确来源的内存测试内容', source_refs: ['private-source'], provenance: [privacySource] }), 'p-chat');
  await wire(privacyChat, privacyControl);
  const privacyEvents = request('session.events', { session_id: 's1', cursor: start.cursor, page_size: 64 }, 'p-events');
  const privacyBefore = (await wire(privacyEvents, privacyControl)).result;
  assert.ok(privacyBefore.events.some(e => e.envelope.type === 'chat.message'));
  const privacyOutside = privacyReceipt((await wire(privacyDelete, 'subject-fixture')).result, 'partial');
  assert.deepEqual(privacyOutside.exceptions, [{ source_id: 'private-source', reason: 'outside_control' }]);
  const privacyAfter = (await wire(privacyEvents, privacyControl)).result;
  assert.ok(!privacyAfter.events.some(e => e.envelope.type === 'chat.message'));
  assert.deepEqual(privacyAfter.next_cursor, privacyBefore.next_cursor);
  assert.equal((await wire({ ...privacyChat, request_id: 'p-chat-late', payload: { ...privacyChat.payload, id: 'p-chat-late' } }, privacyControl)).error.code, 'permission_denied');
  await wire(request('session.close', { session_id: 's1', reason: 'left' }, 'p-close'), 'player-fixture');
  assert.deepEqual((await wire(privacyPoll, 'subject-fixture')).result, privacyOutside);

  // 玩家转发走 GameAuthority 管理凭据和独立席位证明，不用伙伴 token 伪造 sender。
  await command({ kind: 'forward_start' });
  const bob = principal('bob', 'player');
  const forwardDescriptor = (await wire(request('describe', { instance }, 'f-describe'), 'player-fixture')).result;
  const forwardOffer = (await wire(request('offer.create', { entry: 'game', descriptor_id: forwardDescriptor.descriptor_id,
    expected_descriptor_revision: forwardDescriptor.revision,
    requested: { ...requested, supported_features: forwardDescriptor.supported_features, limits: forwardDescriptor.limits,
      ledger_durability: 'durable', audiences: [player, agent, bob] } }, 'f-offer'), 'player-fixture')).result;
  assert.ok(forwardOffer.immutable_scope.audiences.some(p => p.subject === 'bob'));
  const forwardDecision = { ...decision, offer_id: forwardOffer.offer_id, scope_digest: forwardOffer.scope_digest, decision_ref: 'f-approve' };
  await command({ kind: 'admission_decision', payload: forwardDecision });
  await wire(request('offer.decide', forwardDecision, 'f-approve'), 'player-fixture');
  const forwardInvitation = (await wire(request('invitation.redeem', { offer_id: forwardOffer.offer_id,
    join_intent: { scope_digest: forwardOffer.scope_digest } }, 'f-invite'), 'agent-identity')).result;
  const forwardJoin = request('session.join', { invitation_id: forwardInvitation.invitation_id, join_intent: forwardInvitation.join_intent }, 'f-join');
  await wire(forwardJoin, forwardInvitation.invitation_credential);
  await command({ kind: 'admission_finish' });
  const forwardDelivery = (await wire(forwardJoin, forwardInvitation.invitation_credential)).result;
  const forwardControl = forwardDelivery.control_credential;
  await command({ kind: 'forward_seat', player: 'alice', proof_ref: 'seat-alice' });
  const forwarded = request('player_chat.forward', { seat_proof_ref: 'seat-alice', envelope: envelope('forward-1', 'chat.message', player,
    { channel: 'private', text: '玩家的中文消息 🗝 <script>仅文本</script>', source_refs: [], provenance: [] }) }, 'f-send');
  assert.equal((await wire(forwarded, forwardControl)).error.code, 'permission_denied');
  assert.equal((await wire(forwarded, 'player-fixture')).error.code, 'permission_denied');
  assert.equal((await wire({ ...forwarded, payload: { ...forwarded.payload, seat_proof_ref: 'unverified' } }, 'game-fixture')).error.code, 'permission_denied');
  assert.equal((await wire({ ...forwarded, payload: { ...forwarded.payload, envelope: { ...forwarded.payload.envelope, sender: agent } } }, 'game-fixture')).error.code, 'permission_denied');
  assert.equal((await wire(forwarded, 'game-fixture', { fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.equal((await command({ kind: 'forward_observe' })).chat_events, 0);
  assert.equal((await wire(forwarded, 'game-fixture', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  const forwardReceipt = (await wire({ ...forwarded, request_id: 'f-retry' }, 'game-fixture')).result;
  assert.equal(forwardReceipt.duplicate, true);
  assert.equal(forwardReceipt.record_digest, digest('message', forwarded.payload.envelope));
  assert.deepEqual(await command({ kind: 'forward_observe' }), { chat_events: 1, receipts: 1, lease_deadline: forwardDelivery.session.lease_deadline });
  const forwardChanged = structuredClone(forwarded); forwardChanged.payload.envelope.payload.text = '改变正文';
  assert.equal((await wire(forwardChanged, 'game-fixture')).error.code, 'id_conflict');

  async function forwardMembers(verified_members, expected_revision) {
    const payload = { instance, expected_revision, verified_members, membership_proof_ref: `f-members-${expected_revision}` };
    await command({ kind: 'membership_proof', payload });
    assert.equal((await wire(request('membership.replace', payload, `f-members-${expected_revision}`), 'game-fixture')).result.revision, expected_revision + 1);
  }
  await forwardMembers([player, agent, bob], 1);
  assert.equal((await wire(forwarded, 'game-fixture')).error.code, 'permission_denied');
  await command({ kind: 'forward_seat', player: 'alice', proof_ref: 'seat-alice-2' });
  forwarded.payload.seat_proof_ref = 'seat-alice-2';
  assert.equal((await wire(forwarded, 'game-fixture')).result.duplicate, true);
  await command({ kind: 'forward_seat', player: 'bob', proof_ref: 'seat-bob' });
  const forwardedTeam = request('player_chat.forward', { seat_proof_ref: 'seat-bob', envelope: {
    ...envelope('forward-1', 'chat.message', bob, { channel: 'team', text: 'Bob 的队伍消息', source_refs: [], provenance: [] }),
    expected_membership_revision: 2 } }, 'f-team');
  const staleTeam = structuredClone(forwardedTeam); staleTeam.payload.envelope.expected_membership_revision = 1;
  assert.equal((await wire(staleTeam, 'game-fixture')).error.code, 'membership_conflict');
  assert.equal((await wire(forwardedTeam, 'game-fixture')).result.duplicate, false);
  await forwardMembers([player, agent], 2);
  await forwardMembers([player, agent, bob], 3);
  assert.equal((await wire(forwardedTeam, 'game-fixture')).error.code, 'permission_denied');
  const rejoinedSeat = await command({ kind: 'forward_seat', player: 'bob', proof_ref: 'seat-bob-2' });
  assert.equal(rejoinedSeat.membership_generation, 2);
  forwardedTeam.payload.seat_proof_ref = 'seat-bob-2';
  assert.equal((await wire(forwardedTeam, 'game-fixture')).result.duplicate, true);
  const currentTeam = structuredClone(forwardedTeam);
  currentTeam.payload.envelope.id = 'forward-new'; currentTeam.payload.envelope.expected_membership_revision = 4;
  assert.equal((await wire(currentTeam, 'game-fixture')).result.duplicate, false);

  await command({ kind: 'forward_seat', player: 'alice', proof_ref: 'seat-alice-4' });
  forwarded.payload.seat_proof_ref = 'seat-alice-4';
  const forwardSource = request('player_chat.forward', { seat_proof_ref: 'seat-alice-4', envelope: envelope('forward-source', 'chat.message', player,
    { channel: 'private', text: '有来源的玩家消息', source_refs: ['private-source'], provenance: [privacySource] }) }, 'f-source');
  await wire(forwardSource, 'game-fixture');
  const forwardEvents = request('session.events', { session_id: 's1', cursor: start.cursor, page_size: 64 }, 'f-events');
  const forwardBefore = (await wire(forwardEvents, forwardControl)).result;
  assert.equal(forwardBefore.events.filter(e => e.envelope.type === 'chat.message').length, 4);
  assert.ok(forwardBefore.events.some(e => e.envelope.type === 'chat.message' && e.envelope.sender.subject === 'bob'));
  const forwardPrivacy = privacyReceipt((await wire(privacyDelete, 'subject-fixture')).result, 'partial');
  assert.deepEqual(forwardPrivacy.exceptions, [{ source_id: 'private-source', reason: 'outside_control' }]);
  const forwardAfter = (await wire(forwardEvents, forwardControl)).result;
  assert.equal(forwardBefore.events.length - forwardAfter.events.length, 1);
  assert.deepEqual(forwardBefore.next_cursor, forwardAfter.next_cursor);
  forwardSource.payload.envelope.id = 'forward-source-late';
  assert.equal((await wire(forwardSource, 'game-fixture')).error.code, 'permission_denied');
  await command({ kind: 'control_restart' });
  assert.equal((await wire(forwarded, 'game-fixture')).result.duplicate, true);
  const forwardRecovered = await command({ kind: 'forward_observe' });
  assert.equal(forwardRecovered.chat_events, 4); assert.equal(forwardRecovered.receipts, 4);
  await wire(request('session.close', { session_id: 's1', reason: 'left' }, 'f-close'), 'player-fixture');
  // 现有 close 同时撤销 Grant；写入检查先报告该事实，不把拒绝解释为已接受。
  const closedForward = (await wire(forwarded, 'game-fixture')).error;
  assert.equal(closedForward.code, 'grant_revoked'); assert.equal(closedForward.outcome, 'not_accepted');

  // Relay 与游戏是两个 authority；以下配对交付/派发命令仅为可信夹具端口，不是新公开操作。
  await command({ kind: 'relay_start' });
  let rNow = 1000, rIndex = 0;
  const rBootstrap = (await wire(request('describe', { instance }, 'r-bootstrap'), 'agent-identity')).result;
  const rRegistration = request('relay.register', { instance, relay_identity: principal('relay', 'service'),
    relay_origin: 'https://relay.fixture.invalid', agent_principals: [agent], control_principals: [player],
    registration_expiry: 90000, pairing_proof_ref: 'pairing-fixture', limits: rBootstrap.limits }, 'r-register');
  const rBadRegistration = structuredClone(rRegistration);
  rBadRegistration.payload.relay_origin = 'https://unapproved.invalid';
  assert.equal((await wire(rBadRegistration, 'relay-player-identity')).error.code, 'permission_denied');
  assert.equal((await wire(rRegistration, 'relay-player-identity', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  const rRegistered = (await wire(rRegistration, 'relay-player-identity')).result;
  assert.deepEqual(Object.keys(rRegistered).sort(), ['mailbox_id', 'registration_expiry', 'route_revision']);
  const rMailbox = rRegistered.mailbox_id, rTokens = {};
  for (const role of ['agent', 'player', 'game']) {
    rTokens[role] = (await command({ kind: 'relay_credential', mailbox_id: rMailbox, recipient: `relay-${role}-identity` })).credential;
  }
  assert.equal(new Set(Object.values(rTokens)).size, 3);
  const rPayload = (inner, id, proof = 'inner-agent-fixture', deadline = 80000) => ({ mailbox_id: rMailbox,
    call: { relay_request_id: id, operation_request: plain(inner), inner_auth_proof: proof, deadline, route_revision: 1 } });
  const rCall = (payload, role = 'agent', options = {}) => wire(request('relay.call', payload, `outer-${payload.call.relay_request_id}`),
    rTokens[role], { now: rNow, ...options });
  const rPullRequest = (nonce, maximum = 1) => request('relay.pull', { mailbox_id: rMailbox, pull_nonce: nonce, maximum_items: maximum }, nonce);
  async function rPull(nonce, options = {}) {
    return wire(rPullRequest(nonce), rTokens.game, { now: rNow, ...options });
  }
  async function rDispatch(claim, options = {}) {
    const result = await command({ kind: 'relay_dispatch', raw: canonical(claim).toString('base64'), credential: rTokens.game, now: rNow, ...options });
    if (result.fixture_fault || result.fixture_rejected) return result;
    const bytes = Buffer.from(result.reply, 'base64'), reply = plain(decode(bytes));
    assert.ok(bytes.equals(canonical(reply))); assert.equal(reply.request_id, claim.call.operation_request.request_id);
    assert.notEqual(Object.hasOwn(reply, 'result'), Object.hasOwn(reply, 'error'));
    return reply;
  }
  const rReply = (claim, reply, id, options = {}) => wire(request('relay.reply', { mailbox_id: rMailbox,
    claim_id: claim.claim_id, reply }, id), rTokens.game, { now: rNow, ...options });
  async function rExchange(inner, role = 'agent', proof = 'inner-agent-fixture') {
    const id = `r-exchange-${++rIndex}`, payload = rPayload(inner, id, proof);
    assert.equal((await rCall(payload, role)).result.state, 'queued');
    const claim = (await rPull(`pull-${id}`)).result.claims[0];
    assert.deepEqual(claim.call.operation_request, inner); assert.equal(claim.game_identity.subject, game.subject);
    const reply = await rDispatch(claim);
    assert.deepEqual((await rReply(claim, reply, `reply-${id}`)).result, { status: 'accepted' });
    assert.deepEqual((await rCall(payload, role)).result.reply, reply);
    return { reply, payload, claim };
  }
  const rD = (await rExchange(request('describe', { instance }, 'r-describe'))).reply.result;
  assert.equal(rD.bindings[0].kind, 'outbound-relay'); assert.equal(rD.privacy_model.relay_plaintext, true);
  assert.ok(rD.privacy_model.visible_to.some(p => p.subject === 'relay'));
  assert.equal((await rCall(rPayload(request('describe', { instance }, 'wrong-role'), 'wrong-role'), 'game')).error.code, 'permission_denied');
  assert.equal((await wire(rPullRequest('wrong-puller'), rTokens.agent)).error.code, 'permission_denied');
  const rForbidden = request('action.claim', { session_id: 's1', action_id: 'a1', worker: principal('worker-1', 'service') }, 'remote-management');
  assert.equal((await rCall(rPayload(rForbidden, 'remote-management'))).error.code, 'invalid_message');
  assert.equal((await rCall(rPayload(request('privacy.receipt', { privacy_request_id: 'private' }, 'remote-privacy'), 'remote-privacy'))).error.code, 'invalid_message');
  const rRequested = { ...requested, bindings: rD.bindings, privacy_model: rD.privacy_model,
    supported_features: rD.supported_features, limits: rD.limits };
  const rOffer = (await rExchange(request('offer.create', { entry: 'companion', descriptor_id: rD.descriptor_id,
    expected_descriptor_revision: rD.revision, requested: rRequested }, 'r-offer'))).reply.result;
  assert.equal(rOffer.scope_digest, digest('scope', rOffer.immutable_scope));
  const rDecision = { ...decision, offer_id: rOffer.offer_id, scope_digest: rOffer.scope_digest, decision_ref: 'r-decision' };
  const rDecideRequest = request('offer.decide', rDecision, 'r-decide');
  assert.equal((await rCall(rPayload(rDecideRequest, 'cross-lane', 'inner-player-fixture'))).error.code, 'permission_denied');
  assert.equal((await rExchange(rDecideRequest, 'player', 'inner-player-fixture')).reply.error.code, 'consent_required');
  await command({ kind: 'admission_decision', payload: rDecision });
  assert.equal((await rExchange(rDecideRequest, 'player', 'inner-player-fixture')).reply.result.state, 'approved');
  const rInvitation = (await rExchange(request('invitation.redeem', { offer_id: rOffer.offer_id,
    join_intent: { scope_digest: rOffer.scope_digest } }, 'r-redeem'))).reply.result;
  await command({ kind: 'relay_inner_proof', proof_ref: 'r-inner-invitation', credential: rInvitation.invitation_credential });
  const rJoin = request('session.join', { invitation_id: rInvitation.invitation_id, join_intent: rInvitation.join_intent }, 'r-join');
  const rPendingJoin = await rExchange(rJoin, 'agent', 'r-inner-invitation');
  assert.equal(rPendingJoin.reply.result.status, 'join_pending');
  assert.equal((await command({ kind: 'admission_finish' })).session.ready, true);
  assert.equal((await rCall(rPendingJoin.payload)).error.code, 'request_gone'); // 旧缓存不能升级为新秘密。
  const rReady = (await rExchange(rJoin, 'agent', 'r-inner-invitation')).reply.result;
  assert.equal(rReady.session.ready, true);
  await command({ kind: 'relay_inner_proof', proof_ref: 'r-inner-control', credential: rReady.control_credential });
  await command({ kind: 'relay_inner_proof', proof_ref: 'r-inner-results', credential: rReady.result_read_handle });

  const rChat = request('chat.send', envelope('relay-message', 'chat.message', agent,
    { channel: 'private', text: '经过中继，消息仍只接受一次 🗝', source_refs: [], provenance: [] }), 'r-chat');
  const rChatCall = rPayload(rChat, 'r-chat-call', 'r-inner-control');
  assert.equal((await rCall(rChatCall, 'agent', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  assert.equal((await rCall(rChatCall)).result.state, 'queued');
  const rExtended = structuredClone(rChatCall); rExtended.call.deadline = 200000;
  assert.equal((await rCall(rExtended)).result.state, 'queued');
  assert.equal((await rPull('r-chat-pull', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  const rChatClaim = (await rPull('r-chat-pull')).result.claims[0];
  assert.equal(rChatClaim.call.deadline, 31000);
  assert.deepEqual((await rPull('r-chat-pull')).result.claims, [rChatClaim]);
  assert.deepEqual((await rPull('r-chat-next')).result.claims, []);
  const rBeforeGap = await command({ kind: 'relay_observe' });
  assert.equal((await rDispatch(rChatClaim, { fault: 'after_game' })).fixture_fault, 'after_game');
  await command({ kind: 'relay_restart' });
  const rUnknown = await rDispatch(rChatClaim);
  assert.equal(rUnknown.error.code, 'outcome_unknown'); assert.equal(rUnknown.error.outcome, 'unknown');
  const rAfterGap = await command({ kind: 'relay_observe' });
  assert.equal(rAfterGap.dispatch_calls, rBeforeGap.dispatch_calls + 1); assert.equal(rAfterGap.chat_events, 1);
  assert.equal((await rReply(rChatClaim, rUnknown, 'r-chat-reply', { fault: 'after_commit' })).fixture_fault, 'after_commit');
  assert.deepEqual((await rReply(rChatClaim, rUnknown, 'r-chat-reply')).result, { status: 'accepted' });
  assert.equal((await rCall(rChatCall)).result.reply.error.outcome, 'unknown');
  const rDuplicate = (await rExchange(rChat, 'agent', 'r-inner-control')).reply.result;
  assert.equal(rDuplicate.duplicate, true); assert.equal(rDuplicate.record_digest, digest('message', rChat.payload));

  const rAction = request('action.request', { ...envelope('relay-action', 'action.request', agent,
    { action: 'find-key', arguments: { room: 'hall' }, deadline: 30000 }), expected_capabilities_revision: 1 }, 'r-action');
  assert.equal((await rExchange(rAction, 'agent', 'r-inner-control')).reply.result.record_digest, digest('message', rAction.payload));
  // 执行器始终留在游戏管理入口，不把它包装进 relay.call。
  const rTicket = (await wire(request('action.claim', { session_id: 's1', action_id: 'relay-action', worker: principal('worker-1', 'service') },
    'r-local-claim'), 'worker-1-fixture')).result.ticket;
  for (const step of [1, 2]) assert.equal((await command({ kind: 'effect', ticket: rTicket, step })).world_effects, step);
  const rFact = { state: 'succeeded', effect: 'committed', result: { item: 'gold-key' },
    steps: [1, 2].map(step => ({ step, effect: 'committed', evidence_ref: `${rTicket.proof_ref}-step-${step}` })) };
  await wire(request('action.commit_result', { ticket: rTicket, fact: rFact }, 'r-local-result'), 'worker-1-fixture');
  const rQuery = request('action.query', { session_id: 's1', action_id: 'relay-action' }, 'r-query');
  assert.deepEqual((await rExchange(rQuery, 'agent', 'r-inner-results')).reply.result.known_result, { item: 'gold-key' });
  const rBeforeExpiry = await command({ kind: 'relay_observe' });

  const rExpClaimed = rPayload(request('describe', { instance }, 'r-exp-claimed'), 'r-exp-claimed', 'inner-agent-fixture', 1001);
  await rCall(rExpClaimed);
  const rExpiredClaim = (await rPull('r-exp-pull')).result.claims[0];
  const rExpQueued = rPayload(request('describe', { instance }, 'r-exp-queued'), 'r-exp-queued', 'inner-agent-fixture', 1001);
  await rCall(rExpQueued);
  rNow = 1001;
  const rClaimTimeout = (await rCall(rExpClaimed)).error, rQueueTimeout = (await rCall(rExpQueued)).error;
  assert.equal(rClaimTimeout.code, 'transport_timeout'); assert.equal(rClaimTimeout.outcome, 'unknown');
  assert.equal(rQueueTimeout.code, 'relay_not_dispatched'); assert.equal(rQueueTimeout.outcome, 'not_accepted');
  assert.equal((await rReply(rExpiredClaim, { request_id: 'r-exp-claimed', result: rD }, 'r-too-late')).error.code, 'request_gone');
  const rHoldClaimed = rPayload(request('describe', { instance }, 'r-hold-claimed'), 'r-hold-claimed');
  await rCall(rHoldClaimed); await rPull('r-hold-pull');
  const rHoldQueued = rPayload(request('describe', { instance }, 'r-hold-queued'), 'r-hold-queued');
  await rCall(rHoldQueued);
  const rRevoke = request('relay.revoke', { mailbox_id: rMailbox, expected_route_revision: 1 }, 'r-revoke');
  assert.equal((await wire(rRevoke, 'relay-player-identity', { now: rNow, fault: 'before_commit' })).fixture_fault, 'before_commit');
  assert.deepEqual((await command({ kind: 'relay_observe' })).route_revisions, [1]);
  assert.equal((await wire(rRevoke, 'relay-player-identity', { now: rNow, fault: 'after_commit' })).fixture_fault, 'after_commit');
  assert.equal((await wire(rRevoke, 'relay-player-identity', { now: rNow })).result.route_revision, 2);
  assert.equal((await rCall(rHoldClaimed)).error.code, 'unauthenticated');
  const rFreshClaimed = (await wire(request('relay.call', rHoldClaimed, 'r-fresh-claimed'), 'relay-agent-identity', { now: rNow })).error;
  const rFreshQueued = (await wire(request('relay.call', rHoldQueued, 'r-fresh-queued'), 'relay-agent-identity', { now: rNow })).error;
  assert.equal(rFreshClaimed.code, 'request_gone'); assert.equal(rFreshClaimed.outcome, 'unknown');
  assert.equal(rFreshQueued.code, 'relay_not_dispatched'); assert.equal(rFreshQueued.outcome, 'not_accepted');
  assert.equal((await command({ kind: 'relay_credential', mailbox_id: rMailbox, recipient: 'relay-agent-identity', now: rNow })).fixture_rejected, 'request_gone');
  await command({ kind: 'relay_restart', now: rNow });
  const rFinal = await command({ kind: 'relay_observe' });
  assert.deepEqual(rFinal.route_revisions, [2]); assert.equal(rFinal.world_effects, 2); assert.equal(rFinal.chat_events, 1);
  assert.equal(rFinal.lease_deadline, rBeforeExpiry.lease_deadline);
  assert.deepEqual((await wire(rQuery, rReady.result_read_handle, { now: rNow })).result.known_result, { item: 'gold-key' });
  console.log(JSON.stringify({ passed: true, node: process.version, codec_cases: codecCases,
    fixture_commands: calls, wire_calls: wireCalls, wire_operations: [...operations].sort(),
    recovered_events: page.events.length, world_effects: 2, admission_ready_events: readyPage.events.length,
    control_events: controlPage.events.length, control_change_events: controlPage.events.filter(e => e.envelope.type === 'session.control_changed').length,
    mock_restart: true, presentation_events: pEvents.events.length, presentation_render_calls: pDeviceA.render_calls + pDeviceB.render_calls,
    minimal_core: true, minimal_core_chat_events: corePage.events.length,
    compacted_receipts: receiptCompaction.removed, post_compaction_world_effects: afterReceiptCompaction.world_effects,
    operation_status_effects: statusAfterQueries.world_effects, operation_status_partial: statusPartial.action.effect,
    operation_status_confirmations: statusAfterQueries.consumed_confirmations, operation_status_read_only: true,
    lifecycle_device_epoch: lRestart.observation.device_epoch, lifecycle_lease_revision: lAck.lease_revision,
    lifecycle_pending_releases: lRecovery.pending_releases, lifecycle_render_calls: lReleased.render_calls,
    asset_verified_entries: successfulAssets.cache_count, asset_failure_cache_entries: failedAssets.cache_count,
    launch_effects: launchBeforeJoin.effects, launch_recovered_effects: launchRecovered.effects,
    launch_failure_effects: launchFailed.effects,
    privacy_deleted_copies: privacyPartialEffects.effects, privacy_recovered_effects: privacyRecovered.effects,
    privacy_dispatch_gap_effects: privacyDispatchGap.effects, privacy_filtered_events: privacyBefore.events.length - privacyAfter.events.length,
    forward_accepted_messages: forwardRecovered.chat_events, forward_receipts: forwardRecovered.receipts,
    forward_rejoined_generation: rejoinedSeat.membership_generation, forward_filtered_events: forwardBefore.events.length - forwardAfter.events.length,
    relay_mailboxes: rFinal.mailboxes, relay_chat_events: rFinal.chat_events, relay_world_effects: rFinal.world_effects,
    relay_dispatch_gap_executions: rAfterGap.dispatch_calls - rBeforeGap.dispatch_calls,
    relay_closed_route_revision: rFinal.route_revisions[0], relay_terminal_records: rFinal.states,
    limitations: ['fixed enrollment/one action/two steps', 'three event reducers only', 'not full schema validation in JS',
      'same author, separate implementation; not third-party certification'] }));
} finally {
  clearTimeout(timeout);
  child.stdin.end(); child.kill();
}
