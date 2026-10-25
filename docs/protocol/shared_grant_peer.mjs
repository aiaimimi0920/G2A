// 独立手写共享 Grant 请求和响应断言，不导入 Python fixture/schema。
import assert from 'node:assert/strict';
import { canonical, decode } from './codec_peer.mjs';

export async function runSharedGrantCases(command) {
  let wireCalls = 0, fixtureCalls = 0, closedSessions = 0, redactedJoins = 0, snapshotsRejected = 0, preservedEffects = 0;
  const faults = ['before_commit', 'after_first_close', 'after_commit'];
  const invoke = async (action, fields = {}) => {
    fixtureCalls++;
    return command({ kind: 'shared_grant', action, ...fields });
  };
  const request = (operation, payload, requestId) => ({ version: 'fixture-only', operation,
    request_id: requestId, payload, extensions: {} });
  const wire = async (req, credential = 'player-fixture', options = {}) => {
    wireCalls++;
    const output = await invoke('wire', { raw: canonical(req).toString('base64'), credential, ...options });
    if (output.fixture_fault) return output;
    const raw = Buffer.from(output.reply, 'base64'), reply = JSON.parse(JSON.stringify(decode(raw)));
    assert.ok(raw.equals(canonical(reply))); assert.equal(reply.request_id, req.request_id);
    assert.notEqual(Object.hasOwn(reply, 'result'), Object.hasOwn(reply, 'error'));
    return reply;
  };
  const revoke = (kind, id, rid = 'grant-revoke', revision = 1) => request('permission.revoke',
    { object_type: kind, object_id: id, expected_revision: revision }, rid);
  const join = async sid => {
    const invitation = await invoke('issue', { session_id: sid });
    const req = request('session.join', { invitation_id: invitation.invitation_id,
      join_intent: invitation.join_intent }, 'join-' + sid);
    assert.deepEqual((await wire(req, invitation.invitation_credential)).result, { status: 'join_pending', session_id: sid });
    assert.equal((await invoke('finish', { session_id: sid })).ready, true);
    const ready = (await wire(req, invitation.invitation_credential)).result;
    assert.equal(ready.status, 'ready'); assert.equal(ready.session.session_id, sid);
    return { invitation, req, ready };
  };
  const act = async (sid, entry, description) => {
    const req = request('action.request', { version: description.version, session_id: sid, id: 'a1',
      type: 'action.request', sender: description.agent, audience: [description.player],
      expected_capabilities_revision: 1, extensions: {},
      payload: { action: 'find-key', arguments: { room: 'hall' }, deadline: 30000 } }, 'action-' + sid);
    assert.ok((await wire(req, entry.ready.control_credential, { session_id: sid })).result);
    const claim = request('action.claim', { session_id: sid, action_id: 'a1',
      worker: { issuer: 'fixture-enrollment', subject: 'worker-1', kind: 'service' } }, 'claim-' + sid);
    return (await wire(claim, 'worker-1-fixture', { session_id: sid })).result.ticket;
  };
  for (const fault of faults) {
    const description = await invoke('start');
    const left = await join('left'), right = await join('right');
    const late = await invoke('issue', { session_id: 'late' });
    const tickets = { left: await act('left', left, description), right: await act('right', right, description) };
    assert.deepEqual(await invoke('execute', { session_id: 'left', operation: 'step', ticket: tickets.left,
      step: 1, crash: 'after_effect' }), { fixture_fault: 'after_effect' });
    assert.equal((await invoke('execute', { session_id: 'right', operation: 'step', ticket: tickets.right, step: 1 })).result.effect, 'committed');
    const before = await invoke('observe');
    assert.equal(before.sessions.left.action_state, 'unknown');
    await invoke('snapshot', { name: 'before' });
    const revocation = revoke('grant', description.grant_id);
    assert.deepEqual(await wire(revocation, 'player-fixture', { session_id: 'left', fault }), { fixture_fault: fault });
    const observed = await invoke('observe');
    if (fault === 'after_commit') {
      assert.equal(observed.grant_state, 'revoked');
      assert.deepEqual(await invoke('restart', { snapshot: 'before' }), { fixture_rejected: 'snapshot_mismatch' });
      snapshotsRejected++;
    } else assert.deepEqual(observed, before, 'precommit failure cannot leave partially closed children');
    assert.deepEqual(await invoke('restart'), { restarted: true });
    assert.deepEqual(await invoke('old_port_probe'), { fixture_rejected: 'temporarily_unavailable' });
    assert.deepEqual(await invoke('old_action_probe', { session_id: 'right', ticket: tickets.right }),
      { fixture_rejected: 'temporarily_unavailable' });
    const done = (await wire(revocation, 'player-fixture', { session_id: 'left' })).result;
    assert.deepEqual(done, { object_type: 'grant', object_id: description.grant_id, revision: 2, state: 'revoked' });
    const committed = await invoke('observe');
    assert.equal(committed.revoked_invitations, 1); assert.equal(committed.issued, 0);
    for (const child of Object.values(committed.sessions)) {
      assert.equal(child.state, 'closed'); assert.equal(child.authorized, false); assert.equal(child.world_effects, 1);
      closedSessions++;
    }
    assert.deepEqual((await wire(revocation, 'player-fixture', { session_id: 'right' })).result, done);
    assert.deepEqual(await invoke('observe'), committed, 'global replay from sibling cannot append events');
    const status = request('operation.get', { operation: 'permission.revoke', original_request_id: revocation.request_id }, 'status');
    assert.deepEqual((await wire(status)).result.revocation, done);
    for (const entry of [left, right]) {
      const result = (await wire(entry.req, entry.invitation.invitation_credential)).result;
      assert.equal(result.status, 'completed_without_secret'); assert.equal(result.reauth_required, true);
      assert.equal(Object.hasOwn(result, 'control_credential'), false); redactedJoins++;
    }
    assert.equal((await wire(request('session.join', { invitation_id: late.invitation_id,
      join_intent: late.join_intent }, 'late'), late.invitation_credential)).error.code, 'invitation_expired');
    assert.equal((await wire(revoke('grant', description.grant_id, 'grant-revoke', 2))).error.code, 'id_conflict');
    for (const [sid, entry] of [['left', left], ['right', right]]) {
      assert.deepEqual(await invoke('execute', { session_id: sid, operation: 'step', ticket: tickets[sid], step: 2 }),
        { fixture_rejected: 'grant_revoked' });
      if (sid === 'left') assert.equal((await invoke('execute', { session_id: sid,
        operation: 'reconcile', ticket: tickets[sid] })).result, 'reconciled');
      assert.deepEqual((await invoke('execute', { session_id: sid, operation: 'finish', ticket: tickets[sid] })).result,
        ['cancelled', 'partial']);
      const query = request('action.query', { session_id: sid, action_id: 'a1' }, 'query-' + sid);
      const result = (await wire(query, entry.ready.result_read_handle, { session_id: sid })).result;
      assert.equal(result.state, 'cancelled'); assert.equal(result.effect, 'partial');
    }
    const settled = await invoke('observe');
    for (const child of Object.values(settled.sessions)) {
      assert.equal(child.world_effects, 1); preservedEffects += child.world_effects;
    }
  }
  // 独立 session 撤权不推进共享 Grant；兄弟会话仍可执行，结果读权也独立撤销。
  const description = await invoke('start');
  await join('left'); const right = await join('right');
  assert.equal((await wire(revoke('session', 'left', 'local'), 'player-fixture', { session_id: 'left' })).result.state, 'closed');
  const isolated = await invoke('observe');
  assert.equal(isolated.grant_state, 'active'); assert.equal(isolated.grant_revision, 1);
  assert.equal(isolated.sessions.right.state, 'active');
  await act('right', right, description);
  await wire(revoke('result_read', 'right', 'read'), 'player-fixture', { session_id: 'right' });
  assert.equal((await wire(request('action.query', { session_id: 'right', action_id: 'a1' }, 'denied'),
    right.ready.result_read_handle, { session_id: 'right' })).error.code, 'permission_denied');
  assert.equal((await wire(revoke('grant', description.grant_id))).result.revision, 2);
  return { passed: true, scope: 'candidate-shared-grant-fixture', faults, completed: faults.length,
    wire_calls: wireCalls, fixture_calls: fixtureCalls, closed_sessions: closedSessions, redacted_joins: redactedJoins,
    snapshots_rejected: snapshotsRejected, preserved_effects: preservedEffects, isolated_session: true,
    limitations: ['fixed preapproved Grant and trusted invitation port', 'no real authentication or durable storage'] };
}
