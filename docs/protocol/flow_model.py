"""G2A 设计的纯内存重放模型；不是 SDK、服务器或密码学实现。

只使用固定测试身份、逻辑时钟、内存账本和假世界/设备。网络、资源字节、
提供者证明是显式 fixture，不能据此声称真实 TLS/OAuth/引擎验证通过。
"""

from copy import deepcopy
import hashlib
import json


class Rejected(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise Rejected(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


class FlowModel:
    """单授权域、串行操作的抽象模型；不模拟数据库线程或网络堆栈。"""

    def __init__(self, features=('actions', 'presentation'), durable=False):
        self.now = 0
        self.revision = 1
        self.epoch = 1
        self.transport_epoch = 1
        self.features = set(features) | {'core.session', 'core.events'}
        self.durable = durable
        self.proofs = {'player-proof': ('alice', 'player'),
                       'agent-proof': ('fox', 'agent'),
                       'game-proof': ('key-quest', 'game')}
        self.offers = {}
        self.sessions = {}
        self.receipts = {}
        self.invites = {}
        self.controls = {}
        self.slots = {}
        self.actions = {}
        self.events = []
        self.floor = 0
        self.members = {'alice': 1, 'fox': 1, 'bob': 1}
        self.member_serial = dict(self.members)
        self.baseline = True
        self.visible = True
        self.manual_revision = 0
        self.occupations = {}
        self.released = set()
        self.effects = 0
        self.running_companions = 0
        self.capacity = 64
        self.auto_rule = None
        self.mailbox_open = True
        self.relay = {}
        self.pulls = {}
        self.memory = {}
        self.audit = []
        self._serial = 0

    def new_id(self, prefix):
        self._serial += 1
        return f'{prefix}{self._serial}'  # 仅 fixture，生产必须使用不可预测 ID

    def identity(self, proof, role):
        require(proof in self.proofs, 'unauthenticated')
        principal, actual = self.proofs[proof]
        require(actual == role, 'permission_denied')
        return principal

    def scope(self, topology):
        return {'agent': 'fox', 'player': 'alice', 'instance': self.epoch,
                'revision': self.revision, 'features': sorted(self.features),
                'topology': topology, 'actions': ['find-key'] if 'actions' in self.features else [],
                'audiences': ['alice', 'fox', 'bob'], 'expires': self.now + 300}

    @staticmethod
    def rule_key(scope):
        return digest({k: v for k, v in scope.items() if k != 'expires'})

    def create_offer(self, proof, entry, topology='local/local', nonce='offer-1',
                     version='design', required=(), unknown_required_extension=False):
        actor = self.identity(proof, 'agent' if entry == 'companion' else 'player')
        require(version == 'design', 'unsupported_version')
        require(set(required) <= self.features, 'feature_unsupported')
        require(not unknown_required_extension, 'extension_unsupported')
        key = (actor, nonce)
        body = digest((entry, topology, version, sorted(required)))
        if key in self.receipts:
            old = self.receipts[key]
            require(old[0] == body, 'id_conflict')
            return old[1]
        oid = self.new_id('offer-')
        scope = self.scope(topology)
        self.offers[oid] = {'scope': scope, 'digest': digest(scope), 'state': 'pending',
                            'grant': False, 'deadline': self.now + 60,
                            'launch': False, 'invite': None}
        self.receipts[key] = (body, oid)
        return oid

    def current(self, offer):
        require(offer['scope']['instance'] == self.epoch and
                offer['scope']['revision'] == self.revision, 'approval_stale')
        require(self.now < offer['deadline'], 'offer_expired')

    def decide(self, proof, oid, seen=None, allow=True, launch=False, remember=False):
        self.identity(proof, 'player')
        offer = self.offers[oid]
        if offer['state'] == 'denied' and not allow:
            return 'denied'
        if offer['state'] == 'approved' and allow:
            require(seen is None or seen == offer['digest'], 'id_conflict')
            return 'approved'
        require(offer['state'] == 'pending', 'decision_conflict')
        if not allow:
            offer['state'] = 'denied'
            return 'denied'
        self.current(offer)
        require(seen is None or seen == offer['digest'], 'approval_stale')
        offer.update(state='approved', grant=True, launch=launch)
        if remember:
            self.auto_rule = (self.rule_key(offer['scope']), self.now + 900)
        return 'approved'

    def automatic(self, oid, needs_launch=False):
        offer = self.offers[oid]
        self.current(offer)
        require(self.auto_rule and self.auto_rule[0] == self.rule_key(offer['scope'])
                and self.auto_rule[1] >= offer['scope']['expires']
                and not needs_launch, 'consent_required')
        offer.update(state='approved', grant=True)

    def start(self, oid, failure=False):
        offer = self.offers[oid]
        require(offer['state'] == 'approved' and offer['launch'], 'launch_consent_required')
        if failure:
            offer['grant'] = False
            raise Rejected('launch_failed')
        self.running_companions = 1

    def reserve(self, oid):
        if oid in self.slots:
            return
        require('multi-session' in self.features or not self.slots, 'session_conflict')
        self.slots[oid] = None

    def redeem(self, proof, oid, device='desktop'):
        self.identity(proof, 'agent')
        offer = self.offers[oid]
        require(offer['state'] == 'approved' and offer['grant'], 'consent_required')
        self.current(offer)
        intent = digest((offer['digest'], device))
        if offer['invite']:
            inv = self.invites[offer['invite']]
            require(inv['intent'] == intent, 'redemption_conflict')
            require(self.now < inv['deadline'], 'invitation_expired')
            return offer['invite']
        iid = self.new_id('invitation-')
        self.invites[iid] = {'oid': oid, 'intent': intent, 'device': device,
                             'deadline': min(offer['deadline'], self.now + 30), 'sid': None}
        offer['invite'] = iid
        return iid

    def join(self, proof, iid, finish=True):
        self.identity(proof, 'agent')
        inv = self.invites[iid]
        if inv['sid']:
            session = self.sessions[inv['sid']]
            self.live(session)
            if not session['ready']:
                return (inv['sid'], 'join_pending')
            return (inv['sid'], 1 if session['generation'] == 1 else 'already_joined')
        require(self.now < inv['deadline'], 'invitation_expired')
        offer = self.offers[inv['oid']]
        self.current(offer)
        require(offer['grant'], 'grant_revoked')
        self.reserve(inv['oid'])
        sid = self.new_id('session-')
        self.sessions[sid] = {'oid': inv['oid'], 'state': 'active', 'ready': False,
                              'generation': 1, 'lease': self.now + 120,
                              'epoch': self.epoch, 'transport_epoch': self.transport_epoch,
                              'device': inv['device'], 'read_until': None}
        inv['sid'] = sid
        self.slots[inv['oid']] = sid
        if finish:
            self.admit(sid)
        return (sid, 1 if finish else 'join_pending')

    def recompute(self):
        self.visible = self.baseline and not self.occupations

    def acquire(self, sid, generation):
        require((sid, generation) not in self.released, 'occupation_released')
        self.occupations[(sid, generation)] = 'hide'
        self.recompute()

    def release(self, sid, generation):
        self.released.add((sid, generation))
        self.occupations.pop((sid, generation), None)
        self.recompute()

    def admit(self, sid, resource_ok=True, revoke_before_commit=False):
        session = self.sessions[sid]
        self.live(session)
        if not resource_ok:
            self.close(sid, 'resource_failure')
            raise Rejected('resource_failure')
        if 'presentation' in self.features:
            self.acquire(sid, session['generation'])
        if revoke_before_commit:
            self.revoke(session['oid'])
        self.live(session)
        session['ready'] = True

    def live(self, session):
        if session['state'] == 'active' and self.now >= session['lease']:
            sid = next(k for k, v in self.sessions.items() if v is session)
            self.close(sid, 'expired')
        require(session['state'] == 'active', 'session_closed')
        require(self.offers[session['oid']]['grant'], 'grant_revoked')

    def control(self, sid, generation):
        session = self.sessions[sid]
        self.live(session)
        require(session['transport_epoch'] == self.transport_epoch, 'stale_transport')
        require(session['ready'], 'session_not_ready')
        require(generation == session['generation'], 'stale_controller')
        return session

    def close(self, sid, reason='left'):
        session = self.sessions[sid]
        if session['state'] == 'closed':
            return
        session.update(state='closed', ready=False, read_until=self.now + 300, reason=reason)
        self.slots.pop(session['oid'], None)
        for (s, _), action in self.actions.items():
            if s == sid and action['state'] in ('pending', 'executing'):
                action['state'] = 'cancelled' if action['state'] == 'pending' else 'unknown'
                action['effect'] = 'none' if action['state'] == 'cancelled' else 'undetermined'
                action['fence'] += 1
        for s, gen in list(self.occupations):
            if s == sid:
                self.release(sid, gen)

    def revoke(self, oid):
        self.offers[oid]['grant'] = False
        for sid, session in self.sessions.items():
            if session['oid'] == oid:
                self.close(sid, 'revoked')

    def manual(self, visible):
        self.baseline = visible
        self.manual_revision += 1
        if visible:
            for sid, _ in list(self.occupations):
                self.close(sid, 'presentation_terms_rejected')
        self.recompute()

    def publish(self, sid, mid, recipients, text, sender='game'):
        # 本方法从已验证的管理/伙伴路由调用；不是未认证公开 API。
        self.live(self.sessions[sid])
        require(self.sessions[sid]['ready'], 'session_not_ready')
        require(set(recipients) <= set(self.members), 'permission_denied')
        require(set(recipients) <= set(self.offers[self.sessions[sid]['oid']]['scope']['audiences']),
                'permission_denied')
        key = ('message', sid, sender, mid)
        body = digest((recipients, text))
        if key in self.receipts:
            require(self.receipts[key] == body, 'id_conflict')
            return
        self.receipts[key] = body
        self.events.append({'seq': len(self.events) + 1, 'sid': sid,
                            'audience': {(p, self.members[p]) for p in recipients}, 'text': text})

    def membership(self, members):
        for principal in members:
            if principal not in self.members:
                self.member_serial[principal] = self.member_serial.get(principal, 0) + 1
        self.members = {p: self.member_serial[p] for p in members}

    def page(self, sid, principal, cursor=0, size=1, scan_budget=8):
        require(cursor >= self.floor, 'history_gap')
        visible, scanned, last = [], 0, cursor
        for event in self.events:
            if event['seq'] <= cursor:
                continue
            if scanned >= scan_budget:
                break
            scanned += 1
            last = event['seq']
            if event['sid'] == sid and (principal, self.members.get(principal)) in event['audience']:
                visible.append(event['text'])
            if len(visible) == size:
                break
        return visible, last

    def request(self, sid, generation=1, aid='a1', arguments=None):
        session = self.control(sid, generation)
        body = {'room': 'hall'} if arguments is None else deepcopy(arguments)
        key = (sid, aid)
        if key in self.actions:
            require(self.actions[key]['digest'] == digest(body), 'id_conflict')
            return 'duplicate'
        require('actions' in self.features, 'feature_unsupported')
        require(self.revision == self.offers[session['oid']]['scope']['revision'], 'stale_capabilities')
        require(len(self.actions) < self.capacity, 'resource_limit')
        require(body == {'room': 'hall'}, 'invalid_arguments')
        self.actions[key] = {'state': 'pending', 'digest': digest(body), 'generation': generation,
                             'fence': 1, 'ticket': None, 'fact': None, 'step_consumed': False,
                             'effect': 'none', 'deadline': min(self.now + 30, session['lease'])}
        return 'accepted'

    def claim(self, proof, sid, aid='a1'):
        self.identity(proof, 'game')
        action = self.actions[(sid, aid)]
        require(action['state'] == 'pending', 'not_executable')
        self.control(sid, action['generation'])
        require(self.now < action['deadline'], 'not_executable')
        action['state'] = 'executing'
        action['ticket'] = (sid, aid, action['fence'], action['generation'])
        return action['ticket']

    def effect(self, proof, ticket, uncertain=False):
        self.identity(proof, 'game')
        sid, aid, fence, generation = ticket
        action = self.actions[(sid, aid)]
        require(ticket == action['ticket'], 'permission_denied')
        if action['step_consumed']:
            require(action['fact'] is not None, 'outcome_unknown')
            return deepcopy(action['fact'])
        self.control(sid, generation)
        require(action['state'] == 'executing' and action['fence'] == fence, 'not_executable')
        require(self.now < action['deadline'], 'not_executable')
        action['step_consumed'] = True
        if uncertain:
            action.update(state='unknown', effect='undetermined')
            raise Rejected('outcome_unknown')
        self.effects += 1
        action['fact'] = {'state': 'succeeded', 'effect': 'committed', 'item': 'gold-key'}
        # 世界事实与终态上报是两步；已知效果不能在中间查询中继续谎报 none。
        action['effect'] = 'committed'
        return deepcopy(action['fact'])

    def result(self, proof, ticket, fact):
        self.identity(proof, 'game')
        action = self.actions[ticket[:2]]
        require(ticket == action['ticket'], 'permission_denied')
        require(action['fact'] is not None and isinstance(fact, dict)
                and fact == action['fact'], 'unproven_result')
        require(action['state'] not in ('failed', 'cancelled'), 'execution_conflict')
        action.update(state=fact['state'], effect=fact['effect'])

    def unknown(self, sid, aid='a1'):
        action = self.actions[(sid, aid)]
        require(action['state'] == 'executing', 'invalid_state')
        action.update(state='unknown', effect='undetermined')

    def query(self, proof, sid, aid='a1'):
        self.identity(proof, 'agent')  # fixture 代表原主体绑定的只读句柄
        require(sid in self.sessions, 'result_unavailable')
        until = self.sessions[sid]['read_until']
        require(until is None or self.now <= until, 'result_expired')
        require((sid, aid) in self.actions, 'not_found')
        return deepcopy(self.actions[(sid, aid)])

    def cancel(self, sid, aid='a1'):
        action = self.actions[(sid, aid)]
        if action['state'] == 'pending':
            action.update(state='cancelled', effect='none')
        elif action['state'] == 'executing':
            action['fence'] += 1

    def capabilities_changed(self):
        self.revision += 1
        for action in self.actions.values():
            if action['state'] == 'pending':
                action.update(state='cancelled', effect='none')
            elif action['state'] == 'executing':
                action['fence'] += 1

    def resume(self, proof, sid, expected, request_id):
        self.identity(proof, 'agent')
        key = ('resume', sid, request_id)
        session = self.sessions[sid]
        self.live(session)
        if key in self.controls:
            old_expected, issued = self.controls[key]
            require(old_expected == expected, 'id_conflict')
            return issued if issued == session['generation'] else 'completed_without_secret'
        require(self.durable and 'resume' in self.features, 'resume_denied')
        require(session['generation'] == expected, 'generation_conflict')
        self._rotate(sid)
        session['transport_epoch'] = self.transport_epoch
        self.controls[key] = (expected, session['generation'])
        return session['generation']

    def _rotate(self, sid):
        session = self.sessions[sid]
        old = session['generation']
        session['generation'] += 1
        for (s, _), action in self.actions.items():
            if s == sid and action['state'] in ('pending', 'executing'):
                action['state'] = 'cancelled' if action['state'] == 'pending' else 'unknown'
                action['effect'] = 'none' if action['state'] == 'cancelled' else 'undetermined'
                action['fence'] += 1
        if 'presentation' in self.features:
            self.release(sid, old)
            self.acquire(sid, session['generation'])

    def handoff(self, proof, sid, target):
        self.identity(proof, 'player')
        require(self.durable and {'resume', 'handoff'} <= self.features, 'feature_unsupported')
        self.live(self.sessions[sid])
        self._rotate(sid)  # 本模型只覆盖两端 ACK 立即成功，延迟阶段由轨迹审计覆盖
        self.sessions[sid]['device'] = target
        return self.sessions[sid]['generation']

    def restart(self, lose_ledger=False):
        self.transport_epoch += 1
        if lose_ledger or not self.durable:
            self.epoch += 1
            for sid in list(self.sessions):
                self.close(sid, 'state_lost')
            self.actions.clear()
            self.sessions.clear()

    def relay_call(self, role, rid, operation, payload):
        require(self.mailbox_open, 'bridge_closed')
        permitted = {'agent': {'action.request', 'action.query', 'session.join'},
                     'controller': {'offer.decide', 'permission.revoke'}}
        require(operation in permitted.get(role, set()), 'permission_denied')
        key = (role, rid)
        body = digest((operation, payload))
        if key in self.relay:
            require(self.relay[key]['digest'] == body, 'id_conflict')
        else:
            self.relay[key] = {'state': 'queued', 'digest': body, 'reply': None}
        return key

    def pull(self, proof, nonce):
        self.identity(proof, 'game')
        require(self.mailbox_open, 'bridge_closed')
        if nonce in self.pulls:
            return self.pulls[nonce]
        keys = [k for k, v in self.relay.items() if v['state'] == 'queued'][:1]
        for key in keys:
            self.relay[key]['state'] = 'claimed'
        self.pulls[nonce] = keys
        return keys

    def relay_timeout(self, key):
        rec = self.relay[key]
        outcome = 'unknown' if rec['state'] == 'claimed' else 'not_dispatched'
        rec['state'] = 'expired'
        return outcome

    def relay_close(self):
        result = {k: self.relay_timeout(k) for k, v in self.relay.items()
                  if v['state'] in ('queued', 'claimed')}
        self.mailbox_open = False
        return result

    def provider_callback(self, nonce, expected, actual):
        require(actual == expected, 'delegation_mismatch')
        key = ('provider', nonce)
        if key in self.controls:
            require(self.controls[key] == actual, 'id_conflict')
        self.controls[key] = deepcopy(actual)
        return actual

    def remember(self, source, kind, audience):
        require(kind in {'shared_experience', 'player_report', 'external_reference'},
                'invalid_provenance')
        self.memory[source] = {'kind': kind, 'audience': set(audience), 'revoked': False}

    def disclose(self, source, recipients):
        item = self.memory[source]
        require(not item['revoked'] and set(recipients) <= item['audience'], 'permission_denied')
        return item['kind']

    def privacy(self, proof, source, partial=False):
        self.identity(proof, 'player')
        self.memory[source]['revoked'] = True
        return 'partial' if partial else 'done'  # 仅表示模型控制的副本

    @staticmethod
    def resource(content, expected_digest, declared_size, origin, approved, dependencies=()):
        require(origin in approved, 'resource_origin_denied')
        require(len(content) == declared_size, 'resource_size_mismatch')
        require(hashlib.sha256(content).hexdigest() == expected_digest, 'resource_integrity_error')
        require(len(dependencies) == len(set(dependencies)), 'resource_cycle')
        return 'verified-fixture'  # 不是实际 parser/sandbox 证明
