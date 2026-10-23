"""独立代次切换参考模型；未接入 Relay wire，不提供生产身份或持久化。"""

from copy import deepcopy
import hashlib
import json
from threading import RLock
from uuid import uuid4


class RotationError(ValueError):
    pass


class RotationFault(RuntimeError):
    pass


class EpochRotation:
    MAX_EPOCH = 2**53 - 1
    MAX_MAILBOXES = 8

    def __init__(self):
        self.lock = RLock()
        self.retired = False
        self.healthy = True
        self.relay = {"epoch": 0, "sealed": False, "boxes": {}, "pairings": set()}
        self.game = {"epoch": 0, "inflight": set(), "journal": set(), "effects": 0,
                     "receipts": {}, "last_now": 0}
        self.instance_id = str(uuid4())
        # 独立于可回滚快照的可信恢复锚点；真实持久实现必须提供同等保证。
        self.checkpoints = {}
        self._checkpoint("relay")
        self._checkpoint("game")

    @staticmethod
    def _digest(value):
        def normalize(item):
            kind = type(item)
            if kind is dict:
                pairs = [(normalize(key), normalize(val)) for key, val in item.items()]
                return ["map", sorted(pairs, key=lambda pair: repr(pair[0]))]
            if kind is set:
                return ["set", sorted((normalize(val) for val in item), key=repr)]
            if kind in (list, tuple):
                return [kind.__name__, [normalize(val) for val in item]]
            if kind is bytes:
                return ["bytes", item.hex()]
            if item is None:
                return ["null"]
            if kind in (str, int, bool):
                return [kind.__name__, item]
            raise RotationError("invalid_snapshot")
        return hashlib.sha256(json.dumps(normalize(value), ensure_ascii=False,
                                        separators=(",", ":")).encode("utf-8")).hexdigest()

    def _checkpoint(self, owner):
        self.checkpoints[owner] = self._digest(getattr(self, owner))

    @staticmethod
    def require(condition, code):
        if not condition:
            raise RotationError(code)

    def _live(self):
        self.require(self.healthy and not self.retired, "temporarily_unavailable")

    def _epoch(self, value):
        self.require(type(value) is int and 0 <= value <= self.MAX_EPOCH, "invalid_arguments")

    def _commit(self, owner, change, fault):
        self.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        draft = deepcopy(getattr(self, owner))
        result = change(draft)
        if fault == "before_commit":
            raise RotationFault(fault)
        setattr(self, owner, draft)
        self._checkpoint(owner)
        if fault == "after_commit":
            raise RotationFault(fault)
        return result

    def register(self, pairing_epoch, pairing_id):
        """pairing_epoch/id 是可信同意端口提供的绑定，不接受请求自报。"""
        with self.lock:
            self._live(); self._epoch(pairing_epoch)
            r = self.relay
            self.require(pairing_epoch == r["epoch"] and not r["sealed"], "permission_denied")
            self.require(isinstance(pairing_id, str) and bool(pairing_id), "invalid_arguments")
            self.require(pairing_id not in r["pairings"], "id_conflict")
            self.require(len(r["boxes"]) < self.MAX_MAILBOXES, "resource_limit")
            identity = (r["epoch"], len(r["boxes"]) + 1)
            r["boxes"][identity] = "open"
            r["pairings"].add(pairing_id)
            self._checkpoint("relay")
            return identity

    def close(self, identity):
        with self.lock:
            self._live()
            self.require(identity in self.relay["boxes"], "permission_denied")
            self.relay["boxes"][identity] = "closed"
            self._checkpoint("relay")

    def claim(self, identity, request_id):
        with self.lock:
            self._live()
            self.require(not self.relay["sealed"] and self.relay["boxes"].get(identity) == "open", "request_gone")
            return (identity, request_id)  # 可信领取见证，允许在进入游戏之前发生切换。

    def _time(self, now):
        self.require(type(now) is int and 0 <= now <= self.MAX_EPOCH, "invalid_arguments")
        self.require(now >= self.game["last_now"], "temporarily_unavailable")
        self.game["last_now"] = now
        self._checkpoint("game")

    def begin(self, claim, *, now=None, retain_ms=60000):
        with self.lock:
            self._live()
            self.require(type(retain_ms) is int and 1 <= retain_ms <= 300000, "invalid_arguments")
            current = self.game["last_now"] if now is None else now
            self.require(type(current) is int and current <= self.MAX_EPOCH - retain_ms, "invalid_arguments")
            self._time(current)
            self.require(claim[0][0] == self.game["epoch"], "request_gone")
            self.require(claim not in self.game["journal"], "already_seen")
            self.require(len(self.game["journal"]) < 1024 and len(self.game["receipts"]) < 1024, "resource_limit")
            self.game["journal"].add(claim)
            self.game["inflight"].add(claim)
            self.game["receipts"][claim] = {"phase": "accepted", "retain_until": current + retain_ms}
            self._checkpoint("game")

    def finish(self, claim):
        with self.lock:
            self._live()
            self.require(claim in self.game["inflight"], "request_gone")
            self.game["effects"] += 1
            self.game["inflight"].remove(claim)
            self.game["receipts"][claim]["phase"] = "completed"
            self._checkpoint("game")

    def receipt(self, claim, *, now):
        """仅可信读权适配器调用；不是允许任何主体查询的公开接口。"""
        with self.lock:
            self._live(); self._time(now)
            record = self.game["receipts"].get(claim)
            self.require(record is not None and now < record["retain_until"], "request_gone")
            return deepcopy(record)

    def compact_receipts(self, *, now, maximum=128, fault=None):
        with self.lock:
            self._live()
            self.require(type(maximum) is int and 1 <= maximum <= 128, "invalid_arguments")
            self._time(now)
            def change(g):
                eligible = [claim for claim, record in g["receipts"].items()
                            if now >= record["retain_until"] and claim not in g["inflight"]]
                for claim in eligible[:maximum]:
                    del g["receipts"][claim]
                return {"removed": min(maximum, len(eligible)), "remaining": max(0, len(eligible) - maximum)}
            return self._commit("game", change, fault)

    def seal(self, expected_epoch, *, fault=None):
        with self.lock:
            self._live(); self._epoch(expected_epoch)
            def change(r):
                self.require(expected_epoch == r["epoch"], "generation_conflict")
                self.require(r["epoch"] < self.MAX_EPOCH, "resource_limit")
                self.require(all(state == "closed" for state in r["boxes"].values()), "not_drained")
                r["sealed"] = True
                return r["epoch"] + 1
            return self._commit("relay", change, fault)

    def advance_game(self, target_epoch, *, fault=None):
        with self.lock:
            self._live(); self._epoch(target_epoch)
            def change(g):
                if target_epoch == g["epoch"]:
                    return target_epoch
                self.require(self.relay["sealed"] and target_epoch == self.relay["epoch"] + 1
                             and target_epoch == g["epoch"] + 1, "generation_conflict")
                self.require(not g["inflight"], "not_drained")
                g["epoch"], g["journal"] = target_epoch, set()
                return target_epoch
            return self._commit("game", change, fault)

    def advance_relay(self, target_epoch, *, fault=None):
        with self.lock:
            self._live(); self._epoch(target_epoch)
            def change(r):
                if target_epoch == r["epoch"]:
                    return target_epoch
                self.require(r["sealed"] and target_epoch == r["epoch"] + 1
                             and target_epoch == self.game["epoch"], "generation_conflict")
                r.update(epoch=target_epoch, sealed=False, boxes={}, pairings=set())
                return target_epoch
            return self._commit("relay", change, fault)

    def snapshot(self):
        with self.lock:
            self._live()
            return {"instance_id": self.instance_id, "relay": deepcopy(self.relay), "game": deepcopy(self.game)}

    def restart(self, *, intact=True, snapshot=None):
        with self.lock:
            self._live()
            self.require(type(intact) is bool, "invalid_arguments")
            candidate = self.snapshot() if snapshot is None else deepcopy(snapshot)
            self.require(isinstance(candidate, dict) and set(candidate) == {"instance_id", "relay", "game"},
                         "invalid_snapshot")
            self.require(candidate["instance_id"] == self.instance_id, "snapshot_mismatch")
            self.require(all(self._digest(candidate[owner]) == self.checkpoints.get(owner)
                             for owner in ("relay", "game")), "snapshot_mismatch")
            restored = type(self)()
            restored.relay, restored.game = candidate["relay"], candidate["game"]
            restored.instance_id = self.instance_id
            restored.checkpoints = self.checkpoints
            restored.healthy = intact
            self.retired = True
            return restored
