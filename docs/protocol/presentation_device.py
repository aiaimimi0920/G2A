"""独立设备账本与 Renderer 假端口；设备效果不随 authority 事务回滚。"""

from copy import deepcopy
from threading import RLock


class PresentationDevice:
    NORMAL_RECEIPTS = 256
    RELEASE_RECEIPTS = 128  # 普通 acquire/renew 不能耗尽停止路径的预留。

    def __init__(self, device_id, player, require, *, visible=True):
        self.device_id, self.player, self.require = device_id, deepcopy(player), require
        self.lock = RLock()
        self.baseline_visible = self.actual_visible = visible
        self.manual_revision = 1
        self.epoch = 1
        self.occupations, self.tombstones, self.receipts = {}, set(), {}
        self.lease_revisions, self.expiry_facts = {}, {}
        self.reachable, self.retired, self.render_verified = True, False, True
        self.renderer_outcomes = []  # 可信 fixture: (applied, actual_visible)，失败也可能已改变显示。
        self.render_calls = 0
        self.render_failures = 0
        self.last_now = 0

    def _desired(self):
        return False if any(o["terms"]["mode"] == "hide_desktop" for o in self.occupations.values()) else self.baseline_visible

    def _render(self):
        self.render_calls += 1
        applied, actual = self.renderer_outcomes.pop(0) if self.renderer_outcomes else (True, self._desired())
        self.require(type(applied) is bool and type(actual) is bool, "invalid_arguments")
        self.actual_visible = actual
        success = applied and actual == self._desired()
        self.render_verified = success
        if not success:
            self.render_failures += 1
        return success

    def tick(self, now):
        with self.lock:
            self.require(not self.retired, "presentation_unavailable")
            self.require(type(now) is int and now >= self.last_now, "temporarily_unavailable")
            self.last_now = now
            expired = [key for key, value in self.occupations.items() if now >= value["deadline"]]
            for key in expired:
                self.expiry_facts[key] = {"lease_revision": self.occupations[key]["lease_revision"],
                                          "deadline": self.occupations[key]["deadline"]}
                self.tombstones.add(key)
                del self.occupations[key]
            if expired:
                self._render()

    def _receipt(self, payload, rid, applied):
        key = (payload["session_id"], payload["generation"])
        return {"session_id": payload["session_id"], "generation": payload["generation"], "operation_id": rid,
                "device_id": self.device_id, "manual_revision": self.manual_revision,
                "device_epoch": self.epoch, "lease_revision": self.lease_revisions.get(key, 0),
                "lease_deadline": self.occupations.get(key, {}).get("deadline", 0),
                "actual_visible": self.actual_visible, "applied": applied}

    def apply(self, operation, payload, rid, digest, *, now, current_revision=None):
        """仅由验证完设备/authority/Scope 的可信门调用；不接受客户端自报证明。"""
        with self.lock:
            self.tick(now)
            self.require(self.reachable, "temporarily_unavailable")
            self.require(operation in {"presentation.acquire", "presentation.renew", "presentation.release"}, "invalid_arguments")
            key = (payload["session_id"], payload["generation"])
            if operation != "presentation.release":
                self.require(payload["device_epoch"] == self.epoch, "approval_stale")
            receipt_key = (operation, rid)
            old = self.receipts.get(receipt_key)
            if old is not None:
                self.require(old["digest"] == digest, "id_conflict")
                if operation != "presentation.release":
                    self.require(key not in self.tombstones, "presentation_unavailable")
                return deepcopy(old["receipt"])
            releases = sum(op == "presentation.release" for op, _ in self.receipts)
            self.require(releases < self.RELEASE_RECEIPTS if operation == "presentation.release" else
                         len(self.receipts) - releases < self.NORMAL_RECEIPTS, "resource_limit")
            if operation == "presentation.acquire":
                self.require(key not in self.tombstones, "presentation_unavailable")
                self.require(now < payload["deadline"], "presentation_unavailable")
                self.require(payload["lease_revision"] == 1, "approval_stale")
                self.require(key not in self.occupations, "id_conflict")
                self.occupations[key] = deepcopy(payload)
                self.lease_revisions[key] = 1
                applied = self._render()
                if not applied:
                    del self.occupations[key]
                    self.tombstones.add(key)
            elif operation == "presentation.renew":
                self.require(key not in self.tombstones and key in self.occupations, "presentation_unavailable")
                current = self.occupations[key]
                self.require(payload["lease_revision"] == current_revision and
                             payload["lease_revision"] > current["lease_revision"], "approval_stale")
                self.require(all(payload[field] == current[field] for field in ("device_epoch", "terms", "scope_digest")), "permission_denied")
                self.require(now < current["deadline"] < payload["deadline"] and self.render_verified and
                             self.actual_visible == self._desired(), "presentation_unavailable")
                self.occupations[key] = deepcopy(payload)
                self.lease_revisions[key] = payload["lease_revision"]
                applied = True  # 条款未变，不重复调用 Renderer，更不续游戏会话。
            else:
                # 不论 acquire ACK 是否已到达，都先落 tombstone，随后才尝试 Renderer。
                self.tombstones.add(key)
                self.occupations.pop(key, None)
                applied = self._render()
            receipt = self._receipt(payload, rid, applied)
            self.receipts[receipt_key] = {"digest": digest, "receipt": receipt}
            return deepcopy(receipt)

    def prove_expiry(self, payload, horizon, *, now):
        """可信设备端口；网络不可达、仅过了旧期限或渲染失败都不是释放证明。"""
        with self.lock:
            self.tick(now)
            key = (payload["session_id"], payload["generation"])
            # 已验证的本地到期 tombstone 会拒绝连较新但未应用的更新；未收到 release ACK 则不能冒充到期。
            locally_expired = key in self.expiry_facts and key in self.tombstones
            if (not self.reachable or (now < horizon and not locally_expired) or key in self.occupations or
                    not self.render_verified or self.actual_visible != self._desired()):
                return None
            self.tombstones.add(key)
            return {"receipt": self._receipt(payload, "expiry-" + str(payload["generation"]), True),
                    "verified_at": now, "proof_deadline": horizon}

    def reconcile_stop(self, payload, *, now):
        """可信本地停止义务：收据耗尽后仍可收敛；不改写任何原操作结果。"""
        with self.lock:
            self.tick(now)
            if not self.reachable:
                return None
            key = (payload["session_id"], payload["generation"])
            already_stopped = key in self.tombstones and key not in self.occupations
            self.tombstones.add(key)
            self.occupations.pop(key, None)
            if not (already_stopped and self.render_verified and self.actual_visible == self._desired()) and not self._render():
                return None
            return {"kind": "local_reconciliation", "verified_at": now,
                    "receipt": self._receipt(payload, "reconcile-" + str(payload["generation"]), True)}

    def restart_from_mock_ledger(self, *, now, verify=None):
        """独立设备对象重启；保存的 token 不足以保留占用，旧对象立即退休。"""
        with self.lock:
            self.tick(now)
            restored = type(self)(self.device_id, self.player, self.require, visible=self.baseline_visible)
            for field in ("actual_visible", "manual_revision", "occupations", "tombstones", "receipts", "lease_revisions", "expiry_facts",
                          "renderer_outcomes", "render_calls", "render_failures", "render_verified", "reachable", "last_now"):
                setattr(restored, field, deepcopy(getattr(self, field)))
            restored.epoch = self.epoch + 1
            for key, occupation in list(restored.occupations.items()):
                if verify is not None and verify(deepcopy(occupation)):
                    occupation["device_epoch"] = restored.epoch
                else:
                    del restored.occupations[key]
                    restored.tombstones.add(key)
            self.retired = True
            restored._render()
            return restored

    def manual_change(self, visible, *, now):
        """可信本地玩家端口；立即更新最新意图，不依赖远端 ACK。"""
        with self.lock:
            self.require(type(visible) is bool, "invalid_arguments")
            self.tick(now)
            self.baseline_visible = visible
            self.manual_revision += 1
            if visible:
                for key, value in list(self.occupations.items()):
                    if value["terms"]["mode"] == "hide_desktop":
                        self.tombstones.add(key)
                        del self.occupations[key]
            return {"applied": self._render(), "actual_visible": self.actual_visible,
                    "manual_revision": self.manual_revision}
