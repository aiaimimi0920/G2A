"""跨 authority 候选组合的可信管道夹具；不新增公网入口。"""
import base64
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


M = load("fanout_interop_model", "revoke_fanout.py")
F = load("fanout_interop_fixtures", "fixtures.py")


class FanoutInteropFixture:
    def add_port(self, subject, *, session="s1", grant="g1", epoch="epoch-1", multi=False):
        fixture = F.core_fixture(["core.session", "core.events", "actions", "multi-session"] if multi else None)
        old_game = fixture["game"]
        def replace(value):
            if value == old_game:
                return F.principal(subject, "game")
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            if isinstance(value, list):
                return [replace(item) for item in value]
            return value
        fixture = replace(fixture)
        for scope in (fixture["scope"], fixture["grant"]["scope"], fixture["session"]["scope"]):
            scope["instance"]["epoch"] = epoch
        fixture["descriptor"]["instance"]["epoch"] = epoch
        fixture["session"].update(session_id=session, grant_id=grant, instance_epoch=epoch)
        fixture["grant"]["grant_id"] = grant
        fixture["grant"]["scope_digest"] = M.C.codec.digest("scope", fixture["scope"])
        port = M.S.SessionHarness(fixture, {})
        self.ports[self.model.register(port, "player-fixture")] = port

    def describe(self):
        catalogue = self.model.catalogue(player=self.player)
        return {"player": self.player, "version": "fixture-only", "coordinator_id": self.model.coordinator_id,
                "catalogue_revision": catalogue["revision"], "targets": catalogue["targets"]}

    def submit(self, frame):
        try:
            return self.dispatch(frame)
        except M.C.ContractError as error:
            return {"fixture_rejected": error.code}
        except M.FanoutFault as error:
            return {"fixture_fault": str(error)}

    def dispatch(self, frame):
        action = frame["action"]
        if action == "start":
            self.player = F.principal("alice", "player")
            self.model = M.SessionRevokeFanout(self.player)
            self.ports = {}
            self.snapshots = {}
            if frame.get("multi_session") is True:
                for index in (1, 2):
                    self.add_port("game-a", session="s" + str(index), grant="g" + str(index), multi=True)
            else:
                for subject in ("game-a", "game-b"):
                    self.add_port(subject)
            return self.describe()
        if action == "add_epoch_target":
            self.add_port("game-a", epoch="epoch-2", multi=True)
            return self.describe()
        if action == "catalogue":
            return self.model.catalogue(player=self.player)
        if action == "reregister":
            return {"registered": self.model.register(self.ports[frame["target"]], "player-fixture")}
        if action == "retire":
            return self.model.retire_target(frame["target"], player=self.player,
                expected_catalogue_revision=frame["catalogue_revision"], fault=frame.get("fault"))
        if action == "new_coordinator":
            # 新意图的独立协调器，不是丢弃旧协调账本后重新生成请求的恢复方式。
            self.model = M.SessionRevokeFanout(self.player)
            for port in self.ports.values():
                self.model.register(port, "player-fixture")
            return self.describe()
        if action == "begin":
            return self.model.begin(frame["operation_id"], frame["targets"], player=self.player,
                                    catalogue_revision=frame["catalogue_revision"], object_type=frame["object_type"],
                                    capability_ids=frame.get("capability_ids"))
        if action == "deliver":
            raw = base64.b64decode(frame["raw"], validate=True)
            M.C.validate_request(raw)
            item = self.model.records[frame["operation_id"]]["items"][frame["target"]]
            # JS 必须独立构造与冻结意图完全一致的字节，不能换对象或 CAS。
            if raw != item["raw"]:
                return {"fixture_rejected": "id_conflict"}
            return self.model.deliver(frame["operation_id"], frame["target"], player=self.player,
                                      now=1000, remote_fault=frame.get("fault"), lose_ack=frame.get("lose_ack", False))
        if action == "restart":
            snapshot = self.snapshots[frame["snapshot"]] if "snapshot" in frame else None
            self.model = self.model.restart_from_mock_ledger(snapshot=snapshot)
            return {"restarted": True, "coordinator_id": self.model.coordinator_id}
        if action == "snapshot":
            self.snapshots[frame["name"]] = self.model.snapshot()
            return {"saved": True}
        if action == "observe":
            return {key: {"session_state": port.state["session"]["state"], "grant_state": port.state["grant"]["state"],
                          "grant_revision": port.state["grant"]["revision"], "read_revision": port.state["result_access_revision"],
                          "capabilities_revision": port.state["session"]["capabilities_revision"],
                          "definitions": len(port.state["definitions"]), "sequence": port.state["session"]["sequence"]}
                    for key, port in self.ports.items()}
        raise ValueError("fixture_command_unknown")
