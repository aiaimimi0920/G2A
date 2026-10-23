// 独立构造候选组合的完整目标键、请求 ID 和规范字节，不导入 Python schema。
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { canonical } from './codec_peer.mjs';

export async function runFanoutCases(command) {
  const hash = value => createHash('sha256').update(canonical(value)).digest('hex');
  let wireCalls = 0, fixtureCalls = 0, completed = 0, snapshotsRejected = 0;
  const invoke = async (action, fields = {}) => {
    fixtureCalls++;
    return command({ kind: 'revoke_fanout', action, ...fields });
  };
  const kinds = ['session', 'grant', 'result_read', 'capability'];
  for (const objectType of kinds) {
    const description = await invoke('start');
    assert.match(description.coordinator_id, /^[0-9a-f-]{36}$/);
    const keys = Object.keys(description.targets).sort();
    assert.equal(keys.length, 2); assert.notEqual(keys[0], keys[1]);
    for (const key of keys) {
      const binding = description.targets[key];
      assert.deepEqual(Object.keys(binding).sort(), ['grant_id', 'instance', 'player', 'scope_digest', 'session_id']);
      assert.equal(hash(binding), key);
      assert.equal(binding.session_id, 's1'); assert.equal(binding.grant_id, 'g1');
      assert.deepEqual(binding.player, description.player); assert.equal(binding.instance.epoch, 'epoch-1');
    }
    assert.notDeepEqual(description.targets[keys[0]].instance.game, description.targets[keys[1]].instance.game);
    const operationId = 'fanout-' + objectType;
    const initial = await invoke('begin', { operation_id: operationId, object_type: objectType,
      catalogue_revision: description.catalogue_revision,
      targets: Object.fromEntries(keys.map(key => [key, 1])),
      ...(objectType === 'capability' ? { capability_ids: Object.fromEntries(keys.map(key => [key, 'find-key'])) } : {}) });
    assert.equal(initial.state, 'pending'); assert.equal(initial.object_type, objectType);
    assert.deepEqual(await invoke('snapshot', { name: 'prepared' }), { saved: true });
    const requests = keys.map(key => ({ version: description.version, operation: 'permission.revoke',
      request_id: 'fanout-' + hash([description.coordinator_id, operationId, key]), extensions: {}, payload: { object_type: objectType,
        object_id: objectType === 'capability' ? 'find-key' : description.targets[key][objectType === 'grant' ? 'grant_id' : 'session_id'],
        expected_revision: 1 } }));
    const send = async (index, request = requests[index], options = {}) => {
      wireCalls++;
      return invoke('deliver', { operation_id: operationId, target: keys[index], raw: canonical(request).toString('base64'), ...options });
    };
    const changed = structuredClone(requests[0]); changed.payload.expected_revision = 2;
    assert.deepEqual(await send(0, changed), { fixture_rejected: 'id_conflict' });
    assert.equal((await send(0)).state, 'partial');
    const partial = await invoke('observe');
    for (const field of ['grant_revision', 'read_revision', 'capabilities_revision']) assert.equal(partial[keys[1]][field], 1);
    const uncertain = await send(1, requests[1], { fault: 'after_commit' });
    assert.equal(uncertain.state, 'partial'); assert.equal(uncertain.targets[keys[1]], 'unknown');
    const committed = await invoke('observe');
    assert.deepEqual(await invoke('snapshot', { name: 'uncertain' }), { saved: true });
    assert.deepEqual(await invoke('restart', { snapshot: 'prepared' }), { fixture_rejected: 'snapshot_mismatch' });
    snapshotsRejected++;
    assert.deepEqual(await invoke('restart', { snapshot: 'uncertain' }),
      { restarted: true, coordinator_id: description.coordinator_id });
    const done = await send(1);
    assert.equal(done.state, 'done'); assert.ok(Object.values(done.targets).every(value => value === 'acknowledged'));
    assert.deepEqual(await invoke('restart', { snapshot: 'uncertain' }), { fixture_rejected: 'snapshot_mismatch' });
    snapshotsRejected++;
    assert.deepEqual(await invoke('observe'), committed, 'retry must not increment revisions or events');
    for (const value of Object.values(committed)) {
      const closing = objectType === 'session' || objectType === 'grant';
      assert.equal(value.session_state, closing ? 'closed' : 'active');
      assert.equal(value.grant_state, closing ? 'revoked' : 'active');
      assert.equal(value.grant_revision, closing ? 2 : 1);
      assert.equal(value.read_revision, objectType === 'result_read' ? 2 : 1);
      assert.equal(value.capabilities_revision, objectType === 'capability' ? 2 : 1);
      assert.equal(value.definitions, objectType === 'capability' ? 0 : 1);
    }
    completed++;
  }

  // 同一接收方、玩家和 operation_id 下，不同协调器的新意图不可碰撞。
  const first = await invoke('start');
  const key = Object.keys(first.targets).sort()[0], operationId = 'same-id';
  const namespaceIds = [];
  for (const objectType of ['result_read', 'session']) {
    const description = objectType === 'result_read' ? first : await invoke('new_coordinator');
    assert.deepEqual(description.targets, first.targets);
    await invoke('begin', { operation_id: operationId, object_type: objectType, targets: { [key]: 1 },
      catalogue_revision: description.catalogue_revision });
    const request = { version: description.version, operation: 'permission.revoke',
      request_id: 'fanout-' + hash([description.coordinator_id, operationId, key]), extensions: {},
      payload: { object_type: objectType, object_id: 's1', expected_revision: 1 } };
    namespaceIds.push(request.request_id); wireCalls++;
    const done = await invoke('deliver', { operation_id: operationId, target: key, raw: canonical(request).toString('base64') });
    assert.equal(done.state, 'done');
  }
  assert.notEqual(namespaceIds[0], namespaceIds[1]);
  const isolated = await invoke('observe');
  assert.equal(isolated[key].session_state, 'closed'); assert.equal(isolated[key].read_revision, 2);

  let dynamicCompleted = 0, unresolvedRetirements = 0, staleSelections = 0, retiredReplays = 0;
  const faults = ['before_commit', 'after_commit'];
  for (const fault of faults) {
    const description = await invoke('start', { multi_session: true });
    const keys = Object.keys(description.targets).sort((a, b) => description.targets[a].session_id.localeCompare(description.targets[b].session_id));
    assert.equal(description.catalogue_revision, 2);
    assert.equal(description.targets[keys[0]].session_id, 's1'); assert.equal(description.targets[keys[1]].session_id, 's2');
    assert.deepEqual(description.targets[keys[0]].instance, description.targets[keys[1]].instance);
    const operationId = 'dynamic-revoke', selection = { operation_id: operationId, object_type: 'session',
      targets: { [keys[0]]: 1 }, catalogue_revision: description.catalogue_revision };
    const pending = await invoke('begin', selection);
    const expanded = await invoke('add_epoch_target');
    for (const [key, binding] of Object.entries(expanded.targets)) assert.equal(hash(binding), key);
    const freshKey = Object.keys(expanded.targets).find(key => !keys.includes(key));
    assert.ok(freshKey); assert.equal(expanded.catalogue_revision, 3);
    assert.equal(expanded.targets[freshKey].session_id, 's1'); assert.equal(expanded.targets[freshKey].instance.epoch, 'epoch-2');
    assert.deepEqual(await invoke('begin', { ...selection, operation_id: 'late' }), { fixture_rejected: 'generation_conflict' });
    staleSelections++;
    assert.deepEqual(await invoke('begin', selection), pending);
    const retirement = { target: keys[0], catalogue_revision: expanded.catalogue_revision };
    assert.deepEqual(await invoke('retire', retirement), { fixture_rejected: 'not_drained' }); unresolvedRetirements++;
    const send = async (id, target, objectType = 'session', options = {}) => {
      const request = { version: description.version, operation: 'permission.revoke',
        request_id: 'fanout-' + hash([description.coordinator_id, id, target]), extensions: {},
        payload: { object_type: objectType, object_id: expanded.targets[target].session_id, expected_revision: 1 } };
      wireCalls++;
      return invoke('deliver', { operation_id: id, target, raw: canonical(request).toString('base64'), ...options });
    };
    const unknown = await send(operationId, keys[0], 'session', { fault: 'after_commit' });
    assert.equal(unknown.targets[keys[0]], 'unknown');
    assert.deepEqual(await invoke('retire', retirement), { fixture_rejected: 'not_drained' }); unresolvedRetirements++;
    const done = await send(operationId, keys[0]); assert.equal(done.state, 'done');
    const committed = await invoke('observe');
    assert.equal(committed[keys[1]].session_state, 'active'); assert.equal(committed[freshKey].session_state, 'active');
    assert.deepEqual(await invoke('snapshot', { name: 'before-retire' }), { saved: true });
    assert.deepEqual(await invoke('retire', { ...retirement, fault }), { fixture_fault: fault });
    assert.equal((await invoke('restart')).restarted, true);
    assert.deepEqual(await invoke('retire', retirement), { target: keys[0], state: 'retired', catalogue_revision: 4 });
    assert.deepEqual(await invoke('restart', { snapshot: 'before-retire' }), { fixture_rejected: 'snapshot_mismatch' });
    assert.equal((await invoke('restart')).restarted, true);
    assert.deepEqual(await invoke('reregister', { target: keys[0] }), { fixture_rejected: 'request_gone' });
    assert.deepEqual(await invoke('begin', selection), done);
    assert.deepEqual(await send(operationId, keys[0]), done); retiredReplays++;
    const active = await invoke('catalogue');
    assert.equal(active.revision, 4); assert.deepEqual(Object.keys(active.targets).sort(), [keys[1], freshKey].sort());
    assert.deepEqual(await invoke('begin', { ...selection, operation_id: 'retired-late', catalogue_revision: 4 }),
      { fixture_rejected: 'request_gone' });
    assert.deepEqual(await invoke('observe'), committed, 'directory retirement and replay must not change remote effects');
    await invoke('begin', { operation_id: 'read-sibling', object_type: 'result_read', targets: { [keys[1]]: 1 }, catalogue_revision: 4 });
    assert.equal((await send('read-sibling', keys[1], 'result_read')).state, 'done');
    const readRevoked = await invoke('observe');
    assert.equal(readRevoked[keys[1]].session_state, 'active'); assert.equal(readRevoked[keys[1]].read_revision, 2);
    assert.equal(readRevoked[keys[0]].read_revision, 1); assert.equal(readRevoked[freshKey].read_revision, 1);
    await invoke('begin', { operation_id: 'fresh', object_type: 'session', targets: { [freshKey]: 1 }, catalogue_revision: 4 });
    assert.equal((await send('fresh', freshKey)).state, 'done');
    const final = await invoke('observe');
    assert.equal(final[freshKey].session_state, 'closed'); assert.equal(final[keys[1]].session_state, 'active');
    dynamicCompleted++;
  }
  return { passed: true, kinds, completed, wire_calls: wireCalls, fixture_calls: fixtureCalls,
    snapshots_rejected: snapshotsRejected, namespace_isolated: true, scope: 'candidate-coordinator-fixture',
    dynamic_catalogue: { passed: true, faults, completed: dynamicCompleted, stale_selections: staleSelections,
      unresolved_retirements: unresolvedRetirements, retired_replays: retiredReplays, multi_session: true },
    limitations: ['trusted receiver binding and independent in-memory checkpoint', 'no real network or durable storage'] };
}
