"""固定应用的独立启动效果账本；只写内存，不创建进程、命令或网络连接。"""

from copy import deepcopy
from hashlib import sha256
from threading import RLock


class LauncherPort:
    def __init__(self, checks, relations, player, agent):
        self.C, self.R = checks, relations
        self.lock = RLock()
        self.registration = {"application_registration": "fixture-companion", "revision": 1,
            "player": deepcopy(player), "agent": deepcopy(agent), "device_id": "device-a",
            "fixed_program": "fixture-only-program", "fixed_arguments": []}
        self.entries, self.effects, self.running = {}, {}, None
        self.outcomes = []  # 可信故障输入；不接受 wire 中的程序路径/参数/启动结果。
        self.start_calls = 0
        self.exited = set()
        self.sealed = False

    def binding(self):
        return deepcopy(self.registration)

    def available(self, binding):
        with self.lock:
            return (not self.sealed and self.running is not None and self.running.get("verified") is True and
                    self.running.get("process_ref") not in self.exited and
                    self.C.codec.canonical(binding) == self.C.codec.canonical(self.registration) ==
                    self.C.codec.canonical(self.running.get("binding")))

    def query(self, permit_ref, binding):
        with self.lock:
            entry = self.entries.get(permit_ref)
            if entry is None:
                return None
            self.R.require(self.C.codec.canonical(entry["binding"]) == self.C.codec.canonical(binding), "id_conflict")
            return deepcopy(entry)

    def start(self, permit_ref, binding):
        """只供已核验许可的 authority 调用；已消费但无结果时永不再产生效果。"""
        with self.lock:
            self.R.require(not self.sealed, "temporarily_unavailable")
            old = self.query(permit_ref, binding)
            if old is not None:
                return old
            self.R.require(len(self.entries) < 128, "resource_limit")
            entry = {"binding": deepcopy(binding), "state": "unknown"}
            self.entries[permit_ref] = entry  # 先消费，后效果；未知不能从 entries 中删除。
            self.start_calls += 1
            if self.C.codec.canonical(binding) != self.C.codec.canonical(self.registration):
                entry.update(state="failed", reason="registration_changed")
            elif self.available(binding):
                entry.update(state="done", result={"status": "already_running"})
            elif self.running is not None or any(ref != permit_ref and prior["state"] == "unknown" for ref, prior in self.entries.items()):
                # 换 offer/许可也不能绕过同一固定应用尚未解决的启动；不另开一个假进程。
                entry.update(state="failed", reason="previous_launch_unresolved")
            else:
                outcome = self.outcomes.pop(0) if self.outcomes else "started"
                if outcome == "failed":
                    entry.update(state="failed", reason="start_failed")
                elif outcome not in {"unknown_before_effect", "started", "unknown_after_effect", "wrong_identity"}:
                    # 未知端口结果不猜测为成功或未发生；许可仍已消费。
                    return deepcopy(entry)
                elif outcome != "unknown_before_effect":
                    # 完整许可引用参与摘要；不拼接超长 ID，也不截断后产生别名。
                    process_ref = "fixture-process-" + sha256(permit_ref.encode("utf-8")).hexdigest()
                    process = {"process_ref": process_ref, "binding": deepcopy(binding),
                               "verified": outcome == "started"}
                    if outcome == "wrong_identity":
                        process["binding"]["agent"]["subject"] = "wrong-fixture-agent"
                    self.effects[permit_ref] = deepcopy(process)
                    self.running = process
                    if outcome == "started":
                        entry.update(state="done", result={"status": "started"})
                    elif outcome == "wrong_identity":
                        entry.update(state="failed", reason="process_identity_mismatch")
            return deepcopy(entry)

    def seal(self):
        """可信不可逆退役屏障；无未决且全部进程有退出见证才允许封存。"""
        with self.lock:
            if self.sealed:
                return {"sealed": True}
            self.R.require(self.running is None and all(entry["state"] in {"done", "failed"}
                           for entry in self.entries.values()), "temporarily_unavailable")
            self.R.require(all(process["process_ref"] in self.exited for process in self.effects.values()),
                           "temporarily_unavailable")
            self.sealed = True
            return {"sealed": True}

    def compact_sealed(self, maximum=64):
        """仅在不可逆屏障后回收独立内存账本；不创建替代端口、不终止进程。"""
        self.R.require(type(maximum) is int and 1 <= maximum <= 128, "invalid_arguments")
        with self.lock:
            self.R.require(self.sealed, "permission_denied")
            selected = sorted(self.entries)[:maximum]
            for ref in selected:
                process = self.effects.pop(ref, None)
                if process is not None:
                    self.exited.discard(process["process_ref"])
                del self.entries[ref]
            return {"removed": len(selected), "remaining": len(self.entries), "sealed": True}

    def record_exit(self, process_ref):
        """可信进程退出见证；精确关联已知效果，不是 wire 自报的停止命令。"""
        self.C.validate_type("Id", process_ref)
        with self.lock:
            self.R.require(any(process["process_ref"] == process_ref for process in self.effects.values()), "permission_denied")
            self.exited.add(process_ref)
            if self.running is not None and self.running.get("process_ref") == process_ref:
                self.running = None
            return {"state": "exited", "process_ref": process_ref}

    def observe_process(self, process_ref, binding):
        """历史启动成功不等于当前存活；无退出见证时缺失只能是 unknown。"""
        with self.lock:
            known = next((process for process in self.effects.values() if process["process_ref"] == process_ref), None)
            if known is None or self.C.codec.canonical(known["binding"]) != self.C.codec.canonical(binding):
                return "unknown"
            if process_ref in self.exited:
                return "exited"
            if self.running is not None and self.running.get("process_ref") == process_ref and self.available(binding):
                return "running"
            return "unknown"

    def verify_existing_effect(self, permit_ref):
        """可信进程握手假端口，仅验证已存在且与该许可精确关联的效果；不会补启动。"""
        with self.lock:
            entry, process = self.entries.get(permit_ref), self.effects.get(permit_ref)
            if self.sealed:
                return False
            if entry is None or entry["state"] != "unknown" or process is None:
                return False
            if process["process_ref"] in self.exited or self.running is None or self.running.get("process_ref") != process["process_ref"]:
                return False
            if (self.C.codec.canonical(entry["binding"]) != self.C.codec.canonical(process["binding"]) or
                    self.C.codec.canonical(entry["binding"]) != self.C.codec.canonical(self.registration) or
                    self.C.codec.canonical(entry["binding"]) != self.C.codec.canonical(self.running.get("binding"))):
                return False
            process["verified"] = True
            self.running = deepcopy(process)
            entry.update(state="done", result={"status": "started"})
            return True
