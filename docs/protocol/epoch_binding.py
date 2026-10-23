"""代次参考模型的严格字节绑定端口；可信登记表不是生产认证实现。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
from uuid import uuid4

spec = importlib.util.spec_from_file_location("epoch_binding_codec", Path(__file__).with_name("codec.py"))
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)


class EpochBoundPort:
    VERSION = "g2a-epoch-binding-1"
    FIELDS = {"version", "authority", "instance_id", "epoch", "kind", "mailbox_id", "principal", "role"}

    def __init__(self, rotation, authority):
        self.model = rotation
        self.require = rotation.require
        self.require(type(authority) is str and 0 < len(authority) <= 128, "invalid_arguments")
        self.authority = authority
        self.epoch = rotation.relay["epoch"]
        self.records, self.owners = {}, {}
        self.readers = {}
        self.retired = False
        self._checkpoint()

    def _state(self):
        return {"authority": self.authority, "instance_id": self.model.instance_id,
                "epoch": self.epoch, "records": deepcopy(self.records), "owners": deepcopy(self.owners),
                "readers": deepcopy(self.readers)}

    def _checkpoint(self):
        # 与候选快照分离的可信锚点；不得从快照自报值重建。
        self.checkpoint = self.model._digest(self._state())

    def _sync(self):
        self.require(not self.retired, "temporarily_unavailable")
        self.model._live()
        current = self.model.relay["epoch"]
        self.require(current >= self.epoch, "generation_conflict")
        if current != self.epoch:
            # 只有 Relay 已完成切换才能回收旧凭据；跨 authority 间隙不重标记旧证据。
            self.records, self.owners = {}, {}
            self.epoch = current
            self._checkpoint()

    def _issue(self, kind, mailbox_id, principal, role):
        self.require(type(principal) is str and 0 < len(principal) <= 128, "invalid_arguments")
        self.require(len(self.records) < 64, "resource_limit")
        token = "epoch-fixture-" + str(uuid4())
        self.records[token] = {"version": self.VERSION, "authority": self.authority,
            "instance_id": self.model.instance_id, "epoch": self.epoch, "kind": kind,
            "mailbox_id": mailbox_id, "principal": principal, "role": role}
        self._checkpoint()
        return token

    def enroll_pairing(self, principal):
        """仅可信玩家同意端口调用，产生当前代次新证据。"""
        with self.model.lock:
            self._sync()
            self.require(not self.model.relay["sealed"], "request_gone")
            return self._issue("pairing", None, principal, "controller")

    def enroll_mailbox(self, identity, principal, role):
        """仅可信身份交付端口调用；controller 必须是原批准主体。"""
        with self.model.lock:
            self._sync()
            self.require(role in ("controller", "agent", "game"), "permission_denied")
            self.require(type(identity) is tuple and len(identity) == 2 and
                         type(identity[0]) is int and type(identity[1]) is int, "invalid_arguments")
            self.require(self.model.relay["boxes"].get(identity) == "open" and identity[0] == self.epoch,
                         "request_gone")
            if role == "controller":
                self.require(self.owners.get(identity) == principal, "permission_denied")
            return self._issue("mailbox", identity[1], principal, role)

    def binding_bytes(self, token):
        """可信凭据交付通道同时交付公开绑定，输出不含 token。"""
        with self.model.lock:
            self._sync()
            binding = self.records.get(token)
            if binding is None and token in self.readers:
                binding = self.readers[token]["binding"]
            self.require(binding is not None, "unauthenticated")
            return codec.canonical(deepcopy(binding))

    def _authorize(self, raw, token, kind, roles):
        self._sync()
        binding = self._decode_binding(raw)
        self.require(binding["epoch"] == self.epoch, "generation_conflict")
        evidence = self.records.get(token)
        self.require(evidence is not None, "unauthenticated")
        self.require(codec.canonical(binding) == codec.canonical(evidence), "permission_denied")
        self.require(binding["kind"] == kind and binding["role"] in roles, "permission_denied")
        return binding

    def _decode_binding(self, raw):
        self.require(type(raw) is bytes and len(raw) <= 4096, "invalid_arguments")
        binding = codec.decode(raw)
        self.require(type(binding) is dict and set(binding) == self.FIELDS, "invalid_arguments")
        self.require(binding["version"] == self.VERSION, "unsupported_version")
        self.model._epoch(binding["epoch"])
        for field in ("authority", "instance_id", "principal", "role", "kind"):
            self.require(type(binding[field]) is str and 0 < len(binding[field]) <= 128, "invalid_arguments")
        self.require(binding["kind"] in ("pairing", "mailbox"), "invalid_arguments")
        mailbox = binding["mailbox_id"]
        self.require(mailbox is None if binding["kind"] == "pairing" else
                     type(mailbox) is int and 1 <= mailbox <= self.model.MAX_MAILBOXES, "invalid_arguments")
        self.require(binding["authority"] == self.authority and binding["instance_id"] == self.model.instance_id,
                     "permission_denied")
        return binding

    def enroll_receipt_reader(self, claim, principal, *, now, expires_at):
        """独立可信读权批准，只绑定原主体的一条回执，不授予执行或关闭权限。"""
        with self.model.lock:
            self._sync()
            self.require(type(claim) is tuple and len(claim) == 2 and type(claim[1]) is tuple
                         and len(claim[1]) == 2 and claim[1][0] == principal, "permission_denied")
            self.require(type(expires_at) is int and type(now) is int and now < expires_at <= self.model.MAX_EPOCH,
                         "invalid_arguments")
            self.model.receipt(claim, now=now)
            self.require(expires_at - now <= 300000, "invalid_arguments")
            self.require(len(self.readers) < 64, "resource_limit")
            token = "receipt-fixture-" + str(uuid4())
            binding = {"version": self.VERSION, "authority": self.authority, "instance_id": self.model.instance_id,
                "epoch": claim[0][0], "kind": "mailbox", "mailbox_id": claim[0][1],
                "principal": principal, "role": "receipt_reader"}
            self.readers[token] = {"binding": binding, "claim": claim, "expires_at": expires_at, "active": True}
            self._checkpoint()
            return token

    def query_receipt(self, raw, token, request_id, *, now):
        with self.model.lock:
            self._sync()
            binding = self._decode_binding(raw)
            reader = self.readers.get(token)
            self.require(reader is not None, "unauthenticated")
            self.require(codec.canonical(binding) == codec.canonical(reader["binding"])
                         and request_id == reader["claim"][1][1], "permission_denied")
            self.model._time(now)
            self.require(reader["active"] and now < reader["expires_at"], "permission_denied")
            return self.model.receipt(reader["claim"], now=now)

    def revoke_receipt_reader(self, token):
        """可信读权 owner 的撤销端口，不是公开 wire 操作。"""
        with self.model.lock:
            self._sync()
            self.require(token in self.readers, "permission_denied")
            self.readers[token]["active"] = False
            self._checkpoint()

    def compact_receipt_readers(self, *, now, maximum=16):
        with self.model.lock:
            self._sync()
            self.require(type(maximum) is int and 1 <= maximum <= 64, "invalid_arguments")
            self.model._time(now)
            keys = [key for key, reader in self.readers.items()
                    if not reader["active"] or now >= reader["expires_at"]]
            for key in keys[:maximum]:
                del self.readers[key]
            self._checkpoint()
            return {"removed": min(maximum, len(keys)), "remaining": max(0, len(keys) - maximum)}

    def register(self, raw, token):
        with self.model.lock:
            binding = self._authorize(raw, token, "pairing", {"controller"})
            identity = self.model.register(binding["epoch"], token)
            self.owners[identity] = binding["principal"]
            self._checkpoint()
            return identity

    def claim(self, raw, token, request_id):
        with self.model.lock:
            binding = self._authorize(raw, token, "mailbox", {"controller", "agent"})
            self.require(type(request_id) is str and 0 < len(request_id) <= 128, "invalid_arguments")
            identity = (binding["epoch"], binding["mailbox_id"])
            return self.model.claim(identity, (binding["principal"], request_id))

    def close(self, raw, token):
        with self.model.lock:
            binding = self._authorize(raw, token, "mailbox", {"controller"})
            identity = (binding["epoch"], binding["mailbox_id"])
            self.require(self.owners.get(identity) == binding["principal"], "permission_denied")
            self.model.close(identity)

    def snapshot(self):
        """可信内存快照含凭据，不能通过公开 binding_bytes 或 wire 交付。"""
        with self.model.lock:
            self._sync()
            return {"binding": self._state(), "model_checkpoints": deepcopy(self.model.checkpoints)}

    def restart(self, restored_model, *, snapshot):
        """先恢复代次模型，再以独立凭据锚点恢复本端口；错误不消费旧端口恢复权。"""
        with self.model.lock, restored_model.lock:
            self.require(not self.retired and self.model.retired, "temporarily_unavailable")
            restored_model._live()
            self.require(restored_model.instance_id == self.model.instance_id, "snapshot_mismatch")
            self.require(type(snapshot) is dict and set(snapshot) == {"binding", "model_checkpoints"}, "invalid_snapshot")
            candidate = deepcopy(snapshot)
            state = candidate["binding"]
            self.require(self.model._digest(state) == self.checkpoint, "snapshot_mismatch")
            self.require(candidate["model_checkpoints"] == restored_model.checkpoints and
                         all(restored_model._digest(getattr(restored_model, owner)) == restored_model.checkpoints.get(owner)
                             for owner in ("relay", "game")), "snapshot_mismatch")
            self.require(state["epoch"] == restored_model.relay["epoch"] and
                         set(state["owners"]) == set(restored_model.relay["boxes"]), "snapshot_mismatch")
            restored = type(self)(restored_model, self.authority)
            restored.records, restored.owners = state["records"], state["owners"]
            restored.readers = state["readers"]
            restored._checkpoint()
            self.retired = True
            return restored
