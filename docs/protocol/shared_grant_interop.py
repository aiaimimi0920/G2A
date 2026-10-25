"""共享 Grant 候选 profile 的可信管道夹具；命令不是公网操作。"""

import base64
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = load("shared_grant_interop_model", "shared_grant_authority.py")
F = load("shared_grant_interop_fixtures", "fixtures.py")
ERRORS = load("shared_grant_interop_errors", "error_mapping.py")


class SharedGrantInteropFixture:
    def submit(self, frame):
        try:
            return self.dispatch(frame)
        except M.C.ContractError as error:
            return {"fixture_rejected": error.code}
        except (M.SharedGrantFault, M.U.A.M.SimulatedCrash) as error:
            return {"fixture_fault": str(error)}

    def dispatch(self, frame):
        action, now = frame["action"], frame.get("now", 1000)
        if action == "start":
            fixture = F.core_fixture(["core.session", "core.events", "actions", "multi-session"])
            self.owner = M.SharedGrantAuthority(fixture)
            self.snapshots, self.old_ports = {}, []
            return {"version": "fixture-only", "grant_id": fixture["grant"]["grant_id"],
                    **{key: fixture[key] for key in ("player", "agent", "game")}}
        if action == "issue":
            return self.owner.issue_invitation(frame["session_id"], now=now)
        if action == "finish":
            return self.owner.finish_admission(frame["session_id"], now=now)
        if action == "wire":
            raw = base64.b64decode(frame["raw"], validate=True)
            request = M.C.validate_request(raw)
            try:
                reply = self.owner.submit(raw, frame["credential"], now=now,
                                          session_id=frame.get("session_id"), fault=frame.get("fault"))
            except M.C.ContractError as error:
                reply = {"request_id": request["request_id"],
                         "error": ERRORS.boundary_error(error.code, knowledge="not_accepted")}
                M.C.validate_reply(request["operation"], request["request_id"], reply)
                reply = M.C.codec.canonical(reply)
            return {"reply": base64.b64encode(reply).decode("ascii")}
        if action == "execute":
            result = self.owner.execute(frame["session_id"], frame["operation"], "worker-1", now=now,
                                        **{key: frame[key] for key in ("ticket", "step", "crash") if key in frame})
            return {"result": result}
        if action == "snapshot":
            self.snapshots[frame["name"]] = self.owner.snapshot()
            return {"saved": True}
        if action == "restart":
            old = list(self.owner.sessions.values())
            self.owner = self.owner.restart_from_mock_ledger(
                snapshot=self.snapshots[frame["snapshot"]] if "snapshot" in frame else None)
            self.old_ports.extend(old)
            return {"restarted": True}
        if action == "old_port_probe":
            self.old_ports[0].delivery(self.owner.fixture["agent"], now=now)
            return {"unexpectedly_live": True}
        if action == "old_action_probe":
            child = next(c for c in self.old_ports if c.state["session"]["session_id"] == frame["session_id"])
            child.action_model.execute("step", "worker-1", now=now, ticket=frame["ticket"], step=2)
            return {"unexpectedly_executable": True}
        if action == "observe":
            self.owner._live()
            return {"grant_state": self.owner.state["grant"]["state"],
                "grant_revision": self.owner.state["grant"]["revision"],
                "issued": sum(i["state"] == "issued" for i in self.owner.state["invitations"].values()),
                "revoked_invitations": sum(i["state"] == "revoked" for i in self.owner.state["invitations"].values()),
                "sessions": {sid: {"state": c.state["session"]["state"], "ready": c.state["session"]["ready"],
                    "sequence": c.state["session"]["sequence"], "world_effects": len(c.action_model.model.world),
                    "read_revision": c.state["result_access_revision"], "authorized": c.action_model.model.authorized,
                    "action_state": None if c.action_model.model.action is None else c.action_model.model.action["state"]}
                    for sid, c in self.owner.sessions.items()}}
        raise ValueError("fixture_command_unknown")
