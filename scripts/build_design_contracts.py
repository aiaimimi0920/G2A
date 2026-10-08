"""从声明式源生成草案 schema/目录；默认检查，只有 --write 才写入。"""

import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "docs" / "protocol"
SPEC = importlib.util.spec_from_file_location("design_contracts", ROOT / "contracts.py")
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


def artifacts():
    registry = {"design_revision": "g2a-design-1", "not_a_wire_version": True,
                "operations": catalog.OPERATIONS, "features": catalog.FEATURE_DEPENDENCIES,
                "errors": catalog.ERRORS}
    return {"contracts.schema.json": catalog.schema(), "operations.json": registry,
            "conformance.template.json": catalog.statement_template()}


def directory():
    lines = ["# 操作与错误目录（生成文件）", "",
             "由 contracts.py 生成；使用规则和语义边界见 [契约使用说明](OPERATION_CONTRACT.md)。",
             "字段精确定义见 [本地 schema](contracts.schema.json) 的 `$defs`；本文不代替授权检查。", ""]
    for name, data in catalog.OPERATIONS.items():
        spec = catalog.TYPES[data["input"]]
        while "$ref" in spec:
            spec = catalog.TYPES[spec["$ref"].rsplit("/", 1)[1]]
        required = spec.get("required", [])
        optional = [key for key in spec.get("properties", {}) if key not in required]
        lines += [f"## {name}", "",
                  f"- 角色：`{' / '.join(data['roles'])}`；入口：`{data['lane']}`；能力：`{data['feature']}`；重试族：`{data['mode']}`。",
                  f"- 输入：`{data['input']}`；必需字段：`{' / '.join(required)}`；可选字段：`{' / '.join(optional) or '无'}`。",
                  f"- 成功输出：`{data['output']}`。",
                  f"- 语义条件：{data['semantic_guard']}", ""]
    lines += ["## 边界错误目录", "", "| code | category | retry | outcome | HTTP |",
              "| --- | --- | --- | --- | --- |"]
    for code, data in catalog.ERRORS.items():
        lines.append(f"| {code} | {data['category']} | {data['retry']} | {data['outcome']} | {data['http_status']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="显式更新仓库内 schema、目录与声明模板")
    args = parser.parse_args()
    outputs = {name: json.dumps(value, ensure_ascii=False, indent=2) + "\n" for name, value in artifacts().items()}
    outputs["OPERATION_DIRECTORY.md"] = directory()
    for name, expected in outputs.items():
        path = ROOT / name
        if args.write:
            path.write_text(expected, encoding="utf-8", newline="\n")
        elif not path.exists() or path.read_text(encoding="utf-8") != expected:
            raise SystemExit(f"Generated artifact mismatch: {name}")
        print(("Wrote " if args.write else "Verified ") + name)


if __name__ == "__main__":
    main()
