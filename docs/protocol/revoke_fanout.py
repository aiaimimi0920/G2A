"""候选跨 authority 会话、Grant、结果读权与明确能力撤销；不增加公开操作。"""

from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

spec = importlib.util.spec_from_file_location("fanout_session", Path(__file__).with_name("session_harness.py"))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
C, R = S.C, S.R


class FanoutFault(RuntimeError):
    pass


class SessionRevokeFanout:
    def __init__(self, player):
        C.validate_type("Principal", player)
        self.player = deepcopy(player)
        self.targets, self.records = {}, {}
        self.retired_targets = {}
        self.catalogue_revision = 0
        self.lock = RLock()
        self.retired = False
        self.healthy = True
        self.coordinator_id = str(uuid4())
        # 可信恢复锚点独立于可回滚快照；实际存储必须原子提交账本与锚点。
        self.checkpoints = {}
        self._checkpoint()

    def _live(self):
        R.require(self.healthy and not self.retired, "temporarily_unavailable")

    @staticmethod
    def _digest(value):
        def normalize(item):
            kind = type(item)
            if kind is dict:
                pairs = [(normalize(key), normalize(val)) for key, val in item.items()]
                return ["map", sorted(pairs, key=lambda pair: repr(pair[0]))]
            if kind is list:
                return ["list", [normalize(val) for val in item]]
            if kind is bytes:
                return ["bytes", item.hex()]
            if item is None:
                return ["null"]
            if kind in (str, int, bool):
                return [kind.__name__, item]
            R.require(False, "invalid_snapshot")
        return sha256(json.dumps(normalize(value), ensure_ascii=False,
                                 separators=(",", ":")).encode("utf-8")).hexdigest()

    def _checkpoint(self):
        self.checkpoints["ledger"] = self._digest(self.snapshot())

    def _owner(self, player):
        self._live()
        R.require(C.codec.canonical(player) == C.codec.canonical(self.player), "permission_denied")

    @staticmethod
    def binding(port):
        session = port.state["session"]
        return {"instance": deepcopy(session["scope"]["instance"]), "session_id": session["session_id"],
                "grant_id": port.state["grant"]["grant_id"],
                "scope_digest": C.codec.digest("scope", session["scope"]), "player": deepcopy(session["scope"]["player"])}

    def register(self, port, credential):
        """可信登记，不接受网络调用方传入 URL、authority 身份或凭据映射。"""
        with self.lock:
            self._live()
            with port.lock:
                binding = self.binding(port)
                identity = port._identity(credential)
            R.require(identity["role"] == "player" and identity["principal"] == self.player == binding["player"],
                      "permission_denied")
            key = sha256(C.codec.canonical(binding)).hexdigest()
            R.require(key not in self.retired_targets, "request_gone")
            old = self.targets.get(key)
            R.require(old is None or (old["port"] is port and old["credential"] == credential), "id_conflict")
            if old is not None:
                return key
            R.require(len(self.targets) < 16 and self.catalogue_revision < C.codec.MAX_INTEGER, "resource_limit")
            self.targets[key] = {"binding": binding, "port": port, "credential": credential}
            self.catalogue_revision += 1
            self._checkpoint()
            return key

    def catalogue(self, *, player):
        with self.lock:
            self._owner(player)
            return {"revision": self.catalogue_revision,
                    "targets": {key: deepcopy(target["binding"]) for key, target in self.targets.items()}}

    def retire_target(self, key, *, player, expected_catalogue_revision, fault=None):
        """明确移出未来选择，不撤销远端权限；未决意图不可通过目录维护遗忘。"""
        with self.lock:
            self._owner(player)
            C.validate_type("Id", key)
            R.require(type(expected_catalogue_revision) is int and
                      0 <= expected_catalogue_revision <= C.codec.MAX_INTEGER, "invalid_arguments")
            R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
            old = self.retired_targets.get(key)
            if old is not None:
                R.require(old["expected_catalogue_revision"] == expected_catalogue_revision, "id_conflict")
                return deepcopy(old["receipt"])
            R.require(expected_catalogue_revision == self.catalogue_revision, "generation_conflict")
            R.require(key in self.targets, "permission_denied")
            R.require(all(key not in record["items"] or record["items"][key]["state"] == "acknowledged"
                          for record in self.records.values()), "not_drained")
            R.require(len(self.retired_targets) < 64 and self.catalogue_revision < C.codec.MAX_INTEGER, "resource_limit")
            receipt = {"target": key, "state": "retired", "catalogue_revision": self.catalogue_revision + 1}
            tombstone = {"binding": deepcopy(self.targets[key]["binding"]),
                         "expected_catalogue_revision": expected_catalogue_revision, "receipt": receipt}
            if fault == "before_commit":
                raise FanoutFault(fault)
            self.retired_targets[key] = tombstone
            del self.targets[key]  # 只释放可信端口/凭据引用，保留独立接收方及历史协调记录。
            self.catalogue_revision += 1
            self._checkpoint()
            if fault == "after_commit":
                raise FanoutFault(fault)
            return deepcopy(receipt)

    def begin(self, operation_id, targets, *, player, catalogue_revision, object_type="session", capability_ids=None):
        """调用者已认证的玩家只可选择可信登记目标；每目标冻结独立 CAS revision。"""
        with self.lock:
            self._owner(player)
            C.validate_type("Id", operation_id)
            R.require(type(catalogue_revision) is int and 0 <= catalogue_revision <= C.codec.MAX_INTEGER,
                      "invalid_arguments")
            R.require(type(object_type) is str and object_type in {"session", "grant", "result_read", "capability"}, "invalid_arguments")
            R.require(type(targets) is dict and 1 <= len(targets) <= 16, "invalid_arguments")
            for key, revision in targets.items():
                C.validate_type("Id", key)
                R.require(type(revision) is int and 1 <= revision <= C.codec.MAX_INTEGER, "invalid_arguments")
            if object_type == "capability":
                R.require(type(capability_ids) is dict and capability_ids.keys() == targets.keys(), "invalid_arguments")
                for action_id in capability_ids.values():
                    C.validate_type("Id", action_id)
            else:
                R.require(capability_ids is None, "invalid_arguments")
            old = self.records.get(operation_id)
            if old is not None:
                R.require(old["selection"] == targets and old["object_type"] == object_type and
                          old["capability_ids"] == capability_ids and old["catalogue_revision"] == catalogue_revision,
                          "id_conflict")
                return self.view(operation_id, player=player)
            R.require(catalogue_revision == self.catalogue_revision, "generation_conflict")
            for key in targets:
                R.require(key not in self.retired_targets, "request_gone")
                R.require(key in self.targets, "invalid_arguments")
            if object_type == "capability":
                for key, action_id in capability_ids.items():
                    port = self.targets[key]["port"]
                    with port.lock:
                        R.require(C.codec.canonical(self.binding(port)) == C.codec.canonical(self.targets[key]["binding"]),
                                  "permission_denied")
                        scope = port.state["session"]["scope"]
                        R.require("actions" in scope["features"] and action_id in scope["action_ids"], "permission_denied")
            R.require(len(self.records) < 64, "resource_limit")
            items = {}
            for key, revision in sorted(targets.items()):
                target = self.targets[key]
                object_id = capability_ids[key] if object_type == "capability" else target["binding"]["grant_id" if object_type == "grant" else "session_id"]
                rid = "fanout-" + sha256(C.codec.canonical([self.coordinator_id, operation_id, key])).hexdigest()
                request = {"version": target["port"].state["session"]["scope"]["version"],
                           "operation": "permission.revoke", "request_id": rid, "extensions": {},
                           "payload": {"object_type": object_type, "object_id": object_id,
                                       "expected_revision": revision}}
                raw = C.codec.canonical(request)
                C.validate_request(raw)
                items[key] = {"raw": raw, "request_id": rid, "state": "pending", "revision": revision,
                              "object_type": object_type, "object_id": object_id}
            self.records[operation_id] = {"selection": deepcopy(targets), "object_type": object_type,
                                          "capability_ids": deepcopy(capability_ids), "items": items,
                                          "catalogue_revision": catalogue_revision}
            self._checkpoint()
            return self.view(operation_id, player=player)

    def view(self, operation_id, *, player):
        with self.lock:
            self._owner(player)
            record = self.records.get(operation_id)
            R.require(record is not None, "permission_denied")
            states = {key: item["state"] for key, item in record["items"].items()}
            complete = sum(state == "acknowledged" for state in states.values())
            return {"operation_id": operation_id, "object_type": record["object_type"],
                    "catalogue_revision": record["catalogue_revision"], "state": "done" if complete == len(states) else
                    "partial" if complete else "pending", "targets": states}

    def deliver(self, operation_id, key, *, player, now, remote_fault=None, lose_ack=False):
        with self.lock:
            self._owner(player)
            C.validate_type("Nat", now)
            R.require(type(lose_ack) is bool and remote_fault in (None, "before_commit", "after_commit"), "invalid_arguments")
            record = self.records.get(operation_id)
            R.require(record is not None and key in record["items"], "permission_denied")
            item = record["items"][key]
            if item["state"] == "acknowledged":
                return self.view(operation_id, player=player)
            target = self.targets[key]
            # 接收方锁覆盖绑定检查与受理；仅在协调器侧提前检查存在换代 TOCTOU。
            with target["port"].lock:
                R.require(C.codec.canonical(self.binding(target["port"])) == C.codec.canonical(target["binding"]),
                          "permission_denied")
                item["state"] = "unknown"
                self._checkpoint()  # 必须先保存派发知识，再跨越独立接收方提交边界。
                try:
                    raw_reply = target["port"].submit(item["raw"], target["credential"], now=now, fault=remote_fault)
                except Exception:
                    # 远端故障可能已提交，保持 unknown，不能回滚另一 authority。
                    return self.view(operation_id, player=player)
            try:
                reply = C.codec.decode(raw_reply)
                C.validate_reply("permission.revoke", item["request_id"], reply)
                result = reply.get("result", {})
                valid = (result.get("object_type") == item["object_type"] and result.get("object_id") == item["object_id"]
                         and result.get("state") == ("closed" if item["object_type"] == "session" else "revoked")
                         and result.get("revision") == item["revision"] + 1)
            except Exception:
                # 无响应/拒绝不能证明原请求未提交，也不能撤销其他 authority 已提交事实。
                valid = False
            if valid and not lose_ack:
                item["state"] = "acknowledged"
                self._checkpoint()
            return self.view(operation_id, player=player)

    def snapshot(self):
        with self.lock:
            self._live()
            # 只导出账本；不复制独立接收方，不允许快照提供凭据、端口或恢复锚点。
            return {"coordinator_id": self.coordinator_id, "player": deepcopy(self.player),
                    "targets": {key: deepcopy(target["binding"]) for key, target in self.targets.items()},
                    "records": deepcopy(self.records), "catalogue_revision": self.catalogue_revision,
                    "retired_targets": deepcopy(self.retired_targets)}

    def restart_from_mock_ledger(self, *, intact=True, snapshot=None):
        with self.lock:
            self._live()
            R.require(type(intact) is bool, "invalid_arguments")
            candidate = self.snapshot() if snapshot is None else deepcopy(snapshot)
            R.require(type(candidate) is dict and set(candidate) ==
                      {"coordinator_id", "player", "targets", "records", "catalogue_revision", "retired_targets"},
                      "invalid_snapshot")
            R.require(candidate["coordinator_id"] == self.coordinator_id and
                      self._digest(candidate) == self.checkpoints.get("ledger"), "snapshot_mismatch")
            restored = type(self)(self.player)
            restored.coordinator_id, restored.player = candidate["coordinator_id"], candidate["player"]
            restored.targets = {key: {"binding": binding, "port": self.targets[key]["port"],
                                      "credential": self.targets[key]["credential"]}
                                for key, binding in candidate["targets"].items()}
            restored.records = candidate["records"]
            restored.catalogue_revision = candidate["catalogue_revision"]
            restored.retired_targets = candidate["retired_targets"]
            restored.checkpoints = self.checkpoints
            restored.healthy = intact
            self.retired = True
            return restored
