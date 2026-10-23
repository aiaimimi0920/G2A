"""现有 Relay 的显式动态轮换装配；保留有界旧邮箱回执，非网络服务。"""

from copy import deepcopy
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("rotating_relay_base", Path(__file__).with_name("relay_harness.py"))
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)
C, R = H.C, H.R


class RotatingRelayHarness(H.RelayHarness):
    MAX_ARCHIVED = 8
    RETENTION_MS = 60000

    def __init__(self, fixture, records=None, *, game=None):
        super().__init__(fixture, records, game=game)
        R.require(self.route_epoch is not None, "feature_unsupported")
        self.state.update(sealed=False, archives={})

    def _lookup_box(self, mailbox_id):
        return self.state["mailboxes"].get(mailbox_id) or self.state["archives"].get(mailbox_id)

    def _box(self, mailbox_id, identity):
        box = super()._box(mailbox_id, identity)
        if "archive_until" in box:
            R.require(self.state["last_now"] < box["archive_until"], "request_gone")
        return box

    def _selected_extensions(self, request, identity, now):
        if request["operation"] == "relay.register":
            prior = self.state["registrations"].get((R.principal_key(identity["principal"]), request["request_id"]))
            box = None if prior is None else self._box(prior["result"]["mailbox_id"], identity)
        else:
            field = "object_id" if request["operation"] == "permission.revoke" else "mailbox_id"
            box = self._box(request["payload"][field], identity)
        return box.get("archive_extensions", self.epoch_extensions) if box is not None else self.epoch_extensions

    def _register(self, request, identity, now):
        key = (R.principal_key(identity["principal"]), request["request_id"])
        R.require(not self.state["sealed"] or key in self.state["registrations"], "temporarily_unavailable")
        return super()._register(request, identity, now)

    def seal_epoch(self, expected_epoch, *, now, fault=None):
        C.validate_type("Nat", expected_epoch)
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            def seal():
                R.require(expected_epoch == self.route_epoch, "generation_conflict")
                R.require(expected_epoch < 9007199254740991, "resource_limit")
                R.require(all(box["state"] == "closed" for box in self.state["mailboxes"].values()), "permission_denied")
                R.require(len(self.state["archives"]) + len(self.state["mailboxes"]) <= self.MAX_ARCHIVED, "resource_limit")
                self.state["sealed"] = True
                return {"target_epoch": expected_epoch + 1}
            return self._transaction(seal, fault)

    def advance_game_epoch(self, target_epoch, *, now, fault=None):
        C.validate_type("Nat", target_epoch)
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"] and self.state["sealed"], "temporarily_unavailable")
            R.require(target_epoch == self.route_epoch + 1, "generation_conflict")
        return self.port.advance_route_epoch(target_epoch, fault=fault)

    def advance_relay_epoch(self, target_epoch, *, now, fault=None):
        C.validate_type("Nat", target_epoch)
        R.require(fault in (None, "before_commit", "after_commit"), "invalid_arguments")
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            if target_epoch == self.route_epoch:
                return {"epoch": target_epoch}
            R.require(self.state["sealed"] and target_epoch == self.route_epoch + 1
                      and self.port.route_epoch == target_epoch and self.port.healthy, "generation_conflict")
            R.require(len(self.state["archives"]) + len(self.state["mailboxes"]) <= self.MAX_ARCHIVED, "resource_limit")
            R.require(now <= 9007199254740991 - self.RETENTION_MS, "invalid_arguments")
            state, fixture, extensions = deepcopy(self.state), deepcopy(self.fixture), deepcopy(self.epoch_extensions)
            for mid, box in state["mailboxes"].items():
                box.update(archive_until=now + self.RETENTION_MS, archive_extensions=deepcopy(self.epoch_extensions))
                state["archives"][mid] = box
            state.update(mailboxes={}, pairings_used={}, sealed=False)
            fixture.update(relay_epoch_profile=target_epoch, relay_pairing_epochs={}, relay_pairings={})
            extensions[self.EPOCH_EXTENSION]["value"]["epoch"] = target_epoch
            if fault == "before_commit":
                raise H.InjectedFailure(fault)
            self.state, self.fixture, self.epoch_extensions = state, fixture, extensions
            self.route_epoch, self.pairings, self.pairing_epochs = target_epoch, {}, {}
            if fault == "after_commit":
                raise H.InjectedFailure(fault)
            return {"epoch": target_epoch}

    def enroll_epoch_pairing(self, proof, epoch):
        """可信新同意登记，不接受客户端自报的 proof 或从旧同意自动续权。"""
        C.validate_type("RelayPairingAuthorization", proof)
        C.validate_type("Nat", epoch)
        with self.lock:
            R.require(not self.state["retired"] and self.state["ledger_healthy"], "temporarily_unavailable")
            R.require(epoch == self.route_epoch and not self.state["sealed"], "generation_conflict")
            R.require(proof["proof_ref"] not in self.pairings and len(self.pairings) < self.MAX_MAILBOXES, "resource_limit")
            self.pairings[proof["proof_ref"]] = deepcopy(proof)
            self.pairing_epochs[proof["proof_ref"]] = epoch
            self.fixture["relay_pairing_epochs"] = deepcopy(self.pairing_epochs)

    def compact_archives(self, *, now, maximum=8, fault=None):
        R.require(type(maximum) is int and 1 <= maximum <= self.MAX_ARCHIVED, "invalid_arguments")
        with self.lock:
            self._maintain(now)
            R.require(self.state["ledger_healthy"], "temporarily_unavailable")
            def compact():
                expired = [mid for mid, box in self.state["archives"].items() if now >= box["archive_until"]]
                removed = set(expired[:maximum])
                for mid in removed:
                    del self.state["archives"][mid]
                self.state["credentials"] = {key: credential for key, credential in self.state["credentials"].items()
                    if credential["mailbox_id"] not in removed}
                self.state["registrations"] = {key: receipt for key, receipt in self.state["registrations"].items()
                    if receipt["result"]["mailbox_id"] not in removed}
                return {"removed": len(removed), "remaining": len(expired) - len(removed)}
            return self._transaction(compact, fault)
