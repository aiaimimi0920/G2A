"""Python 假服务与独立 JavaScript 编码/客户端验证；仅子进程管道，无网络或真实凭据。"""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "docs/protocol" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def serve():
    session = load("interop_session", "session_harness.py")
    fixtures = load("interop_fixtures", "fixtures.py")
    errors = load("interop_errors", "error_mapping.py")
    harness = session.SessionHarness(fixtures.core_fixture(), {})
    checks, fault_type = session.C, session.S.H.InjectedFailure
    codec = session.C.codec
    while True:
        line = sys.stdin.buffer.readline(2_097_153)
        if not line:
            return 0
        if len(line) > 2_097_152:
            raise ValueError("fixture_frame_limit")
        frame = json.loads(line)
        kind = frame["kind"]
        if kind == "codec":
            try:
                value = codec.decode(base64.b64decode(frame["raw"], validate=True))
                output = {"canonical": codec.canonical(value).hex(), "digest": codec.digest("message", value)}
            except codec.CodecError as error:
                output = {"error": error.code}
        elif kind == "wire":
            raw = base64.b64decode(frame["raw"], validate=True)
            request = codec.decode(raw)
            try:
                checks.validate_request(raw)
                reply = harness.submit(raw, frame["credential"], now=frame.get("now", 1000), fault=frame.get("fault"))
                output = {"reply": base64.b64encode(reply).decode("ascii")}
            except fault_type:
                output = {"fixture_fault": frame["fault"]}
            except checks.ContractError as error:
                # submit 的异常已回滚协议事务；这里只映射此测试服务可证明的提交知识。
                reply = {"request_id": request["request_id"], "error": errors.boundary_error(error.code, knowledge="not_accepted")}
                checks.validate_reply(request["operation"], request["request_id"], reply)
                output = {"reply": base64.b64encode(codec.canonical(reply)).decode("ascii")}
        elif kind == "effect":
            game = getattr(harness, "game", harness)
            game.execute("step", "worker-1", now=1000, ticket=frame["ticket"], step=frame["step"])
            authority = getattr(game, "session", None) or game
            output = {"world_effects": len(authority.action_model.model.world)}
        elif kind == "compact":
            authority = getattr(harness, "session", None) or harness
            authority.compact_through(authority.state["session"]["sequence"])
            output = {"compacted": True}
        elif kind == "membership_proof":
            authority = getattr(harness, "session", None) or harness
            authority.membership_proofs[frame["payload"]["membership_proof_ref"]] = frame["payload"]
            output = {"registered_fixture_proof": True}
        elif kind == "admission_start":
            admission = load("interop_admission", "admission_harness.py")
            fixture = fixtures.core_fixture(["core.session", "core.events"] if frame.get("core_only") is True else None)
            if frame.get("core_only") is True:
                fixture.pop("action")
            harness = admission.AdmissionHarness(fixture)
            checks, fault_type = admission.C, admission.U.S.H.InjectedFailure
            output = {"started_empty_authority": True}
        elif kind == "admission_decision":
            game = getattr(harness, "game", harness)
            game.decisions[frame["payload"]["decision_ref"]] = {"player": fixtures.core_fixture()["player"], "payload": frame["payload"]}
            if hasattr(game, "launcher") and frame["payload"]["launch_permission"]:
                game.decisions[frame["payload"]["decision_ref"]]["launch_binding"] = game.launcher.binding()
            output = {"registered_fixture_decision": True}
        elif kind == "admission_finish":
            game = getattr(harness, "game", harness)
            output = {"session": game.finish_admission(now=frame.get("now", 1000), success=frame.get("success", True))}
        elif kind == "control_start":
            control = load("interop_control", "control_harness.py")
            fixture = fixtures.core_fixture(["core.session", "core.events", "actions", "resume", "handoff"])
            if frame.get("high_risk") is True:
                fixture["action"]["requires_per_action_consent"] = True
                fixture["descriptor"]["actions"][0]["requires_per_action_consent"] = True
            harness = control.ControlHarness(fixture)
            checks, fault_type = control.C, control.U.S.H.InjectedFailure
            output = {"started_control_authority": True}
        elif kind == "action_decision":
            payload = frame["payload"]
            harness.session.action_model.decisions[payload["decision_ref"]] = {
                "player": harness.fixture["player"], "allow": True, "payload": payload}
            output = {"registered_trusted_action_decision": True}
        elif kind == "operation_observe":
            action = harness.session.action_model
            output = {"world_effects": len(action.model.world), "confirmations": len(action.confirmations),
                "consumed_confirmations": sum(item["consumed"] for item in action.confirmations.values()),
                "action_receipts": len(action.receipts), "lease_deadline": harness.session.state["session"]["lease_deadline"]}
        elif kind == "control_restart":
            harness = harness.restart_from_mock_ledger(now=frame.get("now", 1000))
            output = {"restarted_from_mock_ledger": True}
        elif kind == "receipt_compact":
            output = harness.session.compact_closed_receipts(now=frame["now"], max_items=frame.get("max_items", 64))
        elif kind == "control_handoff_proof":
            payload, scope = frame["payload"], harness.session.state["session"]["scope"]
            scope_digest = codec.digest("scope", scope)
            harness.decisions[payload["decision_ref"]] = {"player": scope["player"], "payload": payload, "scope_digest": scope_digest}
            harness.target_proofs[payload["target_proof_ref"]] = {"agent": scope["agent"], "device_id": payload["target_device"],
                "session_id": payload["session_id"], "scope_digest": scope_digest, "expires_at": 100000}
            harness.identities["agent-b"] = {"role": "agent", "principal": scope["agent"], "fresh": True,
                "device_id": payload["target_device"], "expires_at": 100000}
            output = {"registered_trusted_handoff_proof": True}
        elif kind == "control_finish":
            output = {"transfer": harness.advance_transfer(frame["transfer_id"], now=1000)}
        elif kind == "presentation_start":
            presentation = load("interop_presentation", "presentation_harness.py")
            fixture = fixtures.core_fixture(["core.session", "core.events", "actions", "resume", "handoff", "presentation"])
            harness = presentation.PresentationHarness(fixture)
            observation = harness.enroll_device("device-a")
            harness.enroll_device("device-b")
            harness.identities["agent-identity"]["device_id"] = "device-a"
            checks, fault_type = presentation.C, presentation.U.S.H.InjectedFailure
            output = {"observation": observation}
        elif kind == "presentation_proof":
            payload = harness.state["presentation_jobs"][frame["job_id"]]["acquire"]
            output = {key: payload[key] for key in ("authority_proof_ref", "deadline", "device_epoch", "lease_revision")}
        elif kind == "presentation_lease":
            job = harness.state["presentation_jobs"][frame["job_id"]]
            output = {"request_id": job["renewal_id"], "proof": {key: job["lease"][key] for key in
                      ("authority_proof_ref", "deadline", "device_epoch", "lease_revision")}}
        elif kind in {"presentation_restart", "presentation_sweep"}:
            try:
                if kind == "presentation_restart":
                    output = harness.restart_device(frame["device_id"], now=frame["now"],
                        authority_available=frame.get("authority_available", True), fault=frame.get("fault"))
                else:
                    output = harness.sweep_presentation(now=frame["now"], budget=frame.get("budget", 1), fault=frame.get("fault"))
            except fault_type:
                output = {"fixture_fault": frame["fault"]}
        elif kind == "presentation_reachable":
            harness.devices[frame["device_id"]].reachable = frame["reachable"]
            output = {"fixture_reachability_changed": True}
        elif kind == "presentation_observe":
            device = harness.devices[frame["device_id"]]
            output = {"actual_visible": device.actual_visible, "render_calls": device.render_calls,
                      "occupation_count": len(device.occupations)}
        elif kind == "asset_start":
            assets = load("interop_assets", "asset_harness.py")
            fixture = fixtures.core_fixture(["core.session", "core.events", "actions", "resume", "handoff", "presentation", "avatar", "assets"])
            fixture["descriptor"]["avatar_requirements"] = {"accepted_formats": [assets.PORTS.MEDIA]}
            harness = assets.AssetHarness(fixture)
            observation = harness.enroll_device("device-a")
            harness.identities["agent-identity"]["device_id"] = "device-a"
            harness.resources.renderer_profiles["device-a"] = {assets.PORTS.PROFILE}
            for item in frame["assets"]:
                raw = base64.b64decode(item["raw"], validate=True)
                harness.resources.responses[item["locator"]] = {"hops": [{"url": item["locator"], "tls_verified": True,
                    "resolved": ["1.1.1.1"], "connected_ip": "1.1.1.1"}], "chunks": [raw[:10], raw[10:]]}
            checks, fault_type = assets.C, assets.U.S.H.InjectedFailure
            output = {"observation": observation}
        elif kind == "asset_observe":
            output = {"cache_count": len(harness.state["asset_cache"]), "fetch_hops": len(harness.resources.trace),
                      "parse_calls": harness.resources.parse_calls, "session_state": harness.session.state["session"]["state"]}
        elif kind == "launch_start":
            launch = load("interop_launch", "launch_harness.py")
            harness = launch.LaunchHarness(fixtures.core_fixture())
            if frame.get("outcome") is not None:
                harness.launcher.outcomes = [frame["outcome"]]
            checks, fault_type = launch.C, launch.U.S.H.InjectedFailure
            output = {"application_registration": harness.launcher.registration["application_registration"]}
        elif kind == "launch_observe":
            output = {"start_calls": harness.launcher.start_calls, "effects": len(harness.launcher.effects),
                      "has_session": harness.session is not None,
                      "grants": {key: value["state"] for key, value in harness.state["grants"].items()}}
        elif kind == "launch_verify_existing":
            output = {"verified": harness.launcher.verify_existing_effect(frame["launch_permission_ref"])}
        elif kind in {"privacy_start", "forward_start"}:
            privacy = load("interop_privacy", "privacy_harness.py")
            importer_module = load("interop_privacy_import", "source_import.py")
            forwarding = kind == "forward_start"
            fixture = fixtures.core_fixture(["core.session", "core.events", "actions", "privacy-request"] +
                                             (["team", "resume"] if forwarding else []))
            if forwarding:
                fixture["verified_audiences"] = [fixture["player"], fixture["agent"], fixtures.principal("bob", "player")]
            source = {"source_id": "private-source", "source_kind": "player_report", "source_principals": [fixture["player"]],
                      "original_disclosure_scope": [fixture[name] for name in ("player", "agent", "game")]}
            record = {"source": source, "controller": fixture["agent"], "instance": fixture["scope"]["instance"],
                "session_id": "s1", "evidence_ref": "privacy-source-proof", "revision": 1, "state": "active",
                "publishers": [fixture["player"] if forwarding else fixture["agent"]],
                "allowed_readers": source["original_disclosure_scope"], "expires_at": 80000}
            importer = importer_module.SourceImporter({"privacy-source-proof": {**record, "revoked": False}})
            importer.import_record(record, verified_controller=fixture["agent"], session=fixture["session"], now=1000)
            copies = {key: {"source_id": "private-source", "controller": fixture["agent"], "subjects": [fixture["player"]], "state": "present"}
                      for key in ("primary", "backup")}
            if frame.get("retained", False):
                copies["held"] = {**copies["primary"], "retention": {"reason": "legal_hold", "retain_until": 5000}}
            harness = privacy.PrivacyHarness(fixture, importer.snapshot(fixture["session"], now=1000), memory_copies=copies)
            harness.memory.outcomes = [frame.get("outcome", "complete")]
            harness.launcher.running = {"binding": harness.launcher.binding(), "verified": True}
            harness.privacy_identities["other-subject"] = {**harness.privacy_identities["subject-fixture"], "principal": fixtures.principal("bob", "player")}
            checks, fault_type = privacy.C, privacy.U.S.H.InjectedFailure
            output = {"source_id": "private-source"}
        elif kind == "privacy_complete":
            provider = harness.state["privacy_requests"][frame["privacy_request_id"]]["binding"]["provider_operation_ref"]
            harness.memory.complete(provider, now=frame.get("now", 1000))
            output = {"completed_original_storage_job": True}
        elif kind == "privacy_observe":
            output = {"apply_calls": harness.memory.apply_calls, "effects": len(harness.memory.effects),
                      "requests": len(harness.state["privacy_requests"]), "cutoffs": len(harness.state["privacy_cutoffs"]),
                      "copies": {key: value["state"] for key, value in harness.memory.copies.items()}}
        elif kind == "forward_seat":
            # 可信测试输入端口，不是 OperationRequest；只有固定登记玩家可取得当前席位证明。
            authority = harness.session
            state, scope = authority.state["session"], authority.state["session"]["scope"]
            player = fixtures.principal(frame["player"], "player")
            checks.validate_type("Id", frame["proof_ref"])
            if player not in harness.verified_audiences:
                raise ValueError("unregistered_fixture_player")
            key = (player["issuer"], player["subject"], player["kind"])
            proof = {"proof_ref": frame["proof_ref"], "instance": scope["instance"], "session_id": state["session_id"],
                "scope_digest": codec.digest("scope", scope), "game": scope["instance"]["game"], "player": player,
                "membership_revision": state["membership_revision"], "membership_generation": authority.members[key],
                "issued_at": 1000, "expires_at": 100000, "state": "active"}
            checks.validate_type("PlayerSeatAuthorization", proof)
            authority.player_seat_proofs[proof["proof_ref"]] = proof
            output = {"registered_fixture_seat": True, "membership_generation": proof["membership_generation"]}
        elif kind == "forward_observe":
            authority = harness.session
            output = {"chat_events": sum(item["wire"]["envelope"]["type"] == "chat.message" for item in authority.state["events"]),
                      "receipts": len(authority.state["receipts"]), "lease_deadline": authority.state["session"]["lease_deadline"]}
        elif kind == "relay_start":
            relay = load("interop_relay", "relay_harness.py")
            harness = relay.RelayHarness(fixtures.relay_fixture())
            harness.game.launcher.running = {"binding": harness.game.launcher.binding(), "verified": True}
            checks, fault_type = relay.C, relay.InjectedFailure
            output = {"started_relay_authority": True}
        elif kind == "relay_credential":
            try:
                token = harness.credential_for(frame["mailbox_id"], frame["recipient"], now=frame.get("now", 1000))
                output = {"credential": token}
            except checks.ContractError as error:
                output = {"fixture_rejected": error.code}
        elif kind == "relay_inner_proof":
            harness.port.enroll(frame["proof_ref"], frame["credential"], now=frame.get("now", 1000))
            output = {"registered_trusted_inner_proof": True}
        elif kind == "relay_dispatch":
            try:
                reply = harness.dispatch_claim(base64.b64decode(frame["raw"], validate=True), frame["credential"],
                                               now=frame.get("now", 1000), fault=frame.get("fault"))
                output = {"reply": base64.b64encode(reply).decode("ascii")}
            except fault_type:
                output = {"fixture_fault": frame["fault"]}
            except checks.ContractError as error:
                output = {"fixture_rejected": error.code}
        elif kind == "relay_restart":
            harness = harness.restart_from_mock_ledger(now=frame.get("now", 1000), intact=frame.get("intact", True))
            output = {"restarted_relay_mock_ledger": True}
        elif kind == "relay_observe":
            child = harness.game.session
            records = [record for box in harness.state["mailboxes"].values() for record in box["requests"].values()]
            output = {"mailboxes": len(harness.state["mailboxes"]), "dispatch_calls": harness.port.dispatch_calls,
                "states": {state: sum(record["state"] == state for record in records) for state in ("queued", "claimed", "replied", "expired", "closed")},
                "route_revisions": [box["route_revision"] for box in harness.state["mailboxes"].values()],
                "chat_events": 0 if child is None else sum(item["wire"]["envelope"]["type"] == "chat.message" for item in child.state["events"]),
                "world_effects": 0 if child is None else len(child.action_model.model.world),
                "lease_deadline": None if child is None else child.state["session"]["lease_deadline"]}
        else:
            raise ValueError("fixture_command_unknown")
        print(json.dumps(output, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if args.serve:
        return serve()
    node = shutil.which("node")
    if node is None:
        print(json.dumps({"passed": False, "unavailable": "node"}))
        return 1
    result = subprocess.run([node, str(ROOT / "scripts/design_interop_client.mjs"), sys.executable, str(Path(__file__).resolve())],
                            cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
                            capture_output=True, text=True, encoding="utf-8", timeout=90)
    try:
        summary = json.loads(result.stdout)
    except ValueError:
        summary = {"passed": False}
    paths = list((ROOT / "docs/protocol").glob("*")) + [Path(__file__).resolve(), ROOT / "scripts/design_interop_client.mjs"]
    report = {"kind": "g2a-cross-language-fixture-evidence", "created_at": datetime.now(timezone.utc).isoformat(),
              "passed": result.returncode == 0 and summary.get("passed") is True,
              "python": sys.version, "peer": summary, "exit_code": result.returncode, "stderr": result.stderr,
              "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()},
              "not_proven": ["independent vendor or full protocol implementation", "HTTP/TLS/real authentication",
                             "persistent transactions", "all operation configurations or arbitrary interleavings"]}
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "source_sha256"}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
