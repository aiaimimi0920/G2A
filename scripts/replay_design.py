"""本地、无网络的 G2A 假实现轨迹；测试输出不代表真实 SDK/引擎验证。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[1] / 'docs' / 'protocol'
spec = importlib.util.spec_from_file_location('g2a_flow_model', ROOT / 'flow_model.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Model, Rejected = module.FlowModel, module.Rejected
RESULTS = []


def rejects(code, call):
    try:
        call()
    except Rejected as error:
        assert error.code == code, (code, error.code)
    else:
        raise AssertionError(f'Expected rejection: {code}')


def opened(model=None, entry='game', topology='local/local', nonce='offer-1', finish=True):
    m = model or Model()
    if 'cloud' in topology:
        m.provider_callback(nonce, ('alice', 'fox', 'key-quest'), ('alice', 'fox', 'key-quest'))
    proof = 'player-proof' if entry == 'game' else 'agent-proof'
    oid = m.create_offer(proof, entry, topology, nonce)
    m.decide('player-proof', oid, launch=entry == 'game' and topology.endswith('/local'))
    if entry == 'game' and topology.endswith('/local'):
        m.start(oid)
    else:
        m.running_companions = 1 if topology.endswith('/local') else 0
    iid = m.redeem('agent-proof', oid, device='desktop' if topology.endswith('/local') else None)
    sid, status = m.join('agent-proof', iid, finish)
    return m, oid, iid, sid


def record(name):
    def wrap(function):
        try:
            detail = function() or {}
            RESULTS.append({'id': name, 'status': 'passed', 'observed': detail})
        except Exception:
            RESULTS.append({'id': name, 'status': 'failed', 'error': traceback.format_exc()})
        return function
    return wrap


for topology in ('local/local', 'local/cloud', 'cloud/local', 'cloud/cloud'):
    for entry in ('game', 'companion'):
        @record(f'MAIN:{topology}:{entry}')
        def main(topology=topology, entry=entry):
            features = ['actions'] + (['presentation'] if topology.endswith('/local') else [])
            m, oid, iid, sid = opened(Model(features), entry, topology)
            m.publish(sid, 'c1', ['alice', 'fox'], 'hall')
            assert m.page(sid, 'fox')[0] == ['hall']
            m.publish(sid, 'm1', ['alice'], 'I can find the key', sender='fox')
            m.request(sid)
            ticket = m.claim('game-proof', sid)
            fact = m.effect('game-proof', ticket)
            m.result('game-proof', ticket, fact)
            assert m.query('agent-proof', sid)['state'] == 'succeeded'
            assert m.request(sid) == 'duplicate'
            assert m.effects == 1
            m.close(sid)
            assert not m.occupations and m.visible and not m.slots
            assert m.query('agent-proof', sid)['state'] == 'succeeded'
            return {'effects': m.effects, 'sessions': len(m.sessions),
                    'session_state': m.sessions[sid]['state'], 'visible': m.visible}


@record('T01')
def denied():
    m = Model(); oid = m.create_offer('player-proof', 'game')
    m.decide('player-proof', oid, allow=False)
    rejects('consent_required', lambda: m.redeem('agent-proof', oid))
    assert not m.sessions and not m.invites and m.running_companions == 0


@record('T02')
def stale():
    m = Model(); oid = m.create_offer('player-proof', 'game')
    m.decide('player-proof', oid); m.revision += 1
    rejects('approval_stale', lambda: m.redeem('agent-proof', oid))
    assert not m.sessions


@record('T03')
def launch_failure():
    m = Model(); oid = m.create_offer('player-proof', 'game')
    m.decide('player-proof', oid, launch=True)
    rejects('launch_failed', lambda: m.start(oid, failure=True))
    assert not m.offers[oid]['grant'] and not m.sessions


@record('T04')
def repeat_join():
    m, _, iid, sid = opened()
    assert m.join('agent-proof', iid) == (sid, 1)
    assert len(m.sessions) == 1 and len(m.occupations) == 1


@record('T05')
def revoked_during_admission():
    m, _, _, sid = opened(finish=False)
    rejects('session_not_ready', lambda: m.request(sid))
    rejects('session_closed', lambda: m.admit(sid, revoke_before_commit=True))
    assert not m.occupations and m.visible and m.effects == 0


@record('T06')
def cancel_pending():
    m, _, _, sid = opened(); m.request(sid); m.cancel(sid)
    rejects('not_executable', lambda: m.claim('game-proof', sid))
    assert m.query('agent-proof', sid)['state'] == 'cancelled' and m.effects == 0


@record('T07')
def revoke_before_effect():
    m, _, _, sid = opened(); m.request(sid); ticket = m.claim('game-proof', sid)
    m.capabilities_changed()
    rejects('not_executable', lambda: m.effect('game-proof', ticket))
    assert m.effects == 0


@record('T08')
def lost_effect_reply():
    m, _, _, sid = opened(); m.request(sid); ticket = m.claim('game-proof', sid)
    fact = m.effect('game-proof', ticket); m.unknown(sid)
    assert m.query('agent-proof', sid)['state'] == 'unknown'
    assert m.effect('game-proof', ticket) == fact
    m.result('game-proof', ticket, fact)
    assert m.query('agent-proof', sid)['state'] == 'succeeded' and m.effects == 1


@record('T09')
def uncertain_effect():
    m, _, _, sid = opened(); m.request(sid); ticket = m.claim('game-proof', sid)
    rejects('outcome_unknown', lambda: m.effect('game-proof', ticket, uncertain=True))
    rejects('outcome_unknown', lambda: m.effect('game-proof', ticket))
    assert m.query('agent-proof', sid)['effect'] == 'undetermined'


@record('T10')
def history_gap():
    m, _, _, sid = opened()
    for i in range(4): m.publish(sid, f'c{i}', ['fox'], str(i))
    m.floor = 2
    rejects('history_gap', lambda: m.page(sid, 'fox', cursor=0))
    assert m.page(sid, 'fox', cursor=2)[0] == ['2']


@record('T11')
def rejoined_member():
    m, _, _, sid = opened(); m.publish(sid, 'old', ['bob'], 'private-team')
    m.membership(['alice', 'fox']); assert m.page(sid, 'bob')[0] == []
    m.membership(['alice', 'fox', 'bob']); assert m.page(sid, 'bob')[0] == []
    m.publish(sid, 'new', ['bob'], 'new-team')
    assert m.page(sid, 'bob')[0] == ['new-team']


@record('T12')
def two_sessions():
    m = Model(['actions', 'presentation', 'multi-session'])
    _, _, _, s1 = opened(m); _, _, _, s2 = opened(m, nonce='second')
    m.close(s1); assert not m.visible and len(m.occupations) == 1
    m.close(s2); assert m.visible and not m.occupations


@record('T13')
def manual_intent():
    m, _, _, sid = opened(); m.manual(True)
    assert m.visible and m.manual_revision == 1 and not m.occupations
    rejects('session_closed', lambda: m.request(sid))


@record('T14')
def handoff_replay():
    m, _, iid, sid = opened(Model(['actions', 'presentation', 'resume', 'handoff'], True))
    assert m.handoff('player-proof', sid, 'new-device') == 2
    assert m.join('agent-proof', iid) == (sid, 'already_joined')
    rejects('stale_controller', lambda: m.request(sid, generation=1))
    assert m.request(sid, generation=2) == 'accepted'


@record('T15')
def invalid_resource():
    m, _, _, sid = opened(finish=False)
    rejects('resource_integrity_error', lambda: m.resource(b'x', 'bad', 1,
                                                         'https://assets', ['https://assets']))
    rejects('resource_failure', lambda: m.admit(sid, resource_ok=False))
    assert m.sessions[sid]['state'] == 'closed' and not m.occupations


@record('T16')
def restart():
    m, _, _, sid = opened(Model(['actions', 'resume'], True))
    m.request(sid); m.restart()
    assert m.resume('agent-proof', sid, 1, 'resume-1') == 2
    assert m.query('agent-proof', sid)['state'] == 'cancelled'
    m.restart(lose_ledger=True)
    rejects('result_unavailable', lambda: m.query('agent-proof', sid))


@record('T17')
def negotiation_rejection():
    m = Model()
    rejects('unsupported_version', lambda: m.create_offer('player-proof', 'game', version='other'))
    rejects('extension_unsupported', lambda: m.create_offer('player-proof', 'game',
                                                          unknown_required_extension=True))
    assert not m.offers


@record('T18')
def capacity():
    m, _, _, sid = opened(); m.capacity = 0
    rejects('resource_limit', lambda: m.request(sid)); assert not m.actions
    m.capacity = 1; m.request(sid); assert m.query('agent-proof', sid)['state'] == 'pending'
    m.close(sid); assert m.sessions[sid]['state'] == 'closed'


@record('T19')
def cross_lane():
    m = Model()
    rejects('permission_denied', lambda: m.relay_call('agent', 'r1', 'offer.decide', {}))
    rejects('permission_denied', lambda: m.relay_call('agent', 'r2', 'action.claim', {}))
    assert not m.relay


@record('T20')
def claimed_timeout():
    m, _, _, sid = opened(); key = m.relay_call('agent', 'r1', 'action.request', {'id':'a1'})
    m.pull('game-proof', 'p1'); m.request(sid)
    ticket = m.claim('game-proof', sid); fact = m.effect('game-proof', ticket)
    assert m.relay_timeout(key) == 'unknown'
    assert m.request(sid) == 'duplicate'
    m.result('game-proof', ticket, fact); assert m.effects == 1


@record('T21')
def duplicate_pull():
    m = Model(); key = m.relay_call('agent', 'r1', 'action.query', {})
    first = m.pull('game-proof', 'p1')
    assert first == [key] and m.pull('game-proof', 'p1') == first
    assert m.pull('game-proof', 'p2') == []


@record('T22')
def relay_revocation():
    m = Model(); claimed = m.relay_call('agent', 'r1', 'action.query', {})
    m.pull('game-proof', 'p1'); queued = m.relay_call('agent', 'r2', 'action.query', {})
    outcomes = m.relay_close()
    assert outcomes[claimed] == 'unknown' and outcomes[queued] == 'not_dispatched'
    rejects('bridge_closed', lambda: m.pull('game-proof', 'p2'))


@record('T23')
def approval_replay():
    m = Model(); oid = m.create_offer('player-proof', 'game')
    assert m.decide('player-proof', oid) == m.decide('player-proof', oid)
    assert len(m.offers) == 1 and sum(o['grant'] for o in m.offers.values()) == 1


@record('T24')
def resume_replay():
    m, _, _, sid = opened(Model(['actions', 'resume', 'handoff'], True))
    assert m.resume('agent-proof', sid, 1, 'r1') == 2
    assert m.resume('agent-proof', sid, 1, 'r1') == 2
    rejects('generation_conflict', lambda: m.resume('agent-proof', sid, 1, 'r2'))
    m.handoff('player-proof', sid, 'other')
    assert m.resume('agent-proof', sid, 1, 'r1') == 'completed_without_secret'


@record('T25')
def delayed_acquire():
    m = Model(); m.release('old-session', 1)
    rejects('occupation_released', lambda: m.acquire('old-session', 1))
    assert not m.occupations and m.visible


@record('EXTRA:authorization')
def authorization():
    m = Model(); oid = m.create_offer('agent-proof', 'companion')
    rejects('permission_denied', lambda: m.decide('agent-proof', oid))
    rejects('unauthenticated', lambda: m.decide('unknown-proof', oid))
    assert not m.offers[oid]['grant']


@record('EXTRA:minimal-cloud')
def minimal_cloud():
    m, _, _, sid = opened(Model([]), 'companion', 'cloud/cloud')
    assert not m.occupations
    m.publish(sid, 'hello', ['alice'], 'hello', sender='fox')
    rejects('feature_unsupported', lambda: m.request(sid))
    assert m.page(sid, 'alice')[0] == ['hello']


@record('EXTRA:pagination')
def pagination():
    m, _, _, sid = opened()
    for i in range(4): m.publish(sid, str(i), ['fox'], str(i))
    one, c1 = m.page(sid, 'fox', size=2)
    two, c2 = m.page(sid, 'fox', cursor=c1, size=2)
    assert one + two == ['0','1','2','3'] and (c1,c2) == (2,4)


@record('EXTRA:source-and-privacy')
def source_privacy():
    m = Model(); m.remember('s1', 'player_report', ['alice','fox'])
    assert m.disclose('s1', ['alice']) == 'player_report'
    rejects('permission_denied', lambda: m.disclose('s1', ['bob']))
    assert m.privacy('player-proof', 's1', partial=True) == 'partial'
    rejects('permission_denied', lambda: m.disclose('s1', ['alice']))


@record('EXTRA:expiry')
def expiry():
    m, _, _, sid = opened(); m.request(sid); m.now = 121
    rejects('session_closed', lambda: m.request(sid, aid='a2'))
    assert m.sessions[sid]['state'] == 'closed' and m.visible
    assert m.query('agent-proof', sid)['state'] == 'cancelled'
    m.now += 301
    rejects('result_expired', lambda: m.query('agent-proof', sid))


@record('EXTRA:automatic-scope')
def auto_rule():
    m = Model(); oid = m.create_offer('player-proof','game')
    m.decide('player-proof', oid, remember=True)
    m.now = 10; second = m.create_offer('agent-proof','companion',nonce='new')
    m.automatic(second)
    m.revision += 1; third=m.create_offer('agent-proof','companion',nonce='changed')
    rejects('consent_required', lambda:m.automatic(third))


@record('EXTRA:resource-and-provider')
def resource_provider():
    m=Model(); h=hashlib.sha256(b'x').hexdigest()
    assert m.resource(b'x',h,1,'https://a',['https://a']) == 'verified-fixture'
    rejects('resource_origin_denied',lambda:m.resource(b'x',h,1,'https://b',['https://a']))
    rejects('delegation_mismatch',lambda:m.provider_callback('n',('alice','fox'),('alice','other')))


@record('EXTRA:single-session')
def single_session():
    m, _, _, sid = opened()
    rejects('session_conflict', lambda: opened(m, nonce='other'))
    assert len(m.sessions) == 1 and m.sessions[sid]['state'] == 'active'


@record('EXTRA:transport-epoch')
def transport_epoch():
    m, _, _, sid = opened(Model(['actions', 'resume'], True))
    m.restart()
    rejects('stale_transport', lambda: m.request(sid))
    assert m.resume('agent-proof', sid, 1, 'new-transport') == 2
    assert m.request(sid, generation=2) == 'accepted'


output = {'kind': 'pure-memory-design-replay', 'model_sha256': hashlib.sha256(
    (ROOT / 'flow_model.py').read_bytes()).hexdigest(),
    'passed': sum(r['status']=='passed' for r in RESULTS),
    'failed': sum(r['status']=='failed' for r in RESULTS), 'cases': RESULTS,
    'not_proven': ['real authentication/crypto', 'network or concurrency',
                   'real engine or desktop', 'resource parser safety',
                   'all pseudocode branches; see conformance audit']}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, help='可选 JSON 回执路径；默认不写文件')
args = parser.parse_args()
output['driver_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
if args.output:
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k:output[k] for k in ('kind','passed','failed')}, ensure_ascii=False))
for result in RESULTS:
    if result['status']=='failed': print(result['id'], result['error'])
raise SystemExit(1 if output['failed'] else 0)
