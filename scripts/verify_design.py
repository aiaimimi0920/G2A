"""统一验证协议草案；只读仓库，报告可显式写入临时目录。

仅汇总实际执行证据，不把通过当作生产符合性认证。无网络/引擎/模型调用。
"""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def run(command):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, *command], cwd=ROOT, env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=180)
    return {"command": command, "exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="可选完整 JSON 回执路径；不自动创建目录")
    parser.add_argument("--interop", action="store_true", help="同时运行需要 Node.js 的独立 JavaScript 客户端夹具")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    # Windows 标准流显式使用 UTF-8，子进程通过 PYTHONIOENCODING 继承相同约定。
    os.environ["PYTHONIOENCODING"] = "utf-8"
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    generated = run(["scripts/build_design_contracts.py"])
    replay = run(["scripts/replay_design.py"])
    interop = run(["scripts/verify_design_interop.py"]) if args.interop else None
    log = io.StringIO()
    try:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_design_*.py")
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        tests = {"count": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                 "skipped": len(result.skipped), "log": log.getvalue()}
        tests_passed = result.wasSuccessful() and result.testsRun > 0 and not result.skipped
    except Exception as error:
        tests = {"runner_error_type": type(error).__name__, "log": log.getvalue()}
        tests_passed = False
    tracked_inputs = sorted((ROOT / "docs" / "protocol").glob("*"))
    tracked_inputs += sorted((ROOT / "tests").glob("test_design_*.py"))
    tracked_inputs += [ROOT / "scripts" / name for name in ("build_design_contracts.py", "replay_design.py", "verify_design.py",
                                                          "verify_design_interop.py", "design_interop_client.mjs")]
    hashes = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in tracked_inputs if path.is_file()}
    try:
        summary = json.loads(replay["stdout"].strip())
        replay_passed = summary["kind"] == "pure-memory-design-replay" and summary["passed"] == 42 and summary["failed"] == 0
    except (ValueError, KeyError, TypeError):
        summary, replay_passed = None, False
    try:
        interop_passed = interop is None or (interop["exit_code"] == 0 and json.loads(interop["stdout"])["passed"] is True)
    except (ValueError, KeyError, TypeError):
        interop_passed = False
    passed = generated["exit_code"] == 0 and replay["exit_code"] == 0 and replay_passed and tests_passed and interop_passed
    report = {"kind": "g2a-design-local-evidence", "created_at": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "passed": passed, "generated": generated, "replay": replay,
              "replay_summary": summary, "design_tests": tests, "interop": interop, "source_sha256": hashes,
              "not_proven": ["production authentication/crypto/network/storage/engine", "third-party interoperability",
                             "all state interleavings", "legal approval or public release"],
              "completion_claim": "local checks only; evaluate DEVELOPMENT_STATUS and operation traces separately"}
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "design_tests": {key: value for key, value in tests.items() if key != "log"},
                      "replay": summary, "interop": "passed" if interop is not None and interop_passed else "failed" if interop else "not_run"}, ensure_ascii=False))
    if not passed:
        print(generated["stdout"] + generated["stderr"] + replay["stdout"] + replay["stderr"] + tests["log"])
        if interop is not None:
            print(interop["stdout"] + interop["stderr"])
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
