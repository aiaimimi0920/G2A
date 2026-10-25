// 独立构造 owner 域、目标键、组请求 ID 和 wire；不导入 Python 模型或 schema。
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { canonical, decode } from './codec_peer.mjs';

export async function runSharedFanoutCases(command) {
  let fixtureCalls = 0, wireCalls = 0, groupedAcks = 0, rebindings = 0, preservedEffects = 0, staleSnapshots = 0;
  const faults = ['before_commit', 'after_commit', 'lose_ack'];
  const hash = value => createHash('sha256').update(canonical(value)).digest('hex');
  const invoke = async (action, fields = {}) => {
    fixtureCalls++;
    return command({ kind: 'shared_fanout', action, ...fields });
  };
  const local = (owner, action, fields = {}) => invoke('local', { owner, command: { action, ...fields } });
  const request = (operation, payload, requestId) => ({ version: 'fixture-only', operation,
    request_id: requestId, payload, extensions: {} });
  const wire = async (owner, req, credential, sid) => {
    wireCalls++;
    const result = await local(owner, 'wire', { raw: canonical(req).toString('base64'), credential, session_id: sid });
    const raw = Buffer.from(result.reply, 'base64'), reply = JSON.parse(JSON.stringify(decode(raw)));
    assert.ok(raw.equals(canonical(reply))); assert.equal(reply.request_id, req.request_id);
    assert.ok(reply.result); assert.equal(Object.hasOwn(reply, 'error'), false);
    return reply.result;
  };
  const join = async (owner, sid) => {
    const invitation = await local(owner, 'issue', { session_id: sid });
    const req = request('session.join', { invitation_id: invitation.invitation_id, join_intent: invitation.join_intent }, 'join-' + sid);
    assert.equal((await wire(owner, req, invitation.invitation_credential)).status, 'join_pending');
    assert.equal((await local(owner, 'finish', { session_id: sid })).ready, true);
    return wire(owner, req, invitation.invitation_credential);
  };
  for (const fault of faults) {
    const description = await invoke('start');
    const left = await join('shared', 'left');
    await join('shared', 'right'); await join('other', 'left');
    const catalogue = await invoke('register'), targets = catalogue.targets;
    for (const [key, binding] of Object.entries(targets)) assert.equal(key, hash(binding));
    const rightKey = Object.keys(targets).find(key => targets[key].session_id === 'right');
    const ownerId = targets[rightKey].grant_owner_id;
    const leftKey = Object.keys(targets).find(key => targets[key].session_id === 'left' && targets[key].grant_owner_id === ownerId);
    const otherKey = Object.keys(targets).find(key => targets[key].grant_owner_id !== ownerId);
    assert.ok(leftKey && otherKey && rightKey);
    const groups = Object.fromEntries(Object.entries(targets).map(([key, binding]) => {
      const { session_id, ...domain } = binding;
      return [key, 'grant-' + hash(domain)];
    }));
    assert.equal(groups[leftKey], groups[rightKey]); assert.notEqual(groups[leftKey], groups[otherKey]);
    const raws = Object.fromEntries(Object.entries(targets).map(([key, binding]) => [key,
      request('permission.revoke', { object_type: 'grant', object_id: binding.grant_id, expected_revision: 1 },
        'fanout-' + hash([catalogue.coordinator_id, 'revoke', groups[key]]))]));
    assert.deepEqual(raws[leftKey], raws[rightKey]);
    const deliver = async (key, options = {}, req = raws[key]) => {
      wireCalls++;
      return invoke('deliver', { operation_id: 'revoke', target: key, raw: canonical(req).toString('base64'), ...options });
    };
    const pending = await invoke('begin', { operation_id: 'revoke', catalogue_revision: catalogue.revision,
      targets: Object.fromEntries(Object.keys(targets).map(key => [key, 1])) });
    assert.equal(Object.keys(pending.grant_groups).length, 2);
    assert.equal(pending.grant_groups[groups[leftKey]].impact, 'entire_grant');
    assert.deepEqual(pending.grant_groups[groups[leftKey]].members, [leftKey, rightKey].sort());
    const info = description.shared;
    await wire('shared', request('action.request', { version: 'fixture-only', session_id: 'left', id: 'a1', type: 'action.request',
      sender: info.agent, audience: [info.player], expected_capabilities_revision: 1, extensions: {},
      payload: { action: 'find-key', arguments: { room: 'hall' }, deadline: 30000 } }, 'action'), left.control_credential, 'left');
    const claim = await wire('shared', request('action.claim', { session_id: 'left', action_id: 'a1',
      worker: { issuer: 'fixture-enrollment', subject: 'worker-1', kind: 'service' } }, 'claim'), 'worker-1-fixture', 'left');
    await local('shared', 'execute', { session_id: 'left', operation: 'step', ticket: claim.ticket, step: 1 });
    assert.equal((await deliver(otherKey)).state, 'partial');
    const unknown = await deliver(leftKey, fault === 'lose_ack' ? { lose_ack: true } : { fault });
    assert.equal(unknown.state, 'partial'); assert.equal(unknown.targets[otherKey], 'acknowledged');
    assert.equal(unknown.targets[leftKey], 'unknown'); assert.equal(unknown.targets[rightKey], 'unknown');
    const observed = await invoke('observe');
    assert.equal(observed.other.grant_state, 'revoked');
    assert.equal(observed.shared.grant_state, fault === 'before_commit' ? 'active' : 'revoked');
    assert.deepEqual(await invoke('retire', { target: leftKey, catalogue_revision: catalogue.revision }), { fixture_rejected: 'not_drained' });
    await invoke('snapshot', { name: 'unknown' });
    assert.deepEqual(await local('shared', 'restart'), { restarted: true });
    assert.deepEqual(await deliver(rightKey), unknown, 'retired receiver cannot advance group knowledge');
    assert.deepEqual(await invoke('rebind', { target: rightKey }), { target: rightKey }); rebindings++;
    assert.deepEqual(await invoke('restart'), { restarted: true });
    const done = await deliver(rightKey);
    assert.equal(done.state, 'done'); assert.ok(Object.values(done.targets).every(value => value === 'acknowledged'));
    groupedAcks += 2;
    const committed = await invoke('observe');
    assert.equal(committed.shared.grant_revision, 2);
    assert.equal(committed.shared.sessions.left.world_effects, 1); preservedEffects++;
    assert.equal(committed.shared.sessions.left.state, 'closed'); assert.equal(committed.shared.sessions.right.state, 'closed');
    assert.deepEqual(await deliver(leftKey), done);
    assert.deepEqual(await invoke('observe'), committed);
    assert.equal((await wire('shared', request('action.query', { session_id: 'left', action_id: 'a1' }, 'query'),
      left.result_read_handle, 'left')).effect, 'partial');
    assert.equal((await invoke('retire', { target: leftKey, catalogue_revision: catalogue.revision })).state, 'retired');
    assert.deepEqual(await deliver(leftKey), done);
    const changed = structuredClone(raws[rightKey]); changed.payload.expected_revision = 2;
    assert.deepEqual(await deliver(rightKey, {}, changed), { fixture_rejected: 'id_conflict' });
    assert.deepEqual(await invoke('restart', { snapshot: 'unknown' }), { fixture_rejected: 'snapshot_mismatch' }); staleSnapshots++;
  }
  return { passed: true, scope: 'candidate-shared-grant-fanout', faults, completed: faults.length,
    wire_calls: wireCalls, fixture_calls: fixtureCalls, grouped_acks: groupedAcks, trusted_rebindings: rebindings,
    preserved_effects: preservedEffects, stale_snapshots_rejected: staleSnapshots,
    limitations: ['Grant-wide scope, not frozen session impact', 'trusted in-memory recovery chain, not network authentication'] };
}
