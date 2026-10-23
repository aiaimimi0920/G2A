"""候选代次 profile 的可信管道夹具；维护命令不是正式 wire 操作。"""

import base64
import importlib.util
from pathlib import Path


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = load("epoch_interop_model", "epoch_rotation.py")
B = load("epoch_interop_binding", "epoch_binding.py")


class EpochInteropFixture:
    def __init__(self):
        self.model = M.EpochRotation()
        self.port = B.EpochBoundPort(self.model, "relay-epoch-fixture")
        self.claims = {}

    def credential(self, token):
        return {"credential": token, "binding": base64.b64encode(self.port.binding_bytes(token)).decode("ascii")}

    def submit(self, frame):
        try:
            action = frame["action"]
            if action == "describe":
                return {"instance_id": self.model.instance_id, "authority": self.port.authority,
                        "version": self.port.VERSION}
            if action == "pairing":
                return self.credential(self.port.enroll_pairing(frame["principal"]))
            if action == "credential":
                return self.credential(self.port.enroll_mailbox(tuple(frame["identity"]), frame["principal"], frame["role"]))
            if action == "receipt_reader":
                return self.credential(self.port.enroll_receipt_reader(self.claims[frame["claim"]], frame["principal"],
                    now=frame.get("now", 0), expires_at=frame["expires_at"]))
            if action == "receipt_revoke":
                self.port.revoke_receipt_reader(frame["credential"])
                return {"revoked": True}
            if action == "receipt_compact":
                return self.model.compact_receipts(now=frame["now"], maximum=frame.get("maximum", 128), fault=frame.get("fault"))
            if action == "wire":
                raw = base64.b64decode(frame["raw"], validate=True)
                token = frame["credential"]
                try:
                    operation = frame["operation"]
                    if operation == "register":
                        result = {"identity": list(self.port.register(raw, token))}
                    elif operation == "claim":
                        claim = self.port.claim(raw, token, frame["request_id"])
                        handle = "claim-" + str(len(self.claims) + 1)
                        self.claims[handle] = claim
                        result = {"claim": handle}
                    elif operation == "close":
                        self.port.close(raw, token)
                        result = {"closed": True}
                    elif operation == "receipt":
                        result = self.port.query_receipt(raw, token, frame["request_id"], now=frame.get("now", 0))
                    else:
                        raise M.RotationError("unsupported_operation")
                    reply = {"request_id": frame["request_id"], "result": result}
                except M.RotationError as error:
                    reply = {"request_id": frame["request_id"], "error": {"code": str(error)}}
                except B.codec.CodecError as error:
                    reply = {"request_id": frame["request_id"], "error": {"code": error.code}}
                return {"reply": base64.b64encode(B.codec.canonical(reply)).decode("ascii")}
            if action in ("begin", "finish"):
                getattr(self.model, action)(self.claims[frame["claim"]])
                return {"effects": self.model.game["effects"]}
            if action in ("seal", "advance_game", "advance_relay"):
                epoch = getattr(self.model, action)(frame["epoch"], fault=frame.get("fault"))
                return {"epoch": epoch}
            if action == "restart":
                binding = self.port.snapshot()
                restored = self.model.restart(snapshot=self.model.snapshot())
                self.port = self.port.restart(restored, snapshot=binding)
                self.model = restored
                return {"restarted": True, "effects": self.model.game["effects"]}
            if action == "observe":
                return {"relay_epoch": self.model.relay["epoch"], "game_epoch": self.model.game["epoch"],
                        "effects": self.model.game["effects"], "inflight": len(self.model.game["inflight"])}
            raise M.RotationError("unsupported_operation")
        except M.RotationFault as error:
            return {"fixture_fault": str(error)}
        except M.RotationError as error:
            return {"fixture_rejected": str(error)}
