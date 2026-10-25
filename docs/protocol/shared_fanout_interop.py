"""共享授权域 fanout 的可信管道装配；重绑依赖真实恢复链，不是公开管理 API。"""

import base64
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = load("shared_fanout_interop_model", "revoke_fanout.py")
G = load("shared_fanout_local_fixture", "shared_grant_interop.py")


class SharedFanoutInteropFixture:
    def submit(self, frame):
        try:
            return self.dispatch(frame)
        except (M.C.ContractError, G.M.C.ContractError) as error:
            return {"fixture_rejected": error.code}

    def dispatch(self, frame):
        action = frame["action"]
        if action == "start":
            self.owners = {name: G.SharedGrantInteropFixture() for name in ("shared", "other")}
            descriptions = {name: owner.dispatch({"action": "start"}) for name, owner in self.owners.items()}
            self.player = descriptions["shared"]["player"]
            self.model = M.SessionRevokeFanout(self.player)
            self.ports, self.snapshots = {}, {}
            return descriptions
        if action == "local":
            return self.owners[frame["owner"]].submit(frame["command"])
        if action == "register":
            for name, fixture in self.owners.items():
                for sid, child in fixture.owner.sessions.items():
                    key = self.model.register(child, "player-fixture")
                    self.ports[key] = (name, sid)
            return {"coordinator_id": self.model.coordinator_id, **self.model.catalogue(player=self.player)}
        if action == "begin":
            return self.model.begin(frame["operation_id"], frame["targets"], player=self.player,
                                    catalogue_revision=frame["catalogue_revision"], object_type="grant")
        if action == "deliver":
            raw = base64.b64decode(frame["raw"], validate=True)
            M.C.validate_request(raw)
            item = self.model.records[frame["operation_id"]]["items"][frame["target"]]
            if raw != item["raw"]:
                return {"fixture_rejected": "id_conflict"}
            return self.model.deliver(frame["operation_id"], frame["target"], player=self.player, now=1000,
                                      remote_fault=frame.get("fault"), lose_ack=frame.get("lose_ack", False))
        if action == "rebind":
            name, sid = self.ports[frame["target"]]
            return {"target": self.model.rebind_target(frame["target"], self.owners[name].owner.sessions[sid],
                                                        "player-fixture", player=self.player)}
        if action == "snapshot":
            self.snapshots[frame["name"]] = self.model.snapshot()
            return {"saved": True}
        if action == "restart":
            snapshot = self.snapshots[frame["snapshot"]] if "snapshot" in frame else None
            self.model = self.model.restart_from_mock_ledger(snapshot=snapshot)
            return {"restarted": True}
        if action == "retire":
            return self.model.retire_target(frame["target"], player=self.player, expected_catalogue_revision=frame["catalogue_revision"])
        if action == "observe":
            return {name: fixture.dispatch({"action": "observe"}) for name, fixture in self.owners.items()}
        raise ValueError("fixture_command_unknown")
